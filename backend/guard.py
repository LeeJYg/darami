"""부스 시연 안전장치 — LLM 답변에 '플레이북에 없는' 금액·연락처가 섞이는 것을 코드로 차단한다.

프롬프트 규칙만으로는 확률적으로만 막힌다(실측: 금액 3/3·전화번호 3/3 노출).
여기서는 답변 문장 단위로 검사해, 근거(플레이북·시스템 프롬프트)에 없는
금액/전화번호가 든 문장을 버리고 '확인 안내' 문장으로 대체한다.
"""

from __future__ import annotations

import re

# 금액: "3만 원", "50,000원", "5만원" / 전화번호: "02-2620-3000", "1588-1234"
MONEY_RE = re.compile(r"\d[\d,]*\s*(?:억|만|천)?\s*원")
PHONE_RE = re.compile(r"(?<!\d)(?:0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}|1\d{3}[-\s]?\d{4})(?!\d)")

# 문장 분리(한국어 종결 + 줄바꿈). 구분자를 남겨 다시 이어붙일 수 있게 한다.
_SENT_SPLIT = re.compile(r"(?<=[.!?？！。])\s+|\n+")

SAFE_SENTENCE = "정확한 금액과 담당 기관 연락처는 관할 주민센터나 정부24에서 확인하실 수 있어요."


def _norm(s: str) -> str:
    """근거 대조용 정규화 — 공백·쉼표 차이로 '근거 있음'을 놓치지 않게 한다."""
    return re.sub(r"[\s,]", "", s)


def find_ungrounded(text: str, grounded: str) -> dict[str, list[str]]:
    """text 안에서 grounded(플레이북 등)에 없는 금액·전화번호를 찾는다."""
    g = _norm(grounded or "")
    hits: dict[str, list[str]] = {}
    for kind, pat in (("money", MONEY_RE), ("phone", PHONE_RE)):
        found = [m for m in pat.findall(text or "") if _norm(m) not in g]
        if found:
            hits[kind] = found
    return hits


def sanitize_reply(reply: str, grounded: str) -> tuple[str, dict[str, list[str]]]:
    """근거 없는 금액·전화번호가 든 문장을 제거하고 안내 문장으로 대체한다.

    반환: (정제된 reply, 제거된 항목들). 제거된 게 없으면 원문 그대로.
    """
    reply = reply or ""
    hits = find_ungrounded(reply, grounded)
    if not hits:
        return reply, {}

    kept, removed = [], {}
    for sent in _SENT_SPLIT.split(reply):
        if not sent.strip():
            continue
        h = find_ungrounded(sent, grounded)
        if h:
            for k, v in h.items():
                removed.setdefault(k, []).extend(v)
            continue
        kept.append(sent.strip())

    kept.append(SAFE_SENTENCE)
    return " ".join(kept), removed
