"""부스 시연용 오프라인 모드.

DARAMI_DEMO_MODE=1 이면 LLM 호출 대신 backend/demo_script.json 의 고정 대본으로 응답한다.
- 부스 노트북에서 망이 막히거나 키가 없어도 종단 동선(프론트→API→보드)이 그대로 돈다.
- 대본도 제품과 같은 가드(guard.sanitize_reply)를 통과하므로, 금액·연락처 규칙은 동일하게 적용된다.
- 화면에는 오프라인 모드임을 표시한다(/api/health, /api/providers 의 demoMode).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# 기본은 제품 대본. 평가 하네스는 DARAMI_DEMO_SCRIPT 로 다른 대본을 물려
# 제품 대본을 건드리지 않고 같은 라우트를 재생할 수 있다(work/eval/live_replay_all_events.py).
SCRIPT_PATH = Path(os.environ.get("DARAMI_DEMO_SCRIPT") or (Path(__file__).parent / "demo_script.json"))


def enabled() -> bool:
    return os.environ.get("DARAMI_DEMO_MODE") == "1"


def _script() -> dict:
    if not SCRIPT_PATH.exists():
        return {}
    return json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))


def chat_turn(event: str | None, messages: list) -> dict:
    """사용자 발화 수(턴 인덱스)로 대본을 고른다. 대본이 없으면 빈 보드 + 사유를 돌려준다."""
    script = _script()
    turns = (script.get(event or "", {}) or {}).get("turns", [])
    idx = max(0, sum(1 for m in messages if getattr(m, "role", None) == "user") - 1)
    if not turns:
        return {
            "reply": "오프라인 시연 대본에 이 이벤트가 없어요. 담당자에게 알려주세요.",
            "eventDetected": event, "askMissing": [], "quickReplies": [], "boardOps": [], "userTodos": [],
        }
    turn = turns[min(idx, len(turns) - 1)]
    return {
        "reply": turn.get("reply", ""),
        "eventDetected": turn.get("eventDetected", event),
        "askMissing": turn.get("askMissing", []),
        "quickReplies": turn.get("quickReplies", []),
        "boardOps": turn.get("boardOps", []),
        "userTodos": turn.get("userTodos", []),
    }


def persona_turn(event: str | None, prior_facts: dict, messages: list) -> dict:
    """대본의 facts 를 누적해 돌려준다(충돌 검사는 하지 않는다)."""
    script = _script()
    turns = (script.get(event or "", {}) or {}).get("turns", [])
    idx = max(0, sum(1 for m in messages if getattr(m, "role", None) == "user") - 1)
    facts = dict(prior_facts or {})
    for t in turns[: idx + 1]:
        facts.update(t.get("facts", {}))
    return {"facts": facts, "conflict": None}
