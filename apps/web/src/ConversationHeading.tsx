import { useRef, type ReactNode } from "react";
import { WorkspaceIcon } from "./WorkspacePrimitives";

export function ConversationHeading({ title, kind, portrait, onBack, onRefresh, onLongMemory, onMemory, onHistory, onExport, onDissolve, dissolveDisabled }: {
  title: string; kind: string; portrait: ReactNode; onBack: () => void; onRefresh: () => void;
  onLongMemory: () => void; onMemory: () => void; onHistory: () => void;
  onDissolve?: () => void; dissolveDisabled?: boolean;
  onExport?: () => void;
}) {
  const tools = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const choose = (action: () => void) => {
    if (tools.current) tools.current.open = false;
    summary.current?.focus();
    action();
  };
  return <header className="thread-heading conversation-heading">
    <button type="button" className="text-action thread-back" onClick={onBack}>返回聊天</button>
    {portrait}
    <div className="thread-identity"><h2>{title}</h2><span>{kind}</span></div>
    <button type="button" className="text-action transcript-refresh" onClick={onRefresh}><WorkspaceIcon name="refresh" /><span>刷新记录</span></button>
    <details ref={tools} className="thread-tools" onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); if (tools.current) tools.current.open = false; summary.current?.focus(); }
    }}>
      <summary ref={summary}>会话工具<svg aria-hidden="true" viewBox="0 0 16 16"><path d="m4 6 4 4 4-4" /></svg></summary>
      <div className="thread-tool-actions">
        <button type="button" className="text-action" onClick={() => choose(onLongMemory)}>长期记忆</button>
        <button type="button" className="text-action" onClick={() => choose(onMemory)}>会话摘要</button>
        <button type="button" className="text-action" onClick={() => choose(onHistory)}>聊天回忆</button>
        {onExport && <button type="button" className="text-action" onClick={() => choose(onExport)}>导出聊天记录</button>}
        {onDissolve ? <button type="button" className="text-action destructive-action" disabled={dissolveDisabled} onClick={() => choose(onDissolve)}>解散群聊</button> : null}
      </div>
    </details>
  </header>;
}

export function transcriptDay(raw: string): string {
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? "时间未记录" : date.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
}
