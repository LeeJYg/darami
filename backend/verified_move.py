"""Narrow, source-backed answers; never infer a resident's dong from a city."""
LAW_URL = "https://www.easylaw.go.kr/CSP/CnpClsMain.laf?ccfNo=3&cciNo=2&cnpClsNo=1&csmSeq=629"
CONTACT_URL = "https://www.data.go.kr/data/15093649/fileData.do"


def answer(question: str) -> str | None:
    if "전입신고" not in question or "과태료" not in question:
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
