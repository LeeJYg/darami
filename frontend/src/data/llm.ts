import type { LlmProvider } from "../types";

/** 홈 토글에 노출할 LLM 목록. 공식 표기명을 그대로 쓴다. */
export interface LlmOption {
  key: LlmProvider;
  /** 공식 모델명 (UI 표기) */
  label: string;
  /** 제공사 — 보조 설명 */
  vendor: string;
  /** 선택 시 표시할 성능 경고(없으면 미표시). 데모용으로만 노출하는 모델에 사용. */
  note?: string;
}

export const LLM_OPTIONS: LlmOption[] = [
  { key: "solar", label: "Solar Pro", vendor: "Upstage" },
  {
    key: "kexaone",
    label: "K-EXAONE",
    vendor: "LG",
    note: "응답이 느리고 정확도가 떨어질 수 있어요 (데모용)",
  },
];

export const DEFAULT_LLM: LlmProvider = "solar";

export function llmLabel(key: LlmProvider): string {
  return LLM_OPTIONS.find((o) => o.key === key)?.label ?? key;
}

/** 선택된 모델의 성능 경고(없으면 undefined). 데모용 모델 등에 표시. */
export function llmNote(key: LlmProvider): string | undefined {
  return LLM_OPTIONS.find((o) => o.key === key)?.note;
}
