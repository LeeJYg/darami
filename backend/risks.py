"""절차를 놓쳤을 때 실제로 생기는 손해 — 'risk' 한 곳에서만 관리한다.

왜 있나: 지금까지 보드는 '무엇을 언제까지' 만 보여 줬다. 기한이 급하다는 것은 D-day 로
알 수 있지만 **왜 급한지**(놓치면 무슨 손해인지)는 사용자가 따로 물어야만 나왔다.
멘토 지적(work/MENTOR-REVIEW-20260917.md M1 '미흡')이 정확히 이 지점이다.

원칙 — 금액 환각 가드(backend/guard.py)와 같다. **출처로 확인된 값만 숫자로 쓴다.**
  amount_verified=True  : 저장소 안에 근거가 있는 것만. 지금은 두 건이다.
      - transfer-report  주민등록법 제40조 제4항 5만원  (backend/verified_move.py:25 의
                         고정답과 같은 근거·같은 URL)
      - deposit-protection  주택임대차보호법 제3조·제3조의2 (금액이 아니라 법정 효력)
  amount_verified=False : 손해의 '종류'만 적고 금액은 쓰지 않는다. 화면에도
                         "금액 미검증 — 숫자는 표시하지 않음" 배지가 붙는다.
LAW_OC(국가법령정보 OPEN API) 키가 붙으면 이 표의 금액을 조문으로 교차검증해
amount_verified 를 올리는 것이 다음 단계다.

적용 지점(세 경로 모두):
  - main.load_playbook        정적 플레이북 3종
  - curate._enrich            큐레이션된 플레이북
  - curate._proc_from_common  자유 입력(dynamic) 이벤트의 공통 카탈로그 절차
"""

from __future__ import annotations

# 주민등록법 과태료 근거 — verified_move.LAW_URL 과 같은 문서.
_JUMIN_LAW_URL = (
    "https://www.easylaw.go.kr/CSP/CnpClsMain.laf"
    "?ccfNo=3&cciNo=2&cnpClsNo=1&csmSeq=629"
)

RISKS: dict[str, dict] = {
    "transfer-report": {
        "kind": "과태료",
        "label": "과태료 최대 5만원",
        "detail": "정당한 사유 없이 전입 후 14일 안에 신고하지 않으면 5만원 이하의 "
                  "과태료가 부과됩니다. 실제 부과액은 지연 기간에 따라 달라져요.",
        "basis": "주민등록법 제40조 제4항",
        "url": _JUMIN_LAW_URL,
        "amountVerified": True,
    },
    "deposit-protection": {
        "kind": "보증금",
        "label": "보증금이 근저당보다 뒤로 밀림 · 되돌릴 수 없음",
        "detail": "대항력은 주택 인도와 전입신고를 모두 마친 다음 날 0시에 생깁니다. "
                  "잔금 당일에 집주인이 근저당을 설정하면 그 근저당이 앞순위가 되고, "
                  "경매로 넘어가면 보증금이 후순위가 됩니다. 이 순위는 나중에 되돌릴 수 없어요.",
        "basis": "주택임대차보호법 제3조·제3조의2",
        "amountVerified": True,
    },
    "birth-report": {
        "kind": "과태료",
        "label": "기한을 넘기면 과태료",
        "detail": "출생 후 1개월 안에 신고하지 않으면 과태료가 부과되고 지연 기간이 길수록 "
                  "올라갑니다. 금액은 아직 법령 원문으로 자동 확인하지 못해 숫자로 적지 않습니다.",
        "basis": "가족관계의 등록 등에 관한 법률 제122조",
        "amountVerified": False,
    },
    "car-address": {
        "kind": "과태료",
        "label": "기한을 넘기면 과태료",
        "detail": "주소가 바뀐 뒤 기한 안에 변경 등록을 하지 않으면 과태료가 부과됩니다. "
                  "지연 일수에 따라 금액이 달라지고, 아직 법령 원문으로 자동 확인하지 못해 "
                  "숫자로 적지 않습니다.",
        "basis": "자동차관리법 제12조·제84조",
        "amountVerified": False,
    },
    "first-meet": {
        "kind": "지원금",
        "label": "늦으면 바우처를 쓸 수 있는 기간이 줄어듦",
        "detail": "사용 기한이 출생일을 기준으로 정해져 있어, 신청이 늦어진 만큼 쓸 수 있는 "
                  "기간이 줄어듭니다. 신청하지 않으면 자동으로 지급되지 않아요.",
        "basis": "보조금24 · 첫만남이용권 안내",
        "amountVerified": False,
    },
    "child-allowance": {
        "kind": "지원금",
        "label": "늦게 신청하면 지난 달치는 소급되지 않음",
        "detail": "출생 후 일정 기간 안에 신청하면 출생월부터 소급해 주지만, 그 기간을 넘기면 "
                  "신청한 달부터만 받습니다. 놓친 달은 되돌려 받을 수 없어요.",
        "basis": "보조금24 · 아동수당 안내",
        "amountVerified": False,
    },
    "parent-allowance": {
        "kind": "지원금",
        "label": "늦게 신청하면 지난 달치는 소급되지 않음",
        "detail": "출생 후 일정 기간 안에 신청하면 출생월부터 소급해 주지만, 그 기간을 넘기면 "
                  "신청한 달부터만 받습니다. 놓친 달은 되돌려 받을 수 없어요.",
        "basis": "보조금24 · 부모급여 안내",
        "amountVerified": False,
    },
    "unemployment-benefit": {
        "kind": "수급권",
        "label": "기한이 지나면 남은 일수가 있어도 못 받음",
        "detail": "퇴사 다음 날부터 12개월이 지나면 소정급여일수가 남아 있어도 지급이 끝납니다. "
                  "늦게 신청할수록 실제로 받는 일수가 줄어요.",
        "basis": "고용보험법 제48조(수급기간)",
        "amountVerified": False,
    },
    "death-report": {
        "kind": "과태료",
        "label": "기한을 넘기면 과태료",
        "detail": "사망 후 1개월 안에 신고하지 않으면 과태료가 부과됩니다. 금액은 아직 법령 "
                  "원문으로 자동 확인하지 못해 숫자로 적지 않습니다.",
        "basis": "가족관계의 등록 등에 관한 법률 제122조",
        "amountVerified": False,
    },
}


def attach(proc: dict) -> dict:
    """절차 dict 에 risk 를 붙여 돌려준다(이미 있으면 그대로 둔다). 원본을 바꾸지 않는다."""
    pid = proc.get("id")
    if not pid or "risk" in proc or pid not in RISKS:
        return proc
    out = dict(proc)
    out["risk"] = dict(RISKS[pid])
    return out


def attach_all(playbook: dict) -> dict:
    """플레이북의 모든 절차에 risk 를 붙인다."""
    if not isinstance(playbook, dict) or not playbook.get("procedures"):
        return playbook
    out = dict(playbook)
    out["procedures"] = [attach(p) for p in playbook["procedures"]]
    return out


def grounded_amounts() -> list[str]:
    """guard 의 근거 문자열에 합칠, 검증된 금액 표현들.
    (검증되지 않은 금액은 여기 없으므로 가드는 그대로 막는다.)"""
    return [r["label"] for r in RISKS.values() if r.get("amountVerified")]
