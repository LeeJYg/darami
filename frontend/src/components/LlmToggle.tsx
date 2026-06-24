import { useEffect, useState } from "react";
import { useStore } from "../store";
import { LLM_OPTIONS } from "../data/llm";
import { getProviders } from "../api/chat";
import type { LlmProvider } from "../types";

/**
 * 응답 LLM(Solar Pro / K-EXAONE) 전환용 작은 segmented 토글.
 * - 선택은 localStorage에 영속(store.llm).
 * - 백엔드에 키가 없는 모델은 비활성(disabled) 처리.
 */
export default function LlmToggle({ className = "" }: { className?: string }) {
  const llm = useStore((s) => s.llm);
  const setLlm = useStore((s) => s.setLlm);
  const [available, setAvailable] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let alive = true;
    getProviders()
      .then((list) => {
        if (!alive) return;
        const map: Record<string, boolean> = {};
        for (const p of list) map[p.key] = p.available;
        setAvailable(map);
        // 현재 선택이 사용 불가하면 사용 가능한 첫 모델로 전환
        if (map[llm] === false) {
          const fallback = list.find((p) => p.available);
          if (fallback) setLlm(fallback.key as LlmProvider);
        }
      })
      .catch(() => {
        /* 조회 실패 시 모두 활성으로 간주(서버가 막판에 폴백 처리) */
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isOff = (key: string) => available[key] === false;

  return (
    <div className={`inline-flex flex-col items-center ${className}`}>
      <div className="inline-flex rounded-full bg-sand/70 p-0.5 shadow-inner">
        {LLM_OPTIONS.map((o) => {
          const active = llm === o.key;
          const off = isOff(o.key);
          return (
            <button
              key={o.key}
              type="button"
              disabled={off}
              onClick={() => !off && setLlm(o.key)}
              title={off ? `${o.label} — API 키 미설정` : `${o.vendor} · ${o.label}`}
              className={`px-3 py-1 rounded-full text-[11px] font-bold transition whitespace-nowrap ${
                active
                  ? "bg-white text-acorn shadow-sm"
                  : "text-acorn/45 hover:text-acorn/70"
              } ${off ? "opacity-35 cursor-not-allowed" : "active:scale-95"}`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
