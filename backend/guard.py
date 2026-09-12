"""부스 시연 안전장치 — LLM 답변에 '플레이북에 없는' 금액·연락처가 섞이는 것을 코드로 차단한다.

프롬프트 규칙만으로는 확률적으로만 막힌다(실측: 금액 3/3·전화번호 3/3 노출).
여기서는 답변 문장 단위로 검사해, 근거(플레이북·시스템 프롬프트)에 없는
금액/전화번호가 든 문장을 버리고 '확인 안내' 문장으로 대체한다.
"""

from __future__ import annotations

import re

# 금액: "3만 원", "50,000원", "5만원", "삼만 원" / 전화번호: "02-2620-3000", "02)2620-3000", "1588-1234"
# 한글 수사와 괄호 국번은 부스 적대 시험(eval/guard_adversarial.py)에서 실제로 새던 표기다.
MONEY_RE = re.compile(r"\d[\d,]*\s*(?:억|만|천)?\s*원|[일이삼사오육칠팔구십백]{1,4}\s*(?:억|만|천)\s*원")
PHONE_RE = re.compile(
    r"(?<!\d)(?:0\d{1,2}[-\s.)]?\s?\d{3,4}[-\s.]?\d{4}|1\d{3}[-\s.]?\d{4})(?!\d)"
)

# 국번 없는 3~4자리 공공 상담번호("1350" 등)는 위 PHONE_RE 에 걸리지 않는다(eval/verify_short_phone.py).
# 부스에서는 틀린 단축번호도 틀린 대표번호와 똑같은 사고라서 막되,
# "120일"·"365일" 같은 수량 표현을 지우지 않도록 (a) 실재하는 공공번호 목록과
# (b) 연락처 문맥어가 앞에 붙은 3~4자리, 두 조건으로만 잡는다.
SHORT_CODES = (
    "1301", "1330", "1332", "1339", "1345", "1350", "1355", "1357", "1359",
    "1366", "1372", "1382", "1385", "1388", "1391", "1393", "1399",
    "110", "111", "112", "113", "117", "118", "119", "120", "125", "128", "129", "132",
)
# 단축번호 뒤에 오면 '번호'가 아니라 수량인 단위들.
_UNIT = r"(?:개월|일간|일차|퍼센트|가지|시간|번째|일|년|월|주|분|초|원|명|개|건|호|세|차|%|만|천|억)"
SHORT_PHONE_RE = re.compile(
    r"(?<![\d\-.~∼〜–—])(?:" + "|".join(SHORT_CODES) + r")(?![\d\-])(?!\.\d)(?![~∼〜–—])(?!\s*" + _UNIT + r")"
)
CONTEXT_SHORT_RE = re.compile(
    r"(?:전화|번호|연락처|문의|상담|콜센터|국번\s*없이|☎)[^\d\n]{0,10}"
    r"(?<![\d\-.~∼〜–—])(\d{3,4})(?![\d\-])(?!\.\d)(?![~∼〜–—])(?!\s*" + _UNIT + r")"
)

# kind -> 검사할 정규식들. phone 은 대표번호·단축번호·문맥 규칙을 모두 본다.
_KIND_PATS: dict[str, tuple[re.Pattern[str], ...]] = {
    "money": (MONEY_RE,),
    "phone": (PHONE_RE, SHORT_PHONE_RE, CONTEXT_SHORT_RE),
}

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
    for kind, pats in _KIND_PATS.items():
        found: list[str] = []
        for pat in pats:
            for m in pat.findall(text or ""):
                if _norm(m) not in g and m not in found:
                    found.append(m)
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
