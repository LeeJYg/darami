import type {
  ChatMessage,
  EventKey,
  LegalBasis,
  LlmProvider,
  MetaPayload,
  Playbook,
  PersonaResult,
  UserPersona,
} from "../types";
import { COMPOSITE_EVENTS } from "../data/scenarios";

/** 백엔드가 보고하는 LLM provider 가용성 */
export interface ProviderInfo {
  key: LlmProvider;
  label: string;
  available: boolean;
}

/** 선택 가능한 LLM provider 목록·가용성 조회 (키 미설정 모델은 토글에서 비활성) */
export async function getProviders(): Promise<ProviderInfo[]> {
  const res = await fetch("/api/providers");
  if (!res.ok) throw new Error(`provider 조회 실패 (${res.status})`);
  const data = (await res.json()) as { providers: ProviderInfo[] };
  return data.providers;
}

/** 대화 입력으로 사용자 페르소나 갱신 + 충돌 검사 (턴당 1차 호출) */
export async function updatePersona(
  persona: UserPersona | null,
  messages: ChatMessage[],
  provider?: LlmProvider
): Promise<PersonaResult> {
  const res = await fetch("/api/persona", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona, messages, provider }),
  });
  if (!res.ok) throw new Error(`페르소나 갱신 실패 (${res.status})`);
  return (await res.json()) as PersonaResult;
}

/** 자유 입력 생활 이벤트 → 동적 플레이북 생성 (source-first 실데이터 큐레이션) */
export async function generatePlaybook(
  description: string,
  persona?: UserPersona | null,
  provider?: LlmProvider
): Promise<Playbook> {
  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description, persona: persona ?? null, provider }),
  });
  if (!res.ok) throw new Error(`생성 실패 (${res.status})`);
  const pb = (await res.json()) as Playbook & { error?: string };
  if (pb.error) throw new Error(pb.error);
  return pb;
}

interface StreamHandlers {
  onToken: (text: string) => void;
  onMeta: (meta: MetaPayload) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

/**
 * /api/chat 으로 대화 메시지를 보내고 SSE 스트림을 파싱한다.
 * - event: token → reply 텍스트 조각 (타이핑 효과)
 * - event: meta  → 보드 갱신·빠른답변 등 구조화 데이터
 * - event: done  → 종료
 */
export async function streamChat(
  event: EventKey | null,
  messages: ChatMessage[],
  handlers: StreamHandlers,
  playbook?: Playbook | null,
  persona?: UserPersona | null,
  provider?: LlmProvider
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event,
      playbook: playbook ?? null,
      persona: persona ?? null,
      messages,
      provider,
    }),
  });

  if (!res.ok || !res.body) {
    handlers.onError(`서버 오류 (${res.status})`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE는 빈 줄(\n\n)로 이벤트가 구분된다
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let evName = "message";
      let dataStr = "";
      for (const line of lines) {
        if (line.startsWith("event:")) evName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (!dataStr) continue;
      let data: any;
      try {
        data = JSON.parse(dataStr);
      } catch {
        continue;
      }

      if (evName === "token") handlers.onToken(data.text ?? "");
      else if (evName === "meta") handlers.onMeta(data as MetaPayload);
      else if (evName === "done") handlers.onDone();
      else if (evName === "error") handlers.onError(data.message ?? "알 수 없는 오류");
    }
  }
}

export async function fetchPlaybook(event: EventKey, region?: string | null): Promise<Playbook> {
  const q = region ? `?region=${encodeURIComponent(region)}` : "";
  // 복합 이벤트(출산 후 이사 등)는 재료 이벤트를 합쳐 한 보드로 주는 compose 라우트를 쓴다
  const path = COMPOSITE_EVENTS.includes(event)
    ? `/api/playbook/compose/${event}`
    : `/api/playbook/${event}`;
  const res = await fetch(`${path}${q}`);
  if (!res.ok) throw new Error(`플레이북 조회 실패 (${res.status})`);
  return (await res.json()) as Playbook;
}

/** 절차의 법적 근거를 국가법령정보 API로 실시간 조회 */
export async function fetchLegalBasis(procedureId: string): Promise<LegalBasis> {
  try {
    const res = await fetch(`/api/legal-basis/${encodeURIComponent(procedureId)}`);
    if (!res.ok) return { supported: false };
    return (await res.json()) as LegalBasis;
  } catch {
    return { supported: false };
  }
}
