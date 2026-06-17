"""공통 절차 카탈로그 — 자주 나오는 신고/등록 절차의 '고정 grounding ref'.

predefined든 dynamic이든, 절차가 여기 매칭되면 LLM이 법령·조문을 추측하지 않고
이 카탈로그의 고정 ref로 결정론적 grounding 한다(변동 제거).
ref는 모두 국가법령정보 OPEN API 라이브로 조문·기한을 실제 확인한 값만 등록.

- crosscut=True: 여러 이벤트에 걸치는 절차. dynamic에선 '해당 시' 후보로 제시(하이브리드).
"""

from __future__ import annotations

import json
import os

COMMON: dict[str, dict] = {
    # 신고/등록 (법령 근거)
    "transfer-report": {
        "name": "전입신고", "priority": "must", "condition": "거주지를 옮긴 경우(전입 후 14일 이내).",
        "ref": {"law_query": "주민등록법", "article_title": "거주지의 이동", "expected_days": 14},
    },
    "birth-report": {
        "name": "출생신고", "priority": "must", "condition": "자녀 출생 시(출생 후 1개월 이내).",
        "ref": {"law_query": "가족관계의 등록 등에 관한 법률", "article_title": "출생신고의 기재사항", "expected_days": 30},
    },
    "death-report": {
        "name": "사망신고", "priority": "must", "condition": "가족 사망 시(사망 후 1개월 이내).",
        "ref": {"law_query": "가족관계의 등록 등에 관한 법률", "article_title": "사망신고와", "expected_days": 30},
    },
    "marriage-report": {
        "name": "혼인신고", "priority": "must", "condition": "혼인 시.",
        "ref": {"law_query": "가족관계의 등록 등에 관한 법률", "article_title": "혼인신고", "expected_days": None},
    },
    "car-address": {
        "name": "자동차 주소지 변경", "priority": "must", "condition": "차량 보유자가 주소를 옮긴 경우.",
        "ref": {"law_query": "자동차관리법", "article_title": "변경등록", "expected_days": None},
    },
    # cross-cutting (이사·퇴사·출산 등 여러 이벤트에 걸침 → 해당 시 후보)
    "health-insurance-change": {
        "name": "건강보험 자격·주소 변경", "priority": "nice",
        "condition": "거주지 또는 직장가입 자격이 바뀐 경우.", "crosscut": True,
        "ref": {"law_query": "국민건강보험법", "article_title": "자격의 변동 시기", "expected_days": 14},
    },
    "pension-change": {
        "name": "국민연금 자격·소득 변경 신고", "priority": "nice",
        "condition": "소득·가입자 자격이 바뀐 경우(퇴사·이직 등).", "crosscut": True,
        "ref": {"law_query": "국민연금법", "article_title": "가입자 자격 및 소득 등에 관한 신고", "expected_days": None},
    },
}

CROSSCUT_KEYS = [k for k, v in COMMON.items() if v.get("crosscut")]

# ---------- 자기학습 카탈로그 (LLM 제안 → 법령 API 검증 → 영속) ----------
LEARNED_PATH = os.path.join(os.path.dirname(__file__), "learned_common.json")


def _load_learned() -> dict:
    try:
        with open(LEARNED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


LEARNED: dict[str, dict] = _load_learned()


def catalog() -> dict:
    """COMMON(사람 검수 고정) + LEARNED(자동 학습) 병합. 고정이 우선."""
    return {**LEARNED, **COMMON}


def common_ref(key: str) -> dict | None:
    """공통/학습 카탈로그 절차의 법령 grounding ref."""
    e = catalog().get(key)
    return e["ref"] if e else None


def learn(key: str, name: str, ref: dict, condition: str = "", priority: str = "nice") -> None:
    """법령 API로 검증된 (절차 → 법령·조문) 매핑을 학습 카탈로그에 영속."""
    if not key or not ref:
        return
    LEARNED[key] = {"name": name, "priority": priority, "condition": condition,
                    "ref": ref, "learned": True}
    try:
        with open(LEARNED_PATH, "w", encoding="utf-8") as f:
            json.dump(LEARNED, f, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass
