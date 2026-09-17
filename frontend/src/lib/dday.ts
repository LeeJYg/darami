import type { EventKey, Procedure, UserPersona } from "../types";

/** 이벤트별 기본 기준일(anchor) key. 절차에 anchor가 따로 없으면 이걸 쓴다. */
const DEFAULT_ANCHOR: Record<string, string> = {
  move: "move_date",
  birth: "birth_date",
  resignation: "resignation_date",
};

/** "YYYY-MM-DD"(앞부분) → 로컬 자정 Date. 형식이 아니면 null. */
function parseISO(v: unknown): Date | null {
  if (typeof v !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v.trim());
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return isNaN(d.getTime()) ? null : d;
}

function startOfToday(): Date {
  const t = new Date();
  return new Date(t.getFullYear(), t.getMonth(), t.getDate());
}

/**
 * 기준일(사건일) + 법정기간 → 오늘 기준 실제 남은 일수.
 * 기준일을 페르소나에서 못 찾으면 null → 호출부는 기존 deadlineDays(법정기간)로 폴백.
 *   D-day = (기준일 + 법정기간) − 오늘
 *   예) 출생일 5일 전 + 30일 = D-25,  이사일 14일 뒤 + 14일 = D-28
 */
export function computeDday(
  p: Procedure,
  persona: UserPersona | null,
  event: EventKey | null
): number | null {
  const win = p.deadlineDays;
  if (typeof win !== "number" || win < 0 || win >= 3650) return null; // 0은 당일 기한, 음수·기간 미상 항목 제외
  const facts = persona?.facts;
  if (!facts) return null;
  // 복합 이벤트(birth-move 등)는 이벤트 자체의 기준일이 없으므로, 절차가 온 원래 이벤트의 기준일을 쓴다.
  //   예) 출산 후 이사: 출생신고 → birth_date, 전입신고 → move_date
  const origin = (p.fromEvents || []).map((e) => DEFAULT_ANCHOR[e]).find(Boolean);
  const key = p.anchor || (event ? DEFAULT_ANCHOR[event] : undefined) || origin || "event_date";
  const anchor = parseISO(facts[key]);
  if (!anchor) return null;
  const deadline = new Date(anchor);
  deadline.setDate(deadline.getDate() + win);
  return Math.round((deadline.getTime() - startOfToday().getTime()) / 86400000);
}

/** 표시에 쓸 실효 D-day(기준일 알면 환산값, 모르면 법정기간 그대로). */
export function effectiveDday(
  p: Procedure,
  persona: UserPersona | null,
  event: EventKey | null
): number {
  return computeDday(p, persona, event) ?? p.deadlineDays;
}

/** D-day 뱃지 문구. 양수=D-N, 0=D-day, 음수=기한 지남. */
export function ddayLabel(days: number): string {
  if (days > 0) return `D-${days}`;
  if (days === 0) return "D-day";
  return `기한 지남 (D+${Math.abs(days)})`;
}
