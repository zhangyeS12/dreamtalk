import { useEffect, useRef, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { VortexController } from "./celestialVortex";
import "./startup.css";

export function StartupSplash({ ready, failed, onRetry, onComplete }: {
  ready: boolean; failed: boolean; onRetry: () => void; onComplete: () => void;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const vortex = useRef<VortexController | null>(null);
  const entering = useRef(ready);
  const stopped = useRef(failed);
  const nativeHidden = useRef(isTauri());
  entering.current = ready;
  stopped.current = failed;
  const [painted, setPainted] = useState(false);
  const [reduced, setReduced] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(preference.matches);
    preference.addEventListener("change", change);
    return () => preference.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (reduced) return;
    let active = true;
    let started = false;
    let unlisten: (() => void) | undefined;
    const start = () => {
      // Hidden autostart prepares data, but never creates a background WebGL loop.
      if (document.hidden || nativeHidden.current || started || entering.current || stopped.current) return;
      started = true;
      void import("./celestialVortex").then(({ createCelestialVortex }) => {
        if (!active || !surface.current || document.hidden || nativeHidden.current || entering.current || stopped.current) { started = false; return; }
        const scene = createCelestialVortex(surface.current, () => { if (active) setPainted(true); });
        if (!active) { scene.dispose(); return; }
        vortex.current = scene;
      }).catch(() => { /* The original logo remains usable without WebGL. */ });
    };
    const visibility = async () => {
      if (isTauri()) {
        const appWindow = getCurrentWindow();
        try {
          const [visible, minimized] = await Promise.all([appWindow.isVisible(), appWindow.isMinimized()]);
          if (!active) return;
          nativeHidden.current = !visible || minimized;
        } catch { nativeHidden.current = true; }
      }
      if (!active) return;
      vortex.current?.setPaused(stopped.current || document.hidden || nativeHidden.current);
      start();
    };
    void visibility();
    if (isTauri()) void getCurrentWindow().onFocusChanged(() => { void visibility(); }).then(stop => {
      if (active) unlisten = stop; else stop();
    }).catch(() => undefined);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      active = false;
      document.removeEventListener("visibilitychange", visibility); unlisten?.();
      vortex.current?.dispose(); vortex.current = null;
    };
  }, [reduced]);
  useEffect(() => { vortex.current?.setPaused(failed || document.hidden || nativeHidden.current); }, [failed]);
  useEffect(() => {
    if (!ready || failed) return;
    vortex.current?.enter();
    const finish = () => onComplete();
    const hidden = () => { if (document.hidden) finish(); };
    // This is the exit shot, not a fake loading timer. Data is already ready.
    const timer = window.setTimeout(finish, document.hidden || nativeHidden.current ? 0 : reduced ? 160 : 900);
    document.addEventListener("visibilitychange", hidden);
    return () => { clearTimeout(timer); document.removeEventListener("visibilitychange", hidden); };
  }, [ready, failed, reduced, onComplete]);
  return <section className={`startup-splash${ready && !failed ? " is-entering" : ""}${failed ? " has-failed" : ""}${reduced ? " is-reduced" : ""}`} aria-label="dreamtalk 启动" aria-busy={!ready && !failed}>
    <div ref={surface} className={`startup-universe${painted ? " is-painted" : ""}`} aria-hidden="true" />
    <div className="startup-vignette" aria-hidden="true" />
    <div className="startup-signature"><img src="/brand/dreamtalk-logo.png" alt="dreamtalk" width="230" height="198" draggable="false" /><span aria-hidden="true">dreamtalk</span></div>
    <p className="sr-only" role="status" aria-live="polite">{failed ? "启动暂时没有完成。" : ready ? "世界书架已准备好。" : "正在打开世界书架。"}</p>
    {failed && <div className="startup-recovery" role="alert"><p>暂时无法打开世界书架</p><span>请重试；若仍未完成，请退出程序后重新打开。</span><button type="button" onClick={onRetry}>重新打开</button></div>}
  </section>;
}
