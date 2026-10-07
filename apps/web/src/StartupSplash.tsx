import { useEffect, useRef, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { VortexController } from "./celestialVortex";
import "./startup.css";

const MIN_VISIBLE_MS = 1500;

export function StartupSplash({ ready, failed, onRetry, onComplete }: {
  ready: boolean; failed: boolean; onRetry: () => void; onComplete: () => void;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const vortex = useRef<VortexController | null>(null);
  const [visible, setVisible] = useState<boolean | null>(() => isTauri() ? null : !document.hidden);
  const visibilityNow = useRef(visible);
  const stopped = useRef(failed);
  const leaving = useRef(false);
  const remaining = useRef(MIN_VISIBLE_MS);
  const [held, setHeld] = useState(false);
  const [painted, setPainted] = useState(false);
  const [fallback, setFallback] = useState(false);
  const [reduced, setReduced] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  const entering = ready && held && visible === true && !failed;
  leaving.current = entering;
  stopped.current = failed;

  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(preference.matches);
    preference.addEventListener("change", change);
    return () => preference.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    let active = true, started = false, abandoned = false, didPaint = false;
    let visibilityTicket = 0;
    let deadline: number | undefined;
    let unlisten: (() => void) | undefined;
    const useFallback = () => {
      if (!active) return;
      abandoned = true;
      window.clearTimeout(deadline);
      vortex.current?.dispose(); vortex.current = null;
      setPainted(false); setFallback(true);
    };
    const start = () => {
      // Readiness does not skip the shot. Hidden autostart still creates no WebGL.
      if (reduced || abandoned || document.hidden || visibilityNow.current !== true || started || leaving.current || stopped.current) return;
      started = true;
      deadline = window.setTimeout(() => { if (!didPaint) useFallback(); }, 3000);
      void import("./celestialVortex").then(({ createCelestialVortex }) => {
        if (!active || abandoned) return;
        if (!surface.current || document.hidden || visibilityNow.current !== true || leaving.current || stopped.current) {
          started = false; window.clearTimeout(deadline); return;
        }
        const scene = createCelestialVortex(surface.current, () => {
          if (!active || abandoned) return;
          didPaint = true; window.clearTimeout(deadline); setPainted(true);
        });
        if (!active || abandoned) { scene.dispose(); return; }
        vortex.current = scene;
      }).catch(useFallback);
    };
    const visibility = async () => {
      const ticket = ++visibilityTicket;
      // Pause immediately on hide, before the asynchronous native query.
      if (document.hidden) {
        visibilityNow.current = false; setVisible(false); vortex.current?.setPaused(true);
      }
      let shown = !document.hidden;
      if (isTauri()) {
        try {
          const appWindow = getCurrentWindow();
          const [shownNative, minimized] = await Promise.all([appWindow.isVisible(), appWindow.isMinimized()]);
          shown = shownNative && !minimized && !document.hidden;
        } catch {
          if (active && ticket === visibilityTicket) useFallback();
          shown = !document.hidden;
        }
      }
      if (!active || ticket !== visibilityTicket) return;
      visibilityNow.current = shown; setVisible(shown);
      vortex.current?.setPaused(stopped.current || !shown);
      start();
    };
    void visibility();
    if (isTauri()) void getCurrentWindow().onFocusChanged(() => { void visibility(); }).then(stop => {
      if (active) unlisten = stop; else stop();
    }).catch(() => undefined);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      active = false; window.clearTimeout(deadline);
      document.removeEventListener("visibilitychange", visibility); unlisten?.();
      vortex.current?.dispose(); vortex.current = null;
    };
  }, [reduced]);
  useEffect(() => { vortex.current?.setPaused(failed || visibilityNow.current !== true); }, [failed]);
  useEffect(() => {
    // Count actually visible presentation time, starting with the first 3D frame.
    // Core discovery and archive loading continue independently in App.
    if (held || failed || visible !== true || (!painted && !reduced && !fallback)) return;
    const since = performance.now();
    const timer = window.setTimeout(() => setHeld(true), remaining.current);
    return () => {
      window.clearTimeout(timer);
      remaining.current = Math.max(0, remaining.current - (performance.now() - since));
    };
  }, [held, failed, visible, painted, reduced, fallback]);
  useEffect(() => {
    if (!ready || failed || visible === null || (visible && !held)) return;
    if (visible) vortex.current?.enter();
    const timer = window.setTimeout(onComplete, visible ? reduced ? 160 : 900 : 0);
    return () => window.clearTimeout(timer);
  }, [ready, failed, visible, held, reduced, onComplete]);
  return <section className={`startup-splash${entering ? " is-entering" : ""}${failed ? " has-failed" : ""}${reduced ? " is-reduced" : ""}`} aria-label="dreamtalk 启动" aria-busy={!failed}>
    <div ref={surface} className={`startup-universe${painted ? " is-painted" : ""}`} aria-hidden="true" />
    <div className="startup-vignette" aria-hidden="true" />
    <div className="startup-signature"><img src="/brand/dreamtalk-logo.png" alt="dreamtalk" width="230" height="198" draggable="false" /><span aria-hidden="true">dreamtalk</span><p>在万千星轨中，与你相遇。</p></div>
    <div className="startup-horizon" aria-hidden="true"><span />每一个世界，都有回响<span /></div>
    <p className="sr-only" role="status" aria-live="polite">{failed ? "启动暂时没有完成。" : ready ? "世界书架已准备好。" : "正在打开世界书架。"}</p>
    {failed && <div className="startup-recovery" role="alert"><p>暂时无法打开世界书架</p><span>请重试；若仍未完成，请退出程序后重新打开。</span><button type="button" onClick={onRetry}>重新打开</button></div>}
  </section>;
}
