"""국가법령정보 OPEN API 클라이언트 (PoC: 전입신고 근거 검증).

- 검색: GET http://www.law.go.kr/DRF/lawSearch.do  (target=law)
- 본문: GET http://www.law.go.kr/DRF/lawService.do  (target=law, MST=법령일련번호)
- 인증: OC 파라미터(가입 ID). 호출 서버 IP/도메인 사전 등록 필요.
- .env 의 LAW_OC 사용.

절차별로 "법령 + 조문 + 법정기한"을 실조회해 플레이북 값과 교차검증하고,
legal_basis / evidence / verification_status 를 만들어 돌려준다.
"""

from __future__ import annotations

import os
import re
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

LAW_OC = os.environ.get("LAW_OC", "")
BASE = "http://www.law.go.kr/DRF"
TIMEOUT = 8

_UNIT_DAYS = {"일": 1, "개월": 30, "년": 365}

# 프로세스 수명 캐시 ((법령명|조문) 키, 법령은 자주 바뀌지 않음)
_ground_cache: dict[str, dict] = {}


def _today() -> str:
    return date.today().isoformat()


def _fmt_date(yyyymmdd: str) -> str:
    s = str(yyyymmdd or "")
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def search_law(query: str) -> dict | None:
    """법령명을 검색해 현행 최상위 1건의 메타데이터를 반환."""
    try:
        r = requests.get(
            f"{BASE}/lawSearch.do",
            params={"OC": LAW_OC, "target": "law", "type": "JSON", "query": query, "display": "5"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None

    laws = (data.get("LawSearch") or {}).get("law")
    if not laws:
        return None
    if isinstance(laws, dict):
        laws = [laws]
    # 정확히 같은 법령명을 우선(가운뎃점·공백 변형 무시), 없으면 첫 현행
    def norm(s: str) -> str:
        return re.sub(r"[ㆍ·‧\s]", "", s or "")
    nq = norm(query)
    exact = next((l for l in laws if norm(l.get("법령명한글", "")) == nq), None)
    law = exact or laws[0]
    return {
        "law_name": law.get("법령명한글", "").strip(),
        "mst": law.get("법령일련번호", ""),
        "law_id": law.get("법령ID", ""),
        "enforcement_date": _fmt_date(law.get("시행일자", "")),
        "promulgation_date": _fmt_date(law.get("공포일자", "")),
        "ministry": law.get("소관부처명", ""),
        "kind": law.get("법령구분명", ""),
    }


def _collect_articles(obj) -> list:
    """응답 구조에 상관없이 '조문단위' 리스트를 찾아낸다."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "조문단위":
                return v if isinstance(v, list) else [v]
            found = _collect_articles(v)
            if found:
                return found
    elif isinstance(obj, list):
        for it in obj:
            found = _collect_articles(it)
            if found:
                return found
    return []


def _article_text(article: dict) -> str:
    """조문 내 모든 '...내용' 텍스트(조문내용·항내용·호내용 등)를 이어붙인다."""
    parts: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.endswith("내용") and isinstance(v, str):
                    parts.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)
        elif isinstance(o, str):
            return

    walk(article)
    # 중복 제거하며 순서 유지
    seen, out = set(), []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return "\n".join(out)


def get_article(mst: str, title_contains: str) -> dict | None:
    """법령 본문에서 제목에 키워드가 든 조문을 찾아 텍스트로 반환."""
    try:
        r = requests.get(
            f"{BASE}/lawService.do",
            params={"OC": LAW_OC, "target": "law", "MST": mst, "type": "JSON"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None

    for art in _collect_articles(data):
        title = str(art.get("조문제목", ""))
        if title_contains in title:
            no = str(art.get("조문번호", "")).strip()
            branch = str(art.get("조문가지번호", "")).strip()
            label = f"제{no}조" + (f"의{branch}" if branch and branch != "0" else "")
            if title:
                label += f"({title})"
            return {"label": label, "title": title, "text": _article_text(art)}
    return None


def _find_deadline(text: str) -> tuple[str | None, str | None, int | None]:
    """'N(일|개월|년) 이내'를 포함한 문장·문구·환산일수를 추출."""
    for sent in re.split(r"(?<=다\.)\s*|\n", text):
        m = re.search(r"(\d+)\s*(일|개월|년)\s*이내", sent)
        if m:
            num, unit = int(m.group(1)), m.group(2)
            return sent.strip(), f"{num}{unit} 이내", num * _UNIT_DAYS[unit]
    return None, None, None


def _build_legal_result(law: dict, art: dict | None, expected_days: int | None) -> dict:
    span, deadline_text, found_days = (None, None, None)
    if art:
        span, deadline_text, found_days = _find_deadline(art["text"])
    if not art:
        status = "needs_review"
    elif expected_days is None:
        status = "partial"
    elif found_days is not None and found_days == expected_days:
        status = "verified"
    else:
        status = "partial"
    return {
        "verification_status": status,
        "law_name": law["law_name"],
        "article": art["label"] if art else None,
        "article_title": art["title"] if art else None,  # 매칭된 조문제목(학습 카탈로그 영속용)
        "enforcement_date": law["enforcement_date"],
        "promulgation_date": law["promulgation_date"],
        "ministry": law["ministry"],
        "deadline_in_law_text": deadline_text,
        "deadline_days_in_law": found_days,
        "deadline_days_expected": expected_days,
        "evidence_span": span,
        "source_url": f"https://www.law.go.kr/법령/{law['law_name']}",
        "fetched_at": _today(),
    }


def ground_legal(law_query: str, article_title: str, expected_days: int | None = None) -> dict:
    """주어진 (법령·조문 제목 키워드)을 실시간 조회해 근거·기한을 grounding + 교차검증."""
    key = f"{law_query}|{article_title}"
    if key in _ground_cache:
        return _ground_cache[key]
    if not LAW_OC:
        return {"verification_status": "needs_review", "error": "LAW_OC 미설정"}
    law = search_law(law_query)
    if not law:
        return {"verification_status": "needs_review", "error": "법령 조회 실패(키/IP 등록 또는 네트워크)"}
    result = _build_legal_result(law, get_article(law["mst"], article_title), expected_days)
    _ground_cache[key] = result
    return result


def ground_legal_auto(law_query: str, keywords: list[str], expected_days: int | None = None) -> dict:
    """법령명 + 여러 키워드로 조문을 '검색'해 grounding.
    정확한 조문 제목을 몰라도 절차 키워드(예: '사업자등록')로 매칭 → 자기학습 카탈로그용.
    """
    if not LAW_OC:
        return {"verification_status": "needs_review", "error": "LAW_OC 미설정"}
    law = search_law(law_query)
    if not law:
        return {"verification_status": "needs_review", "error": "법령 조회 실패"}
    art = None
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue
        art = get_article(law["mst"], kw)
        if art:
            break
    return _build_legal_result(law, art, expected_days)
