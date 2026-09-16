"""다람이 백엔드 — FastAPI + 멀티 LLM 프록시 (Upstage Solar Pro / LG K-EXAONE).

- 프론트엔드에서 /api/chat 으로 대화 메시지를 보내면
  선별된 이벤트 플레이북을 시스템 프롬프트에 주입해 선택된 LLM을 호출하고,
  결과(JSON)를 SSE로 흘려준다.
- 두 모델 모두 OpenAI 호환 chat completions 라 base_url/model/extra_body 만 바꿔 끼운다.
    · Solar Pro  : Upstage (https://api.upstage.ai/v1, model=solar-pro2)
    · K-EXAONE   : LG / Friendli dedicated endpoint (OpenAI 호환, reasoning off)
- API 키는 .env 에서만 읽고 프론트로 노출하지 않는다. 프론트는 provider 키("solar"|"kexaone")만 보낸다.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI

import demo
from compose import COMPOSITES, merge_playbooks
from guard import sanitize_reply
from verified_move import answer as verified_move_answer
from prompts import build_system_prompt, build_generation_prompt, build_persona_prompt
from sources.curate import curate_event, legal_for, curate_dynamic

load_dotenv()

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY", "")
SOLAR_MODEL = os.environ.get("SOLAR_MODEL", "solar-pro2")

# LG K-EXAONE (Friendli dedicated endpoint) — OpenAI 호환
KEXAONE_API_KEY = os.environ.get("KEXAONE_API_KEY", "")
KEXAONE_ENDPOINT = os.environ.get("KEXAONE_ENDPOINT", "")  # 배포된 endpoint id = model 값
KEXAONE_BASE_URL = os.environ.get("KEXAONE_BASE_URL", "https://api.friendli.ai/dedicated/v1")

PLAYBOOK_DIR = Path(__file__).parent / "playbooks"


# ---------- LLM 제공자(provider) 레지스트리 ----------
@dataclass
class Provider:
    key: str               # 프론트가 보내는 식별자
    label: str             # 공식 표기명(UI 노출)
    model: str             # chat.completions 의 model 값
    client: Optional[OpenAI]
    extra_body: dict = field(default_factory=dict)  # provider 고유 옵션(예: K-EXAONE reasoning off)

    @property
    def available(self) -> bool:
        return self.client is not None and bool(self.model)


PROVIDERS: dict[str, Provider] = {
    "solar": Provider(
        key="solar",
        label="Solar Pro",
        model=SOLAR_MODEL,
        client=OpenAI(api_key=UPSTAGE_API_KEY, base_url="https://api.upstage.ai/v1") if UPSTAGE_API_KEY else None,
    ),
    "kexaone": Provider(
        key="kexaone",
        label="K-EXAONE",
        model=KEXAONE_ENDPOINT,
        client=OpenAI(api_key=KEXAONE_API_KEY, base_url=KEXAONE_BASE_URL) if KEXAONE_API_KEY else None,
        # 구조화 JSON만 필요하므로 추론(thinking) 비활성 → 더 빠르고 깔끔한 응답
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    ),
}
DEFAULT_PROVIDER = "solar"


def get_provider(key: Optional[str]) -> Provider:
    """요청의 provider 키 → Provider. 미지정/미가용이면 사용 가능한 기본값으로 폴백."""
    p = PROVIDERS.get(key or DEFAULT_PROVIDER)
    if p and p.available:
        return p
    # 요청한 provider가 없거나 키 미설정 → 가용한 첫 provider
    fallback = PROVIDERS.get(DEFAULT_PROVIDER)
    if fallback and fallback.available:
        return fallback
    return next((p for p in PROVIDERS.values() if p.available), PROVIDERS[DEFAULT_PROVIDER])


app = FastAPI(title="다람이 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 데이터 모델 ----------
class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatReq(BaseModel):
    event: Optional[str] = None        # "move" | "birth" | "resignation" | 동적 슬러그
    playbook: Optional[dict] = None    # 동적 이벤트는 생성된 플레이북을 직접 실어 보낸다
    persona: Optional[dict] = None     # 지금까지 파악한 사용자 페르소나(facts)
    messages: List[Message]
    provider: Optional[str] = None     # "solar" | "kexaone" (미지정 시 기본값)


class GenReq(BaseModel):
    description: str                    # 사용자가 자유롭게 입력한 생활 이벤트 설명
    persona: Optional[dict] = None      # 거주지 등(지자체 혜택 grounding에 사용)
    provider: Optional[str] = None      # "solar" | "kexaone"


class PersonaReq(BaseModel):
    persona: Optional[dict] = None     # 현재 페르소나(facts)
    messages: List[Message]            # 대화 기록(최신 사용자 입력 포함)
    provider: Optional[str] = None     # "solar" | "kexaone"


# ---------- 플레이북 ----------
def load_playbook(event: str | None) -> dict:
    if not event:
        return {"event": None, "title": "", "procedures": []}
    # 복합 이벤트("출산 후 이사" 등)는 재료 이벤트를 각각 불러 한 보드로 합친다.
    if event in COMPOSITES:
        parts = [load_playbook(e) for e in COMPOSITES[event]["events"]]
        return merge_playbooks(event, parts)
    # on-demand 큐레이션(법령 grounding + 캐시). 실패 시 정적 JSON으로 fallback.
    try:
        curated = curate_event(event)
        if curated and curated.get("procedures"):
            return curated
    except Exception:  # noqa: BLE001
        pass
    path = PLAYBOOK_DIR / f"{event}.json"
    if not path.exists():
        return {"event": event, "title": "", "procedures": []}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "demoMode": demo.enabled(),
        "defaultProvider": DEFAULT_PROVIDER,
        "providers": {k: p.available for k, p in PROVIDERS.items()},
    }


@app.get("/api/providers")
def providers():
    """프론트 LLM 토글용 — 선택 가능한 모델과 가용성."""
    return {
        "default": DEFAULT_PROVIDER,
        "demoMode": demo.enabled(),
        "providers": [
            {"key": p.key, "label": p.label, "available": p.available}
            for p in PROVIDERS.values()
        ],
    }


@app.get("/api/playbook/compose/{slug}")
def get_composed_playbook(slug: str, region: Optional[str] = None):
    """복합 생활 이벤트 → 하나의 보드용 플레이북. 지원하지 않는 slug 면 404."""
    if slug not in COMPOSITES:
        return JSONResponse({"error": f"지원하지 않는 복합 이벤트: {slug}"}, status_code=404)
    parts = []
    for ev in COMPOSITES[slug]["events"]:
        try:
            curated = curate_event(ev, region=region)
            parts.append(curated if (curated and curated.get("procedures")) else load_playbook(ev))
        except Exception:  # noqa: BLE001
            parts.append(load_playbook(ev))
    return JSONResponse(merge_playbooks(slug, parts))


@app.get("/api/playbook/{event}")
def get_playbook(event: str, region: Optional[str] = None):
    """프론트가 절차 상세(서류·링크·출처)를 렌더하기 위한 전체 플레이북.
    region: 사용자 거주지(시도). 지자체/광역 혜택 grounding에 사용."""
    try:
        curated = curate_event(event, region=region)
        if curated and curated.get("procedures"):
            return JSONResponse(curated)
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(load_playbook(event))


@app.get("/api/legal-basis/{procedure_id}")
def legal_basis(procedure_id: str):
    """절차의 법적 근거를 국가법령정보 OPEN API로 실시간 조회·교차검증.
    지원하지 않는 절차면 {"supported": false}."""
    return JSONResponse(legal_for(procedure_id))


# ---------- 핵심: LLM 호출 (provider 공통) ----------
def _parse_json(raw: str, fallback: dict) -> dict:
    """모델 응답에서 JSON 객체를 파싱. 잡텍스트가 섞이면 중괄호 범위만 추출."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
        return fallback


def _create_json(provider: Provider, chat_messages: list[dict], temperature: float) -> str:
    """선택된 provider로 구조화 JSON 응답(raw 문자열)을 받는다."""
    completion = provider.client.chat.completions.create(
        model=provider.model,
        messages=chat_messages,
        response_format={"type": "json_object"},
        temperature=temperature,
        extra_body=provider.extra_body or None,
    )
    return completion.choices[0].message.content or "{}"


def call_chat(
    provider: Provider,
    system_prompt: str,
    messages: list[Message],
    grounded: str | None = None,
) -> dict:
    """선택된 LLM을 호출해 대화용 구조화 JSON 응답을 받는다.

    grounded: 금액·연락처의 근거로 인정할 텍스트(플레이북 JSON). 비우면 아무 금액도 근거 없음으로 본다.
    근거에 없는 금액·전화번호는 여기서 코드로 제거한다(프롬프트 규칙만으로는 못 막는다).
    """
    chat_messages = [{"role": "system", "content": system_prompt}]
    chat_messages += [{"role": m.role, "content": m.content} for m in messages]
    raw = _create_json(provider, chat_messages, temperature=0.3)
    result = _parse_json(
        raw, {"reply": raw, "eventDetected": None, "askMissing": [], "quickReplies": [], "boardOps": []}
    )
    clean, removed = sanitize_reply(str(result.get("reply", "")), grounded or "")
    result["reply"] = clean
    if removed:
        result["ungroundedRemoved"] = removed
    return result


def make_json_caller(provider: Provider):
    """curate_dynamic / persona 가 쓰는 단발 JSON 호출자(provider 바인딩)."""
    def _json_call(system_prompt: str, user_content: str, temperature: float = 0.2) -> dict:
        raw = _create_json(
            provider,
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            temperature,
        )
        return _parse_json(raw, {})

    return _json_call


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/generate")
def generate(req: GenReq):
    """자유 입력 생활 이벤트 → 동적 플레이북 (source-first 실데이터 큐레이션).

    보조금24를 이벤트 키워드로 검색해 실제 서비스에서 절차를 구성(grounding)하고,
    핵심 신고 절차는 법령 API로 보강. grounding 안 되는 건 'ai'(미검증)로 표기.
    """
    provider = get_provider(req.provider)
    if provider.client is None:
        return JSONResponse({"error": f"{provider.label} API 키가 설정되지 않았습니다."}, status_code=500)
    try:
        playbook = curate_dynamic(req.description.strip(), req.persona, make_json_caller(provider))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"동적 큐레이션 실패: {e}"}, status_code=500)
    return JSONResponse(playbook)


@app.post("/api/persona")
def persona(req: PersonaReq):
    """대화 입력으로 사용자 페르소나를 갱신하고 충돌을 검사한다(턴당 1차 호출)."""
    prior = (req.persona or {}).get("facts") or {}
    if demo.enabled():
        return JSONResponse(demo.persona_turn((req.persona or {}).get("event"), prior, req.messages))
    provider = get_provider(req.provider)
    if provider.client is None:
        return JSONResponse({"error": f"{provider.label} API 키가 설정되지 않았습니다."}, status_code=500)
    # 최근 대화를 한 덩어리로 만들어 최신 입력 중심으로 갱신
    prior_facts = (req.persona or {}).get("facts") or {}
    convo = "\n".join(f"{m.role}: {m.content}" for m in req.messages[-8:])
    result = make_json_caller(provider)(build_persona_prompt(req.persona or {}), convo, temperature=0.1)
    facts = result.get("facts")
    if not isinstance(facts, dict):
        facts = prior_facts
    conflict = result.get("conflict")
    if not (isinstance(conflict, dict) and conflict.get("question")):
        conflict = None
    # ★ conflict는 '이미 저장된 facts'와의 모순일 때만 성립한다(룰 3a를 코드로 강제 · 모델 무관).
    #   대조할 기존 facts가 없으면(첫 입력 등) 모델이 confirm성 conflict를 만들어도 무시 → 빈 facts 루프 차단.
    if not prior_facts:
        conflict = None
    return JSONResponse({"facts": facts, "conflict": conflict})


async def _emit(result: dict):
    """구조화 결과 하나를 SSE(token* → meta → done)로 흘려준다. 실시간·시연 모드 공용."""
    reply = str(result.get("reply", "")).strip()

    # 1) reply를 짧게 끊어 타이핑 효과로 흘려준다
    buf = ""
    for ch in reply:
        buf += ch
        if len(buf) >= 2 or ch in " .,!?\n":
            yield sse("token", {"text": buf})
            buf = ""
            await asyncio.sleep(0.012)
    if buf:
        yield sse("token", {"text": buf})

    # 2) 보드 갱신·빠른답변 등 구조화 메타를 마지막에 전달
    yield sse(
        "meta",
        {
            "eventDetected": result.get("eventDetected"),
            "askMissing": result.get("askMissing", []),
            "quickReplies": result.get("quickReplies", []),
            "boardOps": result.get("boardOps", []),
            "userTodos": result.get("userTodos", []),
        },
    )
    yield sse("done", {})


@app.post("/api/chat")
async def chat(req: ChatReq):
    # 동적 이벤트는 요청에 실린 플레이북을 우선 사용, 없으면 디스크에서 로드
    playbook = req.playbook or load_playbook(req.event)
    system_prompt = build_system_prompt(playbook, req.persona)
    provider = get_provider(req.provider)

    async def gen():
        latest = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        verified = verified_move_answer(latest)
        if verified is not None:
            async for chunk in _emit({"reply": verified, "boardOps": []}):
                yield chunk
            return
        if demo.enabled():
            result = demo.chat_turn(req.event, req.messages)
            result["reply"], _ = sanitize_reply(
                str(result.get("reply", "")), json.dumps(playbook, ensure_ascii=False)
            )
            async for chunk in _emit(result):
                yield chunk
            return

        if provider.client is None:
            yield sse("error", {"message": f"{provider.label} API 키가 설정되지 않았습니다. backend/.env를 확인하세요."})
            return

        # LLM 호출은 동기 → 스레드로 빼서 이벤트 루프를 막지 않음
        try:
            grounded = json.dumps(playbook, ensure_ascii=False)
            result = await asyncio.to_thread(call_chat, provider, system_prompt, req.messages, grounded)
        except Exception as e:  # noqa: BLE001
            yield sse("error", {"message": f"{provider.label} 호출 실패: {e}"})
            return

        async for chunk in _emit(result):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")
