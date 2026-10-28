import { useEffect, useState, type CSSProperties, type ReactNode, type Ref } from "react";
import styles from "./WorldShell.module.css";
import "./tokens.css";

/**
 * Layout frame for everything inside a world: sky across the top, the four
 * entries on the rail, and the active page. The room is lit from where the
 * sun or moon currently stands.
 */
export function WorldShell({ className, style, sky, rail, immersive, children, mainRef }: {
  className: string; style: CSSProperties; sky: ReactNode; rail: ReactNode; immersive: boolean;
  children: ReactNode; mainRef?: Ref<HTMLElement>;
}) {
  return <div className={`dt-world ${styles.shell} ${className}`} style={style} data-immersive={immersive || undefined}>
    {sky}
    {!immersive && rail}
    <main className={styles.main} id="main-content" ref={mainRef}>{children}</main>
  </div>;
}

/** Workspace feedback. Errors stay until dismissed or replaced; notices fade after a while. */
export function WorldNotices({ error, notice, onDismissError, onDismissNotice }: {
  error: string; notice: string; onDismissError: () => void; onDismissNotice: () => void;
}) {
  const [shownNotice, setShownNotice] = useState(notice);
  useEffect(() => {
    setShownNotice(notice);
    if (!notice) return;
    const timer = window.setTimeout(() => { setShownNotice(""); onDismissNotice(); }, 7000);
    return () => window.clearTimeout(timer);
  }, [notice, onDismissNotice]);
  return <div className={styles.notices}>
    {error ? <div className={styles.notice} data-tone="error">
      <p role="alert">{error}</p>
      <button type="button" aria-label="关闭提示" onClick={onDismissError}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M7 17 17 7" /></svg>
      </button>
    </div> : null}
    {shownNotice ? <div className={styles.notice} data-tone="notice"><p role="status">{shownNotice}</p></div> : null}
  </div>;
}
