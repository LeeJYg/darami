import { useEffect, useRef } from "react";
import PhoneFrame from "./components/PhoneFrame";
import ScenarioPicker from "./components/ScenarioPicker";
import TimelineBar from "./components/TimelineBar";
import ChatPanel from "./components/ChatPanel";
import TaskBoard from "./components/TaskBoard";
import ProcedureSheet from "./components/ProcedureSheet";
import { useStore } from "./store";
import { SCENARIO_MAP } from "./data/scenarios";

export default function App() {
  const { started, tab } = useStore();
  const startScenario = useStore((s) => s.startScenario);
  const autoStarted = useRef(false);

  // 데모용: ?go=<시나리오 key> 로 시나리오 자동 시작 (복합 이벤트 birth-move 포함)
  // StrictMode 이중 실행/중복 시작을 ref로 1회만 보장한다.
  useEffect(() => {
    if (autoStarted.current) return;
    const go = new URLSearchParams(window.location.search).get("go");
    if (go && SCENARIO_MAP[go]) {
      autoStarted.current = true;
      void startScenario(go);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <PhoneFrame>
      {!started ? (
        <ScenarioPicker />
      ) : (
        <div className="flex-1 flex flex-col min-h-0 relative">
          <TimelineBar />
          {tab === "chat" ? <ChatPanel /> : <TaskBoard />}
          <ProcedureSheet />
        </div>
      )}
    </PhoneFrame>
  );
}
