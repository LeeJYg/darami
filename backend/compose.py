"""복합 생활 이벤트 — 여러 이벤트의 플레이북을 '하나의 보드'로 합친다.

보고서가 문제로 든 예시("출산 후 이사")처럼 생활 이벤트는 겹쳐서 온다.
기존 구조는 이벤트 하나당 보드 하나라, 사용자가 두 번 처음부터 시작해야 했다.
여기서는 절차를 id 로 합치고(중복 제거), 기한이 급한 순으로 정렬해 한 보드로 만든다.
"""

from __future__ import annotations

COMPOSITES: dict[str, dict] = {
    # key: 합성 이벤트 슬러그 → 재료 이벤트와 표기
    "birth-move": {
        "events": ["birth", "move"],
        "title": "출산 후 이사",
        "emoji": "👶📦",
        "intro": "출산과 이사가 겹쳤어요. 두 이벤트의 절차를 한 보드에 모아 기한이 급한 순으로 정리했어요.",
    },
}


def merge_playbooks(slug: str, parts: list[dict]) -> dict:
    """여러 플레이북을 하나로 합친다. 같은 id 절차는 한 번만 남기고 출처 이벤트를 모두 기록한다."""
    meta = COMPOSITES.get(slug, {})
    merged: dict[str, dict] = {}
    for pb in parts:
        ev = pb.get("event")
        for p in pb.get("procedures", []):
            pid = p.get("id")
            if not pid:
                continue
            if pid in merged:
                # 두 이벤트에 모두 걸리는 절차(예: 전입신고·건강보험 변경)는 중복 카드로 만들지 않는다
                fe = merged[pid].setdefault("fromEvents", [])
                if ev and ev not in fe:
                    fe.append(ev)
                continue
            item = dict(p)
            item["fromEvents"] = [ev] if ev else []
            merged[pid] = item

    def _days(p: dict) -> int:
        d = p.get("deadlineDays")
        return d if isinstance(d, int) else 9999

    procedures = sorted(merged.values(), key=lambda p: (_days(p), p.get("priority") != "must"))
    return {
        "event": slug,
        "title": meta.get("title") or " + ".join(pb.get("title", "") for pb in parts),
        "emoji": meta.get("emoji", "🌰"),
        "intro": meta.get("intro", ""),
        "composedOf": [pb.get("event") for pb in parts],
        "procedures": procedures,
    }
