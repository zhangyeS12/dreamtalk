import { useEffect, useState } from "react";

const INPUT = ["pointermove", "pointerdown", "keydown", "wheel"] as const;

/**
 * True while nobody is looking: the window is hidden or unfocused, or there
 * has been no input for `idleMs`. Decorative motion (twinkling stars, drifting
 * clouds) pauses then, because every frame of it also re-blurs the glass panels.
 * World time and data refresh are unaffected.
 */
export function useWindowStill(idleMs = 120_000): boolean {
  const [still, setStill] = useState(false);
  useEffect(() => {
    let timer = 0, armed = 0;
    const away = () => document.hidden || !document.hasFocus();
    const arm = () => { window.clearTimeout(timer); armed = performance.now(); timer = window.setTimeout(() => setStill(true), idleMs); };
    const check = () => { if (away()) { window.clearTimeout(timer); setStill(true); } else { setStill(false); arm(); } };
    // Input only needs to push the idle deadline back; at most once a second.
    const input = () => { if (performance.now() - armed < 1000 || away()) return; setStill(false); arm(); };
    check();
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check); window.addEventListener("blur", check);
    for (const name of INPUT) window.addEventListener(name, input, { passive: true });
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check); window.removeEventListener("blur", check);
      for (const name of INPUT) window.removeEventListener(name, input);
    };
  }, [idleMs]);
  return still;
}
