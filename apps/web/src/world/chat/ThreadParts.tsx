import { useRef, type CSSProperties, type FormEvent, type ReactNode, type Ref } from "react";
import type { ChatMessage } from "@dreamtalk/api-client";
import styles from "./Thread.module.css";

const tintStyle = (tint?: string) => (tint ? ({ "--tint": tint } as CSSProperties) : undefined);

/** Initial on the character's own colour, or their uploaded portrait. */
export function WorldAvatar({ name, url, tint, size = "m", className = "" }: { name: string; url?: string; tint?: string; size?: "s" | "m" | "l"; className?: string }) {
  return <span className={`${styles.avatar} ${className}`} data-size={size} style={tintStyle(tint)} aria-hidden="true">
    {url ? <img src={url} alt="" /> : Array.from(name.trim())[0] ?? "?"}
  </span>;
}

/**
 * One conversation surface: header, optional tools, the scrolling transcript
 * and the composer. `scrollRef` must sit on the direct child of the scroller
 * (useChatScroll reads its parent element).
 */
export function ThreadFrame({ label, header, tools, stage, scrollRef, children, composer, tint, staged, portrait = false }: {
  label: string; header: ReactNode; tools?: ReactNode; stage?: ReactNode; scrollRef: Ref<HTMLElement>;
  children: ReactNode; composer: ReactNode; tint?: string; staged: boolean; portrait?: boolean;
}) {
  return <section className={styles.frame} aria-label={label} style={tintStyle(tint)} data-staged={staged || undefined} data-portrait={portrait || undefined}>
    {stage}
    {header}
    {tools ? <div className={styles.tools}>{tools}</div> : null}
    <div className={styles.scroller} data-chat-scroll>
      <div ref={scrollRef as Ref<HTMLDivElement>} className={styles.column}>{children}</div>
    </div>
    {composer}
  </section>;
}

export function ThreadStage({ url, label }: { url?: string; label: string }) {
  if (!url) return null;
  return <div className={styles.stage} aria-label={label}><img src={url} alt="" /></div>;
}

export function ThreadHeader({ title, kind, portrait, onBack, onRefresh, onLongMemory, onMemory, onHistory, onExport, onPaths, onDissolve, dissolveDisabled, visualControl }: {
  title: string; kind: string; portrait: ReactNode; onBack: () => void; onRefresh: () => void;
  onLongMemory: () => void; onMemory: () => void; onHistory: () => void;
  onDissolve?: () => void; dissolveDisabled?: boolean; onExport?: () => void; onPaths?: () => void; visualControl?: ReactNode;
}) {
  const tools = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const choose = (action: () => void) => {
    if (tools.current) tools.current.open = false;
    summary.current?.focus();
    action();
  };
  return <header className={styles.header}>
    <button type="button" className={styles.back} onClick={onBack}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg><span>返回聊天</span>
    </button>
    {portrait}
    <div className={styles.identity}><h2>{title}</h2><span>{kind}</span></div>
    <div className={styles.headerTools}>
      {visualControl}
      <button type="button" className={styles.chip} onClick={onRefresh}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 5v5h-5M4 19v-5h5M5.2 8a7.5 7.5 0 0 1 12-3L20 8M4 16l2.8 3a7.5 7.5 0 0 0 12-3" /></svg><span>刷新记录</span>
      </button>
      <details ref={tools} className={styles.menu} onKeyDown={event => {
        if (event.key === "Escape") { event.preventDefault(); if (tools.current) tools.current.open = false; summary.current?.focus(); }
      }}>
        <summary ref={summary} className={styles.chip}>会话工具<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg></summary>
        <div className={styles.menuPanel}>
          <button type="button" onClick={() => choose(onLongMemory)}>长期记忆</button>
          <button type="button" onClick={() => choose(onMemory)}>会话摘要</button>
          <button type="button" onClick={() => choose(onHistory)}>聊天回忆</button>
          {onPaths && <button type="button" onClick={() => choose(onPaths)}>分支、检查点与候选</button>}
          {onExport && <button type="button" onClick={() => choose(onExport)}>导出聊天记录</button>}
          {onDissolve ? <button type="button" data-tone="danger" disabled={dissolveDisabled} onClick={() => choose(onDissolve)}>解散群聊</button> : null}
        </div>
      </details>
    </div>
  </header>;
}

/** Script layout: the speaker's name stands in the margin, their words carry the page. */
export function ScriptMessage({ message, own, name, tint, time, body, tools }: {
  message: ChatMessage; own: boolean; name: string; tint?: string; time: ReactNode; body: ReactNode; tools?: ReactNode;
}) {
  if (own) return <li data-message-id={message.message_id} className={styles.mine}>
    <span className="sr-only">我</span>
    <div className={styles.pill}>{body}</div>
    <div className={styles.mineMeta}>{time}{tools}</div>
  </li>;
  return <li data-message-id={message.message_id} className={styles.line} style={tintStyle(tint)}>
    <div className={styles.name}><span>{name}</span>{time}</div>
    <div className={styles.text}>{body}{tools ? <div className={styles.lineTools}>{tools}</div> : null}</div>
  </li>;
}

export function DayDivider({ children }: { children: ReactNode }) {
  return <li className={styles.day}>{children}</li>;
}

export function ThreadNote({ children, tone = "status" }: { children: ReactNode; tone?: "status" | "alert" | "plain" }) {
  return <p className={styles.note} role={tone === "plain" ? undefined : tone} data-tone={tone}>{children}</p>;
}

export function ThreadEmpty({ title, children }: { title: string; children: ReactNode }) {
  return <div className={styles.empty}><h2>{title}</h2><p>{children}</p></div>;
}

export function TranscriptButton({ children, disabled, onClick }: { children: ReactNode; disabled?: boolean; onClick: () => void }) {
  return <div className={styles.transcriptAction}><button type="button" disabled={disabled} onClick={onClick}>{children}</button></div>;
}

/** The writing capsule floats over the bottom of the transcript. */
export function ComposerShell({ onSubmit, status, mentions, sticker, input, send, meta }: {
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  status: ReactNode; mentions?: ReactNode; sticker: ReactNode; input: ReactNode; send: ReactNode; meta: ReactNode;
}) {
  return <form className={styles.composer} onSubmit={onSubmit}>
    <div className={styles.composerStatus}>{status}</div>
    {mentions}
    <div className={styles.capsule}>
      <div className={styles.sticker}>{sticker}</div>
      {input}
      {send}
    </div>
    <div className={styles.composerMeta}>{meta}</div>
  </form>;
}

export function SendButton({ label, disabled }: { label: string; disabled: boolean }) {
  return <button type="submit" className={styles.send} disabled={disabled}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6" /></svg>
    <span className={label === "发送" ? "sr-only" : styles.sendLabel}>{label}</span>
  </button>;
}

export const threadStyles = styles;
