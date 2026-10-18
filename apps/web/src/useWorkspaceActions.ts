import { useCallback, useEffect, useReducer, useRef, type SetStateAction } from "react";

type Status = { busy: boolean; error: string; notice: string };
type Action = { type: "begin" | "finished" } | { type: "error"; value: SetStateAction<string> }
  | { type: "notice"; value: string };
function reduce(state: Status, action: Action): Status {
  switch (action.type) {
    case "begin": return { busy: true, error: "", notice: "" };
    case "finished": return { ...state, busy: false };
    case "error": return { ...state, error: typeof action.value === "function" ? action.value(state.error) : action.value };
    case "notice": return { ...state, notice: action.value };
  }
}

export function useWorkspaceActions() {
  const [state, dispatch] = useReducer(reduce, { busy: false, error: "", notice: "" });
  const alive = useRef(false), running = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const setError = useCallback((value: SetStateAction<string>) => { if (alive.current) dispatch({ type: "error", value }); }, []);
  const setNotice = useCallback((value: string) => { if (alive.current) dispatch({ type: "notice", value }); }, []);
  const run = useCallback(async (action: () => Promise<unknown>, success: string, failure = "操作未完成，请稍后重试。") => {
    if (running.current || !alive.current) return;
    running.current = true;
    dispatch({ type: "begin" });
    try { await action(); if (alive.current) dispatch({ type: "notice", value: success }); }
    catch { if (alive.current) dispatch({ type: "error", value: failure }); }
    finally { running.current = false; if (alive.current) dispatch({ type: "finished" }); }
  }, []);
  return { ...state, setError, setNotice, run };
}
