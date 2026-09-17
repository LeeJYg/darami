"""Narrow, source-backed answers; never infer a resident's dong from a city."""
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
        "전입신고와 확정일자를 '같은 날' 함께 받아야 보증금을 지킬 수 있어요. "
        "대항력(전입신고+입주)은 다음 날 0시부터 생기기 때문에, 집주인이 같은 날 근저당을 새로 설정하면 "
        "그 근저당이 임차인보다 먼저입니다. 확정일자가 늦으면 대항력이 있어도 배당 순위가 밀려요.\n"
        f"출처: {LEASE_LAW_SOURCE}"
    )
    if any(w in question for w in LOAN_WORDS):
        reply += (
            "\n잔금을 치르는 날 등기부등본을 다시 한번 확인하고, 그날 바로 전입신고와 확정일자를 함께 처리하는 것이 "
            "가장 안전합니다. 구체적인 위험 여부는 등기부의 실제 권리관계를 봐야 판단할 수 있어 "
            "여기서 '안전하다/위험 없다'로 단정하지 않습니다."
        )
    return reply
