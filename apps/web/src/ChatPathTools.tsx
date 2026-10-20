import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type ChatMessage, type ChatPath, type ChatPathPreview, type PathConfirm, type PathDraft } from "@dreamtalk/api-client";
import { useDesktopUpdateBlock } from "./DesktopUpdates";
import type { ChatPathsController } from "./useChatPaths";

export interface PathAction { action: PathDraft["action"]; message?: ChatMessage; path?: ChatPath }
const labels = { branch: "从此分支", checkpoint: "保存检查点", edit: "编辑消息", candidate: "新建候选回复", switch: "切换路线", rename: "重命名" };

export function MessagePathActions({ message, disabled, onAction }: { message: ChatMessage; disabled: boolean; onAction: (action: PathAction) => void }) {
  return <details className="message-path-actions"><summary>消息操作</summary><div>
    {(["edit", ...(!message.media?.only_media ? ["candidate"] : []), "branch", "checkpoint"] as PathDraft["action"][]).map(action =>
      <button key={action} type="button" className="text-action" disabled={disabled || action === "edit" && (!message.text.trim() || message.media?.only_media === true)} onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); onAction({ action, message }); }}>{labels[action]}</button>)}
  </div></details>;
}

function errorText(error: unknown) {
  if (error instanceof CoreRequestError) {
    if (error.code === "chat_path_waiting_contact") return "此会话尚有主动邀请等待回复，请先回应后再切换路线。";
    if (error.code === "chat_path_reply_running") return "回复仍在运行或结果未确认，请先检查回复状态，再修改路线。";
    if (error.status === 409) return "记录或状态已经变化。请重新读取路线，再预览本次修改。";
  }
  return "操作未确认。草稿已保留；确认保存可安全重试，不会再次调用模型。";
}

export function ChatPathTools({ client, worldId, conversationId, paths, blocked, tokenCeiling, group = false, action, onAction, onGenerate }: {
  client: CoreClient; worldId: string; conversationId: string; paths: ChatPathsController; blocked: boolean;
  tokenCeiling: number; group?: boolean; action: PathAction | null; onAction: (action: PathAction | null) => void;
  onGenerate: (turnId: string) => Promise<void>;
}) {
  useDesktopUpdateBlock(paths.busy ? "正在保存聊天路线。" : null);
  const [text, setText] = useState(action?.message?.text ?? "");
  const [name, setName] = useState(action?.path?.name ?? "");
  const [preview, setPreview] = useState<ChatPathPreview | null>(null);
  const [feedback, setFeedback] = useState("");
  const [older, setOlder] = useState<ChatPath[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const receipt = useRef<PathConfirm | null>(null);
  const lock = useRef(false);
  const panel = useRef<HTMLElement>(null);
  const snapshot = paths.snapshot;
  useEffect(() => {
    if (snapshot && (action || paths.open)) {
      panel.current?.focus({ preventScroll: true });
      panel.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [action?.action, action?.message?.message_id, action?.path?.path_id, paths.open, !!snapshot]);
  const busy = blocked || paths.busy;
  const change = () => { setPreview(null); receipt.current = null; setFeedback(""); };
  const select = (value: PathAction) => { setText(value.message?.text ?? ""); setName(value.path?.name ?? ""); change(); onAction(value); };
  const readPreview = async () => {
    if (!snapshot || !action || lock.current || busy) return;
    lock.current = true; paths.setBusy(true); setFeedback("");
    try {
      const draft: PathDraft = { action: action.action, revision: snapshot.revision, message_id: action.message?.message_id ?? null,
        path_id: action.path?.path_id ?? null, name, text: action.action === "edit" ? text : "", token_ceiling: tokenCeiling };
      setPreview(await client.previewChatPath(worldId, conversationId, draft));
    } catch (error) { setFeedback(errorText(error)); if (error instanceof CoreRequestError && error.status === 409) await paths.reload().catch(() => {}); }
    finally { lock.current = false; paths.setBusy(false); }
  };
  const commit = async () => {
    if (!preview || lock.current || busy) return;
    lock.current = true; paths.setBusy(true); setFeedback("");
    receipt.current ??= { draft: preview.draft, reviewed_hash: preview.reviewed_hash, confirmed: true, request_id: crypto.randomUUID() };
    let turn: string | null;
    try {
      const result = await client.commitChatPath(worldId, conversationId, receipt.current);
      // A confirmed receipt is never submitted to the model. Even if the following
      // read fails, only the save may be retried with this same request identity.
      await paths.reload(); setOlder([]); setCursor(undefined); setPreview(null); receipt.current = null;
      turn = result.turn_id;
      onAction(null); setFeedback(turn ? "候选路线已保存，正在准备生成。" : "已保存。原路线和原文仍可在路线列表中查看。");
    } catch (error) {
      turn = null; setFeedback(errorText(error));
      if (error instanceof CoreRequestError && error.status === 409) { receipt.current = null; setPreview(null); await paths.reload().catch(() => {}); }
    }
    finally { lock.current = false; paths.setBusy(false); }
    if (turn) await onGenerate(turn);
  };
  if (!snapshot) return <p role={paths.failed ? "alert" : "status"} className="thread-hint">{paths.failed ? <>无法读取聊天路线。<button className="text-action" onClick={paths.refresh}>重新读取</button></> : "正在读取聊天路线…"}</p>;
  return <aside ref={panel} tabIndex={-1} className="chat-path-tools" aria-label="聊天路线">
    <div className="chat-path-current"><span>当前：{snapshot.active.name}{snapshot.active.kind === "checkpoint" ? "（检查点，只读）" : ""}</span><button type="button" className="text-action" onClick={() => paths.setOpen(!paths.open)}>分支与候选</button></div>
    {(paths.open || action) && <section className="chat-path-panel">
      <p className="inline-hint">候选、编辑和分支保留原文与旧路线。仅切换聊天及其记忆，不回退世界时间、地点或费用。检查点保留固定记录，选择消息的“从此分支”可继续。</p>
      {paths.open && <><ul>{[...snapshot.paths, ...older].filter((path, index, all) => all.findIndex(item => item.path_id === path.path_id) === index).map(path => <li key={path.path_id}>
        <span>{path.name}{path.path_id === snapshot.active.path_id ? " · 当前" : ""}{path.kind === "checkpoint" ? " · 检查点" : path.kind === "candidate" ? " · 候选" : ""}<small className="chat-path-time"><time dateTime={path.created_at}>{new Date(path.created_at).toLocaleString("zh-CN")}</time></small></span>
        <button type="button" className="text-action" disabled={busy || path.path_id === snapshot.active.path_id} onClick={() => select({ action: "switch", path })}>选择</button>
        <button type="button" className="text-action" disabled={busy} onClick={() => select({ action: "rename", path })}>命名</button>
      </li>)}</ul>{(cursor === undefined ? snapshot.next_before : cursor) && <button type="button" className="text-action" disabled={busy} onClick={async () => {
        if (lock.current) return; lock.current = true; paths.setBusy(true);
        try { const page = await client.chatPaths(worldId, conversationId, (cursor === undefined ? snapshot.next_before : cursor) ?? undefined); setOlder(value => [...value, ...page.paths]); setCursor(page.next_before); }
        catch (error) { setFeedback(errorText(error)); } finally { lock.current = false; paths.setBusy(false); }
      }}>读取更多路线</button>}</>}
      {action && <div className="chat-path-review"><h3>{labels[action.action]}</h3>
        {action.action === "edit" && <label className="field"><span>修改后的消息</span><textarea rows={6} maxLength={65536} disabled={busy || !!receipt.current} value={text} onChange={event => { setText(event.target.value); change(); }} /></label>}
        {!["switch"].includes(action.action) && <label className="field"><span>路线名称{action.action === "rename" ? "" : "（可留空）"}</span><input maxLength={80} disabled={busy || !!receipt.current} value={name} onChange={event => { setName(event.target.value); change(); }} /></label>}
        {action.action === "candidate" && <p>确认后将为同一条用户消息生成另一份{group ? "整轮群聊回复（共享本轮额度）" : "回复"}，可能产生模型费用。旧回复会保留。</p>}
        {preview ? <><p>即将{labels[preview.draft.action]}{action.path ? `：${action.path.name}` : ""}。{preview.creates_path && "消息之后的旧剧情保留在原路线。"}</p>
          {action.action === "edit" && <details><summary>原文</summary><pre>{preview.original_text}</pre></details>}
          <button type="button" className="primary-button" disabled={busy} onClick={() => void commit()}>{paths.busy ? "正在保存…" : preview.calls_model ? "确认保存并生成" : "确认保存"}</button>
        </> : <button type="button" className="primary-button" disabled={busy || action.action === "edit" && !text.trim() || action.action === "rename" && !name.trim()} onClick={() => void readPreview()}>预览修改</button>}
        <button type="button" className="text-action" disabled={busy} onClick={() => { onAction(null); change(); }}>取消</button>
      </div>}
      <button type="button" className="text-action" disabled={busy} onClick={() => { paths.setOpen(false); onAction(null); change(); }}>关闭路线面板</button>
    </section>}
    {feedback && <p role="status">{feedback}</p>}
  </aside>;
}
