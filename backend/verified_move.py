"""Narrow, source-backed answers; never infer a resident's dong from a city."""
import re

LAW_URL = "https://www.easylaw.go.kr/CSP/CnpClsMain.laf?ccfNo=3&cciNo=2&cnpClsNo=1&csmSeq=629"
CONTACT_URL = "https://www.data.go.kr/data/15093649/fileData.do"
LEASE_LAW_SOURCE = "국가법령정보센터(law.go.kr) 주택임대차보호법 제3조·제3조의2 (2026-01-02 시행판)"


MOVE_WORDS = ("전입신고", "전입 신고", "이사")
PENALTY_WORDS = ("과태료", "벌금", "벌칙", "불이익")
DEPOSIT_WORDS = ("확정일자", "대항력", "우선변제")
LOAN_WORDS = ("근저당", "대출", "담보")


def answer(question: str) -> str | None:
    if any(w in question for w in DEPOSIT_WORDS):
        return _deposit_protection_answer(question)
    is_move = any(w in question for w in MOVE_WORDS)
    if not is_move or not any(w in question for w in PENALTY_WORDS):
        return None
    if "이사" in question and "신고" not in question and "전입" not in question:
        return None
    reply = (
        "정당한 사유 없이 이사 후 14일 이내에 전입신고를 하지 않으면 "
        "주민등록법 제40조 제4항에 따라 최대 5만원(5만원 이하)의 과태료가 부과됩니다. "
        "실제 부과액은 지연 기간 등에 따라 달라집니다.\n"
        f"출처: 법제처 찾기쉬운 생활법령정보 {LAW_URL}\n"
    )
    if "전화" in question or "연락처" in question:
        if "성남" in question and "정자1동" in question:
            reply += (
                "성남시 분당구 정자1동주민센터 전화는 031-729-8260입니다.\n"
                f"출처: 공공데이터포털 \"경기도 성남시_분당구홈페이지_행정복지센터 현황\"(2026-06-25 기준) {CONTACT_URL}"
            )
        else:
            reply += "담당 전화번호를 확인하려면 이사한 시·군·구와 행정동을 알려주세요."
    return reply


def _deposit_protection_answer(question: str) -> str:
    """전세·월세 보증금 보호(대항력·확정일자) — 법정 요건은 항상 이 고정 답으로 낸다.
    LLM이 '괜찮다/안전하다' 같은 확정적 안심 문구를 지어내는 것을 막는다."""
    reply = (
        "확정일자는 입주 전에도 받을 수 있습니다. 입주 시 전입신고도 신속하게 처리하세요. "
        "대항력(전입신고+입주)은 다음 날 0시부터 생기기 때문에, 집주인이 같은 날 근저당을 새로 설정하면 "
        "그 근저당이 임차인보다 먼저입니다. 당일 확정일자를 받아도 이 공백이 없어지지는 않습니다. "
        "우선변제권에는 주택 인도·전입신고와 확정일자가 모두 필요합니다.\n"
        f"출처: {LEASE_LAW_SOURCE}"
    )
    if any(w in question for w in LOAN_WORDS):
        reply += "\n잔금을 치르는 날 등기부등본을 다시 한번 확인하고, 그날 바로 전입신고와 확정일자를 함께 처리하세요."
    reply += (
        "\n구체적인 위험 여부는 등기부의 실제 권리관계를 봐야 판단할 수 있어 "
        "여기서 '안전하다/위험 없다'로 단정하지 않습니다."
    )
    return reply


def board_ops(question: str, playbook: dict | None) -> list[dict]:
    """고정답으로 답한 확정일자 질문도 보드에 절차 카드를 올린다(대화만 하고 보드가 비는 것 방지)."""
    ids = {p.get("id") for p in (playbook or {}).get("procedures", [])}
    if any(w in question for w in DEPOSIT_WORDS) and "deposit-protection" in ids:
        return [{"op": "add", "id": "deposit-protection", "status": "waiting"}]
    return []


LEASE_WORDS = ("전세", "월세", "임차", "보증금") + DEPOSIT_WORDS


def ensure_deposit_card(question: str, ops: list, playbook: dict | None) -> list:
    """확정일자 카드는 LLM의 boardOps 선택에만 맡기지 않는다(놓치면 보증금 전액이 걸림).
    질문에 임차 신호가 있고 플레이북에 절차가 있는데 LLM이 add하지 않았으면 코드로 추가한다."""
    ids = {p.get("id") for p in (playbook or {}).get("procedures", [])}
    if "deposit-protection" not in ids or not any(w in question for w in LEASE_WORDS):
        return ops
    already = any(o.get("op") == "add" and o.get("id") == "deposit-protection" for o in ops or [])
    if already:
        return ops
    return list(ops or []) + [{"op": "add", "id": "deposit-protection", "status": "waiting"}]


SOFT_WORDS = ("가까운 시일", "여유", "천천히", "나중에", "편하실 때")
SAME_DAY_SENTENCE = (
    "확정일자는 입주 전에도 받을 수 있으며, 아직 받지 않았다면 입주·전입신고 당일 함께 처리하세요. "
    "대항력은 주택 인도와 전입신고를 모두 마친 다음 날 0시부터 생깁니다. "
    "당일 확정일자를 받아도 같은 날 설정된 근저당보다 뒤에 설 수 있어요."
)


def enforce_same_day(reply: str, ops: list) -> str:
    """확정일자 카드를 올린 턴에는 '당일' 기한이 느슨하게 들리지 않도록 코드로 고정한다(temperature 0.3 실측 2/3 느슨)."""
    if not any(o.get("op") == "add" and o.get("id") == "deposit-protection" for o in ops or []):
        return reply
    sentences = re.split(r"(?<=[.!?])\s+", reply.strip())
    kept = [s for s in sentences if not ("확정일자" in s and any(w in s for w in SOFT_WORDS))]
    strong = any("확정일자" in s and ("오늘" in s or "당일" in s) for s in kept)
    out = " ".join(kept)
    return out if strong else f"{out} {SAME_DAY_SENTENCE}".strip()
