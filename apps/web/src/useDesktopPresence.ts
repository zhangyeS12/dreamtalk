import { useEffect } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";

export function useDesktopPresence(worldId: string, playerId: string | null) {
  useEffect(() => {
    if (!isTauri()) return;
    let active = true, running = false;
    let timer: number | undefined;
    const report = async () => {
      if (running || !active) return;
      running = true;
      try {
        await invoke("report_desktop_presence", { worldId: playerId ? worldId : null,
          visible: Boolean(worldId && playerId && document.visibilityState === "visible" && document.hasFocus()) });
      } catch { /* A failed report lets the short visibility lease expire. */ }
      finally { running = false; if (active) { window.clearTimeout(timer); timer = window.setTimeout(() => void report(), 10_000); } }
    };
    const changed = () => { void report(); };
    window.addEventListener("focus", changed); window.addEventListener("blur", changed);
    document.addEventListener("visibilitychange", changed);
    void report();
    return () => { active = false; window.clearTimeout(timer);
      window.removeEventListener("focus", changed); window.removeEventListener("blur", changed);
      document.removeEventListener("visibilitychange", changed);
      void invoke("report_desktop_presence", { worldId: null, visible: false }).catch(() => undefined); };
  }, [worldId, playerId]);
}
