import { useEffect, useState, type CSSProperties, type ReactNode, type Ref } from "react";
import { WorldScene } from "./WorldScene";
import styles from "./WorldShell.module.css";
import "./tokens.css";
import "./theme.css";

/**
 * Everything inside a world floats over that world's sky: the title written
 * on the sky, the four entries on a glass rail, and the active page.
 */
export function WorldShell({ className, style, sky, rail, immersive, paused, body, children, mainRef }: {
  className: string; style: CSSProperties; sky: ReactNode; rail: ReactNode; immersive: boolean; paused: boolean;
  body: "sun" | "moon" | null; children: ReactNode; mainRef?: Ref<HTMLElement>;
}) {
  return <div className={`dt-world ${styles.shell} ${className}`} style={style} data-immersive={immersive || undefined} data-paused={paused || undefined}>
    <WorldScene kind={body} />
    {sky}
    {!immersive && <div className={styles.railSlot}>{rail}</div>}
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
