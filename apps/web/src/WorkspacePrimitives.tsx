import { useId, type ReactNode } from "react";

export type WorkspaceIconName = "search" | "plus" | "orbit" | "arrow" | "book" | "people" | "refresh" | "close";

export function WorkspaceIcon({ name }: { name: WorkspaceIconName }) {
  const paths = {
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    orbit: <><circle cx="12" cy="12" r="4" /><ellipse cx="12" cy="12" rx="11" ry="4.5" transform="rotate(-30 12 12)" /><path d="m19 2 .5 1.5L21 4l-1.5.5L19 6l-.5-1.5L17 4l1.5-.5Z" /></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    book: <><path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4Zm16 0h-4a3 3 0 0 0-3 3m0 14a4 4 0 0 1 4-2h3V4" /></>,
    people: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 5a3 3 0 0 1 0 6m1 3a5 5 0 0 1 3 5" /></>,
    refresh: <><path d="M20 5v5h-5M4 19v-5h5M5.2 8a7.5 7.5 0 0 1 12-3L20 8M4 16l2.8 3a7.5 7.5 0 0 0 12-3" /></>,
    close: <path d="m6 6 12 12M6 18 18 6" />,
  };
  return <svg className="workspace-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

/** Filters only already-authorized directory names. It performs no requests. */
export function DirectorySearch({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const id = useId();
  return <div className="directory-search">
    <label className="sr-only" htmlFor={id}>{label}</label><WorkspaceIcon name="search" />
    <input id={id} type="search" value={value} onChange={event => onChange(event.target.value)} placeholder={label} autoComplete="off" maxLength={120} />
    {value && <button type="button" aria-label="清除搜索" onClick={() => { onChange(""); document.getElementById(id)?.focus(); }}><WorkspaceIcon name="close" /></button>}
  </div>;
}

export function CelestialEmpty({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="conversation-placeholder celestial-empty">
    <div className="empty-emblem" aria-hidden="true"><i /><img src="/brand/dreamtalk-logo.png" alt="" width="120" height="104" /></div>
    <h2>{title}</h2><p>{children}</p>{action}
  </div>;
}
