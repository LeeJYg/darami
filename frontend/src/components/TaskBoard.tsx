import { useState } from "react";
import { useStore } from "../store";
import { effectiveDday, ddayLabel } from "../lib/dday";
import type { BoardItem, Priority, Procedure, Status, UserTodo } from "../types";

const PRIORITY_GROUPS: { key: Priority; label: string; hint: string }[] = [
  { key: "must", label: "Must · 필수", hint: "기한 내 꼭 처리해야 해요" },
  { key: "nice", label: "Nice-to-have · 권장", hint: "챙기면 좋아요" },
  { key: "qna", label: "참고 · 주의", hint: "알아두세요" },
];

const STATUS_BADGE: Record<Status, { label: string; cls: string }> = {
  done: { label: "완료", cls: "bg-leaf/15 text-leaf" },
  in_progress: { label: "진행중", cls: "bg-nut/15 text-nut-deep" },
  waiting: { label: "대기", cls: "bg-acorn/10 text-acorn/60" },
};

/** 상세가 없는 보드 항목도 조용히 버리지 않도록 최소 카드로 표시 (안전망) */
function fallbackProc(id: string): Procedure {
  return {
    id,
    name: "직접 추가한 할 일",
    priority: "nice",
    deadline: "",
    deadlineDays: 9999,
    agency: "",
    online: false,
    documents: [],
    link: "",
    source: { name: "사용자 추가", tier: "reference", checkedAt: "" },
    condition: "",
    summary: "사용자 요청으로 추가된 항목입니다.",
  };
}

export default function TaskBoard() {
  const {
    board, procIndex, openProc, toggleDone, persona, event,
    userTodos, openTodoId, addUserTodo, toggleUserTodo, removeUserTodo, openTodo, updateTodoNote,
  } = useStore();

  if (board.length === 0 && userTodos.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-8 text-acorn/50">
        <div className="text-4xl mb-3">🌰</div>
        <p className="text-sm">
          대화를 시작하면 다람이가<br />필요한 절차를 모아 여기에 담아줘요.
        </p>
      </div>
    );
  }

  // 상세가 없으면 fallback으로 채워 어떤 항목도 누락되지 않게 한다(카운트 일치 보장)
  const items: { b: BoardItem; p: Procedure }[] = board.map((b) => ({
    b,
    p: procIndex[b.id] ?? fallbackProc(b.id),
  }));

  const doneCount = board.filter((b) => b.status === "done").length;

  return (
    <div className="flex-1 overflow-y-auto no-scrollbar px-4 py-4">
      {/* 진행률 */}
      <div className="mb-4">
        <div className="flex justify-between text-[11px] text-acorn/60 mb-1">
          <span>진행 상황</span>
          <span>
            {doneCount}/{board.length} 완료
          </span>
        </div>
        <div className="h-2 bg-sand rounded-full overflow-hidden">
          <div
            className="h-full bg-leaf rounded-full transition-all"
            style={{ width: `${board.length ? (doneCount / board.length) * 100 : 0}%` }}
          />
        </div>
      </div>

      {PRIORITY_GROUPS.map((g) => {
        const groupItems = items
          .filter((x) => x.p.priority === g.key)
          .sort(
            (a, b) =>
              effectiveDday(a.p, persona, event) - effectiveDday(b.p, persona, event)
          );
        if (groupItems.length === 0) return null;
        return (
          <div key={g.key} className="mb-5">
            <div className="flex items-center gap-2 mb-2 px-1">
              <span
                className={`w-2 h-2 rounded-full ${
                  g.key === "must" ? "bg-nut" : g.key === "nice" ? "bg-leaf" : "bg-acorn/40"
                }`}
              />
              <span className="text-[12px] font-bold text-acorn">{g.label}</span>
              <span className="text-[10px] text-acorn/40">{g.hint}</span>
            </div>
            <div className="space-y-2">
              {groupItems.map(({ b, p }) => (
                <div
                  key={b.id}
                  className="bg-white rounded-xl border border-sand p-3 flex items-center gap-3 active:scale-[0.99] transition"
                >
                  <button
                    onClick={() => toggleDone(b.id)}
                    className={`w-6 h-6 rounded-md border-2 flex items-center justify-center shrink-0 transition ${
                      b.status === "done"
                        ? "bg-leaf border-leaf text-white"
                        : "border-acorn/25 text-transparent"
                    }`}
                  >
                    ✓
                  </button>
                  <button onClick={() => openProc(p.id)} className="flex-1 min-w-0 text-left">
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-semibold text-[13.5px] truncate ${
                          b.status === "done" ? "text-acorn/40 line-through" : "text-acorn"
                        }`}
                      >
                        {p.name}
                      </span>
                      {p.online && (
                        <span className="text-[9px] text-leaf border border-leaf/40 rounded px-1 py-0.5 shrink-0">
                          온라인
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-acorn/55 mt-0.5 truncate">{p.deadline}</div>
                  </button>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span
                      className={`text-[10px] font-bold rounded-md px-1.5 py-0.5 ${STATUS_BADGE[b.status].cls}`}
                    >
                      {STATUS_BADGE[b.status].label}
                    </span>
                    {(() => {
                      const dday = effectiveDday(p, persona, event);
                      if (p.priority !== "must" || dday >= 3650 || b.status === "done") return null;
                      return (
                        <span
                          className={`text-[10px] font-semibold ${
                            dday < 0 ? "text-red-500" : "text-nut-deep"
                          }`}
                        >
                          {ddayLabel(dday)}
                        </span>
                      );
                    })()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      <p className="text-[10px] text-acorn/40 text-center mt-2">
        절차를 탭하면 서류·기관·바로가기를 확인할 수 있어요.
      </p>

      {/* User defined — 사용자가 직접 추가한 할 일 (검증 대상 아님, 클릭 시 메모) */}
      <UserDefinedSection
        todos={userTodos}
        openId={openTodoId}
        onToggle={toggleUserTodo}
        onRemove={removeUserTodo}
        onOpen={openTodo}
        onNote={updateTodoNote}
        onAdd={addUserTodo}
      />
    </div>
  );
}

function UserDefinedSection({
  todos, openId, onToggle, onRemove, onOpen, onNote, onAdd,
}: {
  todos: UserTodo[];
  openId: string | null;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
  onOpen: (id: string | null) => void;
  onNote: (id: string, note: string) => void;
  onAdd: (title: string) => void;
}) {
  const [input, setInput] = useState("");
  return (
    <div className="mt-6">
      <div className="flex items-center gap-2 mb-2 px-1">
        <span className="w-2 h-2 rounded-full bg-acorn/40" />
        <span className="text-[12px] font-bold text-acorn">User defined · 직접 추가</span>
        <span className="text-[10px] text-acorn/40">내가 추가한 할 일 (메모)</span>
      </div>

      <div className="space-y-2">
        {todos.map((t) => (
          <div key={t.id} className="bg-white rounded-xl border border-dashed border-acorn/25">
            <div className="p-3 flex items-center gap-3">
              <button
                onClick={() => onToggle(t.id)}
                className={`w-6 h-6 rounded-md border-2 flex items-center justify-center shrink-0 transition ${
                  t.done ? "bg-leaf border-leaf text-white" : "border-acorn/25 text-transparent"
                }`}
              >
                ✓
              </button>
              <button onClick={() => onOpen(openId === t.id ? null : t.id)} className="flex-1 min-w-0 text-left">
                <div
                  className={`font-semibold text-[13.5px] truncate ${
                    t.done ? "text-acorn/40 line-through" : "text-acorn"
                  }`}
                >
                  {t.title}
                </div>
                <div className="text-[11px] text-acorn/45 mt-0.5 truncate">
                  {t.note?.trim() ? `📝 ${t.note}` : "탭해서 메모 추가"}
                </div>
              </button>
              <button
                onClick={() => onRemove(t.id)}
                title="삭제"
                className="text-acorn/30 hover:text-red-500 text-sm px-1 shrink-0"
              >
                ✕
              </button>
            </div>
            {openId === t.id && (
              <div className="px-3 pb-3">
                <textarea
                  value={t.note}
                  onChange={(e) => onNote(t.id, e.target.value)}
                  autoFocus
                  rows={3}
                  placeholder="메모를 남겨보세요 (예: 준비물, 마감, 연락처 등)"
                  className="w-full bg-cream/60 rounded-lg p-2 text-[12.5px] text-acorn outline-none border border-sand resize-none placeholder:text-acorn/35"
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 직접 추가 입력 */}
      <div className="flex items-center gap-2 mt-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && input.trim()) {
              onAdd(input);
              setInput("");
            }
          }}
          placeholder="+ 직접 할 일 추가"
          className="flex-1 bg-white rounded-lg px-3 py-2 text-[12.5px] text-acorn outline-none border border-dashed border-acorn/25 focus:border-acorn/40 placeholder:text-acorn/40"
        />
        <button
          onClick={() => {
            if (input.trim()) {
              onAdd(input);
              setInput("");
            }
          }}
          disabled={!input.trim()}
          className="w-9 h-9 rounded-lg bg-acorn/80 text-white text-lg flex items-center justify-center disabled:opacity-30 active:scale-90 transition shrink-0"
        >
          +
        </button>
      </div>
    </div>
  );
}
