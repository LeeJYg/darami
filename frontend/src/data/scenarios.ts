import type { EventKey } from "../types";

export interface ScenarioPreset {
  key: EventKey;
  title: string;
  emoji: string;
  persona: string;
  blurb: string;
  /** 데모 시작 시 사용자가 보낼 첫 메시지 (실제 입력란에 프리필) */
  opener: string;
}

export const SCENARIOS: ScenarioPreset[] = [
  {
    key: "move",
    title: "이사",
    emoji: "📦",
    persona: "김도윤 · 37세 · 포항→경주",
    blurb: "2주 뒤 토요일 이사, 자녀 둘(초5·유치원), 평일 낮 방문 어려움",
    opener:
      "포항에서 경주로 2주 뒤 토요일에 이사 가요. 평일 낮에는 시간 내기 어렵고, 아이가 둘 있어요. 첫째는 초등학교 5학년, 둘째는 유치원에 다녀요. 뭘 준비해야 하나요?",
  },
  {
    key: "birth",
    title: "출산",
    emoji: "👶",
    persona: "박준호 · 31세 · 양천구 목동",
    blurb: "첫 아이 생후 5일, 출생신고와 지원금 신청, 혜택이 헷갈림",
    opener:
      "첫 아이가 5일 전에 태어났어요. 서울 양천구 목동에 살아요. 출생신고랑 받을 수 있는 지원금을 챙기고 싶은데 중앙정부, 서울시, 구청 혜택이 섞여서 헷갈려요.",
  },
  {
    key: "resignation",
    title: "퇴사",
    emoji: "💼",
    persona: "정유진 · 34세 · 분당",
    blurb: "권고사직(2주 뒤), 1인 가구, 실업급여·건강보험 걱정",
    opener:
      "회사 사정으로 2주 뒤에 권고사직하게 됐어요. 분당에 혼자 살고 3년 4개월 일했어요. 실업급여를 받을 수 있는지, 건강보험은 어떻게 되는지 걱정돼요.",
  },
];

export const SCENARIO_MAP: Record<EventKey, ScenarioPreset> = Object.fromEntries(
  SCENARIOS.map((s) => [s.key, s])
) as Record<EventKey, ScenarioPreset>;
