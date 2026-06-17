"""다람이 백엔드 — FastAPI + Upstage Solar Pro 프록시.

- 프론트엔드에서 /api/chat 으로 대화 메시지를 보내면
  선별된 이벤트 플레이북을 시스템 프롬프트에 주입해 Solar Pro2를 호출하고,
  결과(JSON)를 SSE로 흘려준다.
- API 키는 .env(UPSTAGE_API_KEY)에서만 읽고 프론트로 노출하지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI

from prompts import build_system_prompt, build_generation_prompt, build_persona_prompt
from sources.curate import curate_event, legal_for, curate_dynamic

load_dotenv()

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY", "")
SOLAR_MODEL = os.environ.get("SOLAR_MODEL", "solar-pro2")
PLAYBOOK_DIR = Path(__file__).parent / "playbooks"

client = OpenAI(api_key=UPSTAGE_API_KEY, base_url="https://api.upstage.ai/v1") if UPSTAGE_API_KEY else None

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


class GenReq(BaseModel):
    description: str                    # 사용자가 자유롭게 입력한 생활 이벤트 설명
    persona: Optional[dict] = None      # 거주지 등(지자체 혜택 grounding에 사용)


class PersonaReq(BaseModel):
    persona: Optional[dict] = None     # 현재 페르소나(facts)
    messages: List[Message]            # 대화 기록(최신 사용자 입력 포함)


# ---------- 플레이북 ----------
def load_playbook(event: str | None) -> dict:
    if not event:
        return {"event": None, "title": "", "procedures": []}
    # on-demand 큐레이션(법령 grounding + 캐시). 실패 시 정적 JSON으로 fallback.
    try:
        curated = curate_event(event)
        if curated:
            return curated
    except Exception:  # noqa: BLE001
        pass
    path = PLAYBOOK_DIR / f"{event}.json"
    if not path.exists():
        return {"event": event, "title": "", "procedures": []}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"ok": True, "model": SOLAR_MODEL, "hasKey": bool(UPSTAGE_API_KEY)}


@app.get("/api/playbook/{event}")
def get_playbook(event: str, region: Optional[str] = None):
    """프론트가 절차 상세(서류·링크·출처)를 렌더하기 위한 전체 플레이북.
    region: 사용자 거주지(시도). 지자체/광역 혜택 grounding에 사용."""
    try:
        curated = curate_event(event, region=region)
        if curated:
            return JSONResponse(curated)
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(load_playbook(event))


@app.get("/api/legal-basis/{procedure_id}")
def legal_basis(procedure_id: str):
    """절차의 법적 근거를 국가법령정보 OPEN API로 실시간 조회·교차검증.
    지원하지 않는 절차면 {"supported": false}."""
    return JSONResponse(legal_for(procedure_id))


# ---------- 핵심: 대화 ----------
def call_solar(system_prompt: str, messages: list[Message]) -> dict:
    """Solar Pro2를 호출해 구조화 JSON 응답을 받는다."""
    chat_messages = [{"role": "system", "content": system_prompt}]
    chat_messages += [{"role": m.role, "content": m.content} for m in messages]

    completion = client.chat.completions.create(
        model=SOLAR_MODEL,
        messages=chat_messages,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw = completion.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 모델이 가끔 코드블록/잡텍스트를 섞으면 중괄호 범위만 추출
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {"reply": raw, "eventDetected": None, "askMissing": [], "quickReplies": [], "boardOps": []}


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/generate")
def generate(req: GenReq):
    """자유 입력 생활 이벤트 → 동적 플레이북 (source-first 실데이터 큐레이션).

    보조금24를 이벤트 키워드로 검색해 실제 서비스에서 절차를 구성(grounding)하고,
    핵심 신고 절차는 법령 API로 보강. grounding 안 되는 건 'ai'(미검증)로 표기.
    """
    if client is None:
        return JSONResponse({"error": "UPSTAGE_API_KEY가 설정되지 않았습니다."}, status_code=500)
    try:
        playbook = curate_dynamic(req.description.strip(), req.persona, _solar_json)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"동적 큐레이션 실패: {e}"}, status_code=500)
    return JSONResponse(playbook)


def _solar_json(system_prompt: str, user_content: str, temperature: float = 0.2) -> dict:
    """Solar를 1회 호출해 JSON 객체를 받아 파싱한다(비스트리밍)."""
    completion = client.chat.completions.create(
        model=SOLAR_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    raw = completion.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start : end + 1]) if start != -1 and end != -1 else {}


@app.post("/api/persona")
def persona(req: PersonaReq):
    """대화 입력으로 사용자 페르소나를 갱신하고 충돌을 검사한다(턴당 1차 호출)."""
    if client is None:
        return JSONResponse({"error": "UPSTAGE_API_KEY가 설정되지 않았습니다."}, status_code=500)
    # 최근 대화를 한 덩어리로 만들어 최신 입력 중심으로 갱신
    convo = "\n".join(f"{m.role}: {m.content}" for m in req.messages[-8:])
    result = _solar_json(build_persona_prompt(req.persona or {}), convo, temperature=0.1)
    facts = result.get("facts")
    if not isinstance(facts, dict):
        facts = (req.persona or {}).get("facts") or {}
    conflict = result.get("conflict")
    if not (isinstance(conflict, dict) and conflict.get("question")):
        conflict = None
    return JSONResponse({"facts": facts, "conflict": conflict})


@app.post("/api/chat")
async def chat(req: ChatReq):
    # 동적 이벤트는 요청에 실린 플레이북을 우선 사용, 없으면 디스크에서 로드
    playbook = req.playbook or load_playbook(req.event)
    system_prompt = build_system_prompt(playbook, req.persona)

    async def gen():
        if client is None:
            yield sse("error", {"message": "UPSTAGE_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요."})
            return

        # Solar 호출은 동기 → 스레드로 빼서 이벤트 루프를 막지 않음
        try:
            result = await asyncio.to_thread(call_solar, system_prompt, req.messages)
        except Exception as e:  # noqa: BLE001
            yield sse("error", {"message": f"Solar 호출 실패: {e}"})
            return

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

    return StreamingResponse(gen(), media_type="text/event-stream")
