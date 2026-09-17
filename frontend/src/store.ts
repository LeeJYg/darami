import { create } from "zustand";
import type {
  BoardItem,
  BoardOp,
  ChatMessage,
  DynamicEntry,
  EventKey,
  LlmProvider,
  Playbook,
  Procedure,
  StoredSession,
  UserPersona,
  UserTodo,
} from "./types";
import {
  fetchPlaybook,
  generatePlaybook,
  streamChat,
  updatePersona,
} from "./api/chat";
import { SCENARIO_MAP, COMPOSITE_EVENTS } from "./data/scenarios";
import { DEFAULT_LLM } from "./data/llm";

type Tab = "chat" | "board";

const LLM_KEY = "darami.llm"; // 선택한 응답 LLM(provider) 영속

function loadLlm(): LlmProvider {
  const v = localStorage.getItem(LLM_KEY);
  return v === "solar" || v === "kexaone" ? v : DEFAULT_LLM;
}

const DYN_KEY = "darami.dynamicEvents.v2"; // v2: 동적 grounding 전환으로 옛 미검증 캐시 무효화
const SESS_KEY = "darami.sessions.v2"; // v2: 큐레이션 grounding 전환으로 옛 보드 캐시 무효화

function loadDynamic(): DynamicEntry[] {
  try {
    return JSON.parse(localStorage.getItem(DYN_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveDynamic(list: DynamicEntry[]) {
  try {
    localStorage.setItem(DYN_KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

// 시도 약칭 → 보조금24 소관기관명 접두(거주지 문자열에서 지역 추출)
const SIDO: [string, string][] = [
  ["서울", "서울특별시"], ["부산", "부산광역시"], ["대구", "대구광역시"], ["인천", "인천광역시"],
  ["광주", "광주광역시"], ["대전", "대전광역시"], ["울산", "울산광역시"], ["세종", "세종특별자치시"],
  ["경기", "경기도"], ["강원", "강원"], ["충북", "충청북도"], ["충남", "충청남도"],
  ["전북", "전북"], ["전남", "전라남도"], ["경북", "경상북도"], ["경남", "경상남도"], ["제주", "제주"],
];

/** 페르소나 facts에서 거주 시도를 추출 (예: "서울 양천구 목동" → "서울특별시") */
function deriveRegion(facts: Record<string, string | number | boolean> | undefined): string | null {
  if (!facts) return null;
  const blob = Object.values(facts)
    .filter((v) => typeof v === "string")
    .join(" ");
  for (const [short, canonical] of SIDO) {
    if (blob.includes(short)) return canonical;
  }
  return null;
}

function loadSessions(): Record<string, StoredSession> {
  try {
    return JSON.parse(localStorage.getItem(SESS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveSessions(map: Record<string, StoredSession>) {
  try {
    localStorage.setItem(SESS_KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

interface State {
  started: boolean;
  event: EventKey | null;
  playbook: Playbook | null;
  procIndex: Record<string, Procedure>;

  messages: ChatMessage[];
  streaming: boolean;
  quickReplies: string[];
  error: string | null;
  persona: UserPersona | null;
  conflictPending: boolean;
  appliedRegion: string | null; // 플레이북에 반영된 거주 지역(시도)

  board: BoardItem[];
  /** 보드가 비어 있는 '이유'. null이면 정상(아직 대화 전이거나 절차가 담겼다) */
  boardError: string | null;
  userTodos: UserTodo[];
  openTodoId: string | null;
  tab: Tab;
  openProcId: string | null;

  // 동적 이벤트
  dynamicEvents: DynamicEntry[];
  generating: boolean;
  genError: string | null;

  // 이벤트별 대화 세션 (영속)
  sessions: Record<string, StoredSession>;

  // 응답 LLM (영속) — "solar"(Solar Pro) | "kexaone"(K-EXAONE)
  llm: LlmProvider;

  // actions
  setLlm: (key: LlmProvider) => void;
  startScenario: (key: EventKey) => Promise<void>;
  enterEvent: (event: EventKey, playbook: Playbook, opener: string) => Promise<void>;
  generateAndStart: (description: string) => Promise<void>;
  startDynamic: (key: string) => Promise<void>;
  removeDynamic: (key: string) => void;
  clearSession: (key: string) => void;
  persistCurrent: () => void;
  send: (text: string) => Promise<void>;
  setTab: (t: Tab) => void;
  openProc: (id: string | null) => void;
  toggleDone: (id: string) => void;
  // User defined 할 일
  addUserTodo: (title: string) => void;
  toggleUserTodo: (id: string) => void;
  removeUserTodo: (id: string) => void;
  openTodo: (id: string | null) => void;
  updateTodoNote: (id: string, note: string) => void;
  reset: () => void;
}

/** 플레이북에 없는 사용자 추가 절차(boardOp.procedure)를 완전한 Procedure로 정규화 */
function procFromOp(op: BoardOp): Procedure | null {
  const p = op.procedure;
  if (!p) return null;
  return {
    id: op.id,
    name: p.name || "직접 추가한 할 일",
    priority: p.priority === "must" || p.priority === "qna" ? p.priority : "nice",
    deadline: p.deadline || "",
    deadlineDays: typeof p.deadlineDays === "number" ? p.deadlineDays : 9999,
    agency: p.agency || "",
    online: Boolean(p.online),
    documents: p.documents || [],
    link: p.link || "",
    source: p.source || { name: "사용자 추가", tier: "reference", checkedAt: "" },
    condition: p.condition || "",
    summary: p.summary || "",
  };
}

/**
 * 모델은 보드 상태를 모른 채 "필요한 절차 N가지를 '할 일'에 담아뒀어요"라고 쓴다.
 * 복합 이벤트처럼 보드가 미리 채워져 있으면 N이 화면과 어긋나므로(실측: "2가지" vs 보드 7장) 실제 개수로 맞춘다.
 */
const COUNT_CLAIM = /(필요한\s*)?절차\s*(\d+)\s*가지를\s*['‘"]?할\s*일['’"]?에\s*담아\s*(뒀|두었|놓았|놨)어요/;
export function fixBoardCountClaim(messages: ChatMessage[], boardCount: number): ChatMessage[] {
  const last = messages[messages.length - 1];
  const m = last?.role === "assistant" ? COUNT_CLAIM.exec(last.content) : null;
  if (!m || Number(m[2]) === boardCount) return messages;
  const fixed = last.content.replace(COUNT_CLAIM, `필요한 절차 ${boardCount}가지를 '할 일'에 정리해뒀어요`);
  return [...messages.slice(0, -1), { ...last, content: fixed }];
}

function applyBoardOps(board: BoardItem[], ops: BoardOp[]): BoardItem[] {
  const map = new Map(board.map((b) => [b.id, { ...b }]));
  for (const op of ops) {
    if (!op?.id) continue;
    const existing = map.get(op.id);
    if (existing) {
      if (op.status) existing.status = op.status;
    } else {
      // add(또는 모르는 id의 update)는 새 항목으로 보드에 올린다
      map.set(op.id, { id: op.id, status: op.status ?? "waiting" });
    }
  }
  return Array.from(map.values());
}

export const useStore = create<State>((set, get) => ({
  started: false,
  event: null,
  playbook: null,
  procIndex: {},
  messages: [],
  streaming: false,
  quickReplies: [],
  error: null,
  persona: null,
  conflictPending: false,
  appliedRegion: null,
  board: [],
  boardError: null,
  userTodos: [],
  openTodoId: null,
  tab: "chat",
  openProcId: null,
  dynamicEvents: loadDynamic(),
  generating: false,
  genError: null,
  sessions: loadSessions(),
  llm: loadLlm(),

  setLlm: (key) => {
    try {
      localStorage.setItem(LLM_KEY, key);
    } catch {
      /* ignore */
    }
    set({ llm: key });
  },

  // 현재 이벤트의 대화 상태를 세션에 저장
  persistCurrent: () => {
    const { event, messages, board, quickReplies, persona, procIndex, playbook, userTodos, sessions } = get();
    if (!event) return;
    const kept = messages.filter((m) => m.content.length > 0);
    if (kept.length === 0 && userTodos.length === 0) return;
    // 플레이북에 없던 사용자 추가 절차만 따로 저장(복원용)
    const playbookIds = new Set((playbook?.procedures ?? []).map((p) => p.id));
    const procExtras = Object.values(procIndex).filter((p) => !playbookIds.has(p.id));
    const next = {
      ...sessions,
      [event]: {
        messages: kept,
        board,
        quickReplies,
        persona: persona ?? undefined,
        procExtras: procExtras.length > 0 ? procExtras : undefined,
        userTodos: userTodos.length > 0 ? userTodos : undefined,
        updatedAt: Date.now(),
      },
    };
    saveSessions(next);
    set({ sessions: next });
  },

  // 이벤트 진입: 저장된 세션이 있으면 복원, 없으면 새로 시작(opener 전송)
  enterEvent: async (event, playbook, opener) => {
    const procIndex = Object.fromEntries(
      playbook.procedures.map((p) => [p.id, p])
    );
    const sess = get().sessions[event];
    if (sess && sess.messages.length > 0) {
      // 이전 대화 복원 (페르소나 + 사용자 추가 절차 포함)
      const mergedIndex = { ...procIndex };
      for (const p of sess.procExtras ?? []) mergedIndex[p.id] = p;
      set({
        started: true,
        event,
        playbook,
        procIndex: mergedIndex,
        messages: sess.messages,
        board: sess.board,
        quickReplies: sess.quickReplies,
        persona: sess.persona ?? { event, facts: {} },
        conflictPending: false,
        userTodos: sess.userTodos ?? [],
        openTodoId: null,
        appliedRegion: null,
        error: null,
        streaming: false,
        tab: "chat",
      });
      return;
    }
    // 새 대화 — 빈 페르소나로 시작
    // 복합 이벤트(예: 출산 후 이사)는 LLM이 이번 대화에서 무엇을 add 하느냐에 따라
    // 보드 카드 수가 매번 달라진다(부스 시연에서 카드 5장→2장으로 흔들리는 원인).
    // 이미 서버가 병합·정렬해 준 필수(must) 절차는 대화 없이도 확정된 사실이므로
    // 첫 화면부터 채워 두고, LLM은 그 위에 추가·상태 변경만 한다.
    const prefill: BoardItem[] = COMPOSITE_EVENTS.includes(event)
      ? playbook.procedures
          .filter((p) => p.priority === "must")
          .map((p) => ({ id: p.id, status: "waiting" as const }))
      : [];
    set({
      started: true,
      event,
      playbook,
      procIndex,
      messages: [],
      board: prefill,
      // 플레이북 자체가 비면 대화를 해도 보드에 담길 절차가 없다 → 이유를 바로 화면에 띄운다
      boardError:
        playbook.procedures.length === 0
          ? "플레이북을 불러오지 못했어요 (절차 0건). 백엔드 /api/playbook 응답과 법령·복지 API 키 설정을 확인해 주세요."
          : null,
      quickReplies: [],
      persona: { event, facts: {} },
      conflictPending: false,
      userTodos: [],
      openTodoId: null,
      appliedRegion: null,
      error: null,
      tab: "chat",
    });
    await get().send(opener);
  },

  startScenario: async (key) => {
    let playbook: Playbook;
    try {
      playbook = await fetchPlaybook(key);
    } catch (e) {
      // 플레이북을 못 받아도 화면을 열고 '이유'를 보여준다(빈 화면으로 두지 않는다)
      playbook = {
        event: key,
        title: SCENARIO_MAP[key]?.title ?? "",
        emoji: SCENARIO_MAP[key]?.emoji ?? "🌰",
        intro: "",
        procedures: [],
      };
      await get().enterEvent(key, playbook, SCENARIO_MAP[key].opener);
      set({ boardError: `플레이북을 불러오지 못했어요 — ${e instanceof Error ? e.message : e}` });
      return;
    }
    await get().enterEvent(key, playbook, SCENARIO_MAP[key].opener);
  },

  clearSession: (key) => {
    const sessions = { ...get().sessions };
    delete sessions[key];
    saveSessions(sessions);
    // 현재 보고 있는 이벤트라면 라이브 상태도 비운다
    const patch: Partial<State> = { sessions };
    if (get().event === key) {
      patch.messages = [];
      patch.board = [];
      patch.boardError = null;
      patch.userTodos = [];
      patch.openTodoId = null;
      patch.quickReplies = [];
      patch.persona = { event: key, facts: {} };
      patch.conflictPending = false;
    }
    set(patch);
  },

  // 자유 입력 → 동적 플레이북 생성 후 홈에 누적하고 바로 시작
  generateAndStart: async (description) => {
    const desc = description.trim();
    if (!desc || get().generating) return;
    set({ generating: true, genError: null });
    try {
      const playbook = await generatePlaybook(desc, get().persona, get().llm);
      if (!playbook.procedures || playbook.procedures.length === 0) {
        set({
          generating: false,
          genError:
            "이 이벤트에 대한 행정 절차를 찾지 못했어요. 조금 더 구체적으로 적어 주세요.",
        });
        return;
      }
      const key = `dyn_${Date.now()}`;
      const entry: DynamicEntry = {
        key,
        title: playbook.title || "내 생활 이벤트",
        emoji: playbook.emoji || "🌰",
        blurb: desc.length > 42 ? desc.slice(0, 42) + "…" : desc,
        opener: desc,
        playbook,
      };
      const list = [...get().dynamicEvents, entry];
      saveDynamic(list);
      set({ dynamicEvents: list, generating: false });
      await get().enterEvent(key, playbook, desc);
    } catch (e) {
      set({
        generating: false,
        genError: e instanceof Error ? e.message : "생성 중 오류가 발생했어요.",
      });
    }
  },

  startDynamic: async (key) => {
    const entry = get().dynamicEvents.find((d) => d.key === key);
    if (!entry) return;
    await get().enterEvent(entry.key, entry.playbook, entry.opener);
  },

  removeDynamic: (key) => {
    const list = get().dynamicEvents.filter((d) => d.key !== key);
    saveDynamic(list);
    // 동적 이벤트를 지우면 세션도 함께 정리
    const sessions = { ...get().sessions };
    delete sessions[key];
    saveSessions(sessions);
    set({ dynamicEvents: list, sessions });
  },

  send: async (text) => {
    const trimmed = text.trim();
    if (!trimmed || get().streaming) return;

    const userMsg: ChatMessage = { role: "user", content: trimmed };
    // 사용자 메시지 + 빈 assistant 메시지(타이핑 표시) 추가
    set((s) => ({
      messages: [...s.messages, userMsg, { role: "assistant", content: "" }],
      streaming: true,
      quickReplies: [],
      error: null,
      boardError: null,
    }));

    const history = get().messages.filter((m) => m.content.length > 0);

    // ① 페르소나 갱신 + 충돌 검사 (1차 호출)
    let personaFacts = get().persona?.facts ?? {};
    try {
      const pr = await updatePersona(get().persona, history, get().llm);
      // 비충돌 facts는 conflict 여부와 무관하게 항상 커밋한다.
      // (conflict일 때 facts를 통째로 버리면 확정값이 영영 저장되지 않아 같은 질문이 무한 반복됨)
      if (pr.facts) personaFacts = pr.facts;

      // conflict는 '한 턴'만 대화를 막을 수 있다. 직전 턴에 이미 같은 확인을 띄웠다면(conflictPending)
      // 사용자의 답을 확정으로 보고 그대로 진행한다 → 모델이 무엇을 하든 무한 루프 차단(결정론적 안전장치).
      if (pr.conflict && pr.conflict.question && !get().conflictPending) {
        const pendingPersona: UserPersona = { event: get().event ?? undefined, facts: personaFacts };
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") last.content = pr.conflict!.question;
          return {
            messages: msgs,
            quickReplies: pr.conflict!.options ?? [],
            streaming: false,
            persona: pendingPersona, // 비충돌 facts는 저장(disputed key만 다음 답으로 확정)
            conflictPending: true,
          };
        });
        get().persistCurrent();
        return;
      }
    } catch {
      // 페르소나 호출 실패 시 기존 페르소나로 계속 진행
    }
    // 진행(충돌 해소 또는 없음) → pending 해제하고 갱신된 페르소나 반영
    const nextPersona: UserPersona = { event: get().event ?? undefined, facts: personaFacts };
    set({ persona: nextPersona, conflictPending: false });

    // 거주지가 파악되면 지자체/광역 혜택까지 포함해 플레이북을 재큐레이션(on-demand)
    const region = deriveRegion(personaFacts);
    const ev = get().event;
    if (region && ev && region !== get().appliedRegion) {
      try {
        const rpb = await fetchPlaybook(ev, region);
        if (rpb?.procedures?.length) {
          const procIndex = Object.fromEntries(rpb.procedures.map((p) => [p.id, p]));
          set({ playbook: rpb, procIndex, appliedRegion: region });
        }
      } catch {
        /* 지역 재큐레이션 실패 시 기존 플레이북 유지 */
      }
    }

    // ② 대화 생성 (갱신된 페르소나 주입, 2차 호출 — 스트리밍)
    await streamChat(get().event, history, {
      onToken: (t) =>
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") last.content += t;
          return { messages: msgs };
        }),
      onMeta: (meta) =>
        set((s) => {
          const ops = meta.boardOps ?? [];
          const prevIds = new Set(s.board.map((b) => b.id));
          const board = applyBoardOps(s.board, ops);
          // 플레이북에 없는 사용자 추가 절차 상세를 procIndex에 병합
          let procIndex = s.procIndex;
          const extras = ops.map(procFromOp).filter((p): p is Procedure => Boolean(p));
          if (extras.length > 0) {
            procIndex = { ...s.procIndex };
            // 이미 grounding된 절차는 LLM이 임베드한 추측 데이터로 덮어쓰지 않는다(환각 방지)
            for (const p of extras) if (!procIndex[p.id]) procIndex[p.id] = p;
          }
          // 이번 턴에 '새로' 추가된 절차만 골라(결정론적) 이름을 모은다
          const addedNames = ops
            .filter((o) => o.op === "add" && !prevIds.has(o.id))
            .map((o) => procIndex[o.id]?.name)
            .filter((n): n is string => Boolean(n));
          // 사용자가 직접 추가 요청한 할 일 → User defined 섹션(중복 제목 제외)
          const existingTitles = new Set(s.userTodos.map((t) => t.title));
          const newTodos = (meta.userTodos ?? [])
            .filter((t) => t && !existingTitles.has(t))
            .map((t, i) => ({ id: `ut_${Date.now()}_${i}`, title: t, note: "", done: false }));
          const userTodos = newTodos.length ? [...s.userTodos, ...newTodos] : s.userTodos;
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant" && addedNames.length > 0) {
            last.added = { count: addedNames.length, names: addedNames };
          }
          return { board, procIndex, userTodos, quickReplies: meta.quickReplies ?? [], messages: msgs };
        }),
      onDone: () => {
        // 응답이 끝났는데 보드가 여전히 비어 있으면 '조용한 빈 화면' 대신 이유를 남긴다.
        set((s) => {
          if (s.board.length > 0 || s.userTodos.length > 0) {
            return { streaming: false, boardError: null, messages: fixBoardCountClaim(s.messages, s.board.length) };
          }
          const n = s.playbook?.procedures.length ?? 0;
          const waiting = (s.quickReplies?.length ?? 0) > 0;
          return {
            streaming: false,
            boardError: waiting
              ? null // 되묻는 턴이라 아직 담을 절차가 없는 정상 상태
              : `응답은 왔지만 보드에 담긴 절차가 없어요. 모델이 절차 id를 돌려주지 않았을 수 있어요 (플레이북 절차 ${n}건). 같은 질문을 한 번 더 보내거나 시나리오를 다시 시작해 주세요.`,
          };
        });
        get().persistCurrent(); // 응답 완료 시 세션 저장
      },
      onError: (message) =>
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant" && !last.content) msgs.pop();
          return {
            streaming: false,
            error: message,
            boardError: s.board.length === 0 ? `절차를 불러오지 못했어요 — ${message}` : s.boardError,
            messages: msgs,
          };
        }),
    },
    // 현재 플레이북 + 페르소나 + 선택한 LLM을 함께 보낸다
    get().playbook,
    nextPersona,
    get().llm);
  },

  setTab: (t) => set({ tab: t }),
  openProc: (id) => set({ openProcId: id }),
  toggleDone: (id) => {
    set((s) => ({
      board: s.board.map((b) =>
        b.id === id
          ? { ...b, status: b.status === "done" ? "waiting" : "done" }
          : b
      ),
    }));
    get().persistCurrent(); // 체크 상태도 세션에 반영
  },

  // ---- User defined 할 일 ----
  addUserTodo: (title) => {
    const t = title.trim();
    if (!t) return;
    set((s) => ({
      userTodos: [...s.userTodos, { id: `ut_${Date.now()}`, title: t, note: "", done: false }],
    }));
    get().persistCurrent();
  },
  toggleUserTodo: (id) => {
    set((s) => ({
      userTodos: s.userTodos.map((t) => (t.id === id ? { ...t, done: !t.done } : t)),
    }));
    get().persistCurrent();
  },
  removeUserTodo: (id) => {
    set((s) => ({
      userTodos: s.userTodos.filter((t) => t.id !== id),
      openTodoId: s.openTodoId === id ? null : s.openTodoId,
    }));
    get().persistCurrent();
  },
  openTodo: (id) => set({ openTodoId: id }),
  updateTodoNote: (id, note) => {
    set((s) => ({
      userTodos: s.userTodos.map((t) => (t.id === id ? { ...t, note } : t)),
    }));
    get().persistCurrent();
  },

  reset: () => {
    get().persistCurrent(); // 홈으로 나가기 전에 현재 세션 저장
    set({
      started: false,
      event: null,
      playbook: null,
      procIndex: {},
      messages: [],
      board: [],
      boardError: null,
      userTodos: [],
      openTodoId: null,
      quickReplies: [],
      persona: null,
      conflictPending: false,
      appliedRegion: null,
      error: null,
      tab: "chat",
      openProcId: null,
      streaming: false,
      genError: null,
      // dynamicEvents, sessions는 홈에서 유지(영속)
    });
  },
}));
