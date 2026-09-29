import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type ChatMessage, type ConversationMemoryDraft, type ConversationMemorySnapshot, type ConversationMemorySources } from "@dreamtalk/api-client";
import { ChatMessageBody } from "./ChatMessageBody";

function feedback(failure: unknown): string {
  const code = failure instanceof CoreRequestError ? failure.code ?? "" : "";
  const known: Record<string, string> = {
    memory_revision_changed: "已有较新的确认版本。草稿仍保留，请读取最新状态后重新整理或修正。",
    memory_preview_changed: "预览已变化，请重新预览后确认。",
    memory_no_new_messages: "没有新的已保存消息可整理。",
    memory_content_invalid: "摘要不能为空，且不能超过 8,192 字节。请缩短后重新预览。",
    memory_model_unavailable: "尚未配置可用模型。仍可查看已有摘要，或手动修正。",
    memory_token_bound_unavailable: "无法确认本次模型输入额度，请检查模型设置。无需调整聊天每轮额度。",
    memory_output_invalid: "模型输出未通过完整性检查。本次可能已有费用，没有保存为记忆。",
    memory_model_failed: "模型调用未完成，请检查模型、余额和网络。本次可能已有费用；不会自动重试。",
    memory_interrupted: "上次生成被中断，不会自动重新调用模型。可明确点击生成新的初稿。",
    memory_capacity_reached: "正在处理其他资料生成任务，请稍后再试。",
    memory_generation_failed: "摘要任务未完成，草稿状态已保留，不会自动重新调用模型。",
    memory_source_invalid: "来源暂时无法核对，请读取最新状态。",
    conversation_not_found: "当前身份已变化或无法访问这段会话，请关闭后重新打开。",
  };
  return known[code] ?? "操作结果尚未确认。请点击“读取最新状态”核对；系统不会自动重复模型调用。";
}

export function ConversationMemoryPanel({ client, worldId, conversationId, senderName, canGenerate, onClose }: {
  client: CoreClient; worldId: string; conversationId: string; senderName: (message: ChatMessage) => string;
  canGenerate: boolean; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const lifetime = useRef<AbortController | null>(null);
  const locked = useRef(false);
  const [view, setView] = useState<ConversationMemorySnapshot | null>(null);
  const [draft, setDraft] = useState<ConversationMemoryDraft | null>(null);
  const [content, setContent] = useState("");
  const [sources, setSources] = useState<ChatMessage[] | null>(null);
  const [history, setHistory] = useState<ConversationMemorySources | null>(null);
  const [busy, setBusy] = useState("正在读取记忆…");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const request = new AbortController(); lifetime.current = request;
    const element = dialog.current; element?.showModal();
    void client.conversationMemory(worldId, conversationId, request.signal).then(result => {
      if (request.signal.aborted) return;
      setView(result); setDraft(result.draft); setContent(result.draft?.content ?? "");
    }).catch(failure => { if (!request.signal.aborted) setError(feedback(failure)); })
      .finally(() => { if (!request.signal.aborted) setBusy(""); });
    return () => { request.abort(); element?.close(); };
  }, [client, worldId, conversationId]);

  const run = async (label: string, operation: (signal: AbortSignal) => Promise<void>) => {
    const request = lifetime.current;
    if (locked.current || !request || request.signal.aborted) return;
    locked.current = true; setBusy(label); setError(""); setNotice("");
    try { await operation(request.signal); }
    catch (failure) { if (!request.signal.aborted) setError(feedback(failure)); }
    finally { locked.current = false; if (!request.signal.aborted) setBusy(""); }
  };
  const refresh = () => run("正在核对保存状态…", async signal => {
    const result = await client.conversationMemory(worldId, conversationId, signal);
    if (signal.aborted) return;
    setView(result);
    const keepEdits = draft?.draft_id === result.draft?.draft_id && ["ready", "previewed"].includes(result.draft?.state ?? "") && content !== draft?.content;
    setDraft(keepEdits && result.draft ? { ...result.draft, state: "ready", reviewed_hash: null } : result.draft);
    if (!keepEdits) setContent(result.draft?.content ?? "");
    setSources(null); setHistory(null);
    setNotice(result.draft?.state === "committed" ? "这份摘要已保存。" : "已读取最新状态，未重新调用模型。");
  });
  const create = (mode: "summarize" | "correct") => run(mode === "summarize" ? "正在整理摘要，可能产生模型费用…" : "正在建立修正草稿…", async signal => {
    if (!view) return;
    const result = await client.draftConversationMemory(worldId, conversationId, view.current?.revision ?? 0, mode, crypto.randomUUID(), signal);
    if (signal.aborted) return;
    setDraft(result); setContent(result.content ?? ""); setSources(null); setHistory(null);
    if (result.error) setError(feedback(new CoreRequestError(409, result.error)));
    else setNotice(mode === "correct" ? "请修改草稿，再预览确认。不调用模型。" : "初稿已保留，请核对原文并修改，再预览确认。");
  });
  const preview = () => run("正在保存预览并读取原文…", async signal => {
    if (!draft) return;
    const result = await client.previewConversationMemory(worldId, conversationId, draft.draft_id, content, signal);
    if (signal.aborted) return;
    setDraft(result); setContent(result.content ?? ""); setSources(null);
    const raw = await client.conversationMemoryDraftSources(worldId, conversationId, result.draft_id, signal);
    if (!signal.aborted) { setSources(raw.items); setNotice("请核对下面的摘要和来源，再确认保存。"); }
  });
  const save = () => run("正在确认保存记忆…", async signal => {
    if (!draft?.reviewed_hash || sources === null) return;
    const revision = await client.commitConversationMemory(worldId, conversationId, draft.draft_id, draft.reviewed_hash, signal);
    if (signal.aborted) return;
    setView(current => current ? { ...current, current: revision } : current);
    setDraft(current => current ? { ...current, state: "committed", committed_revision: revision.revision } : current);
    setSources(null); setNotice(`第 ${revision.revision} 版已保存，将用于这段会话后续的角色回复。`);
  });
  const revision = (number: number) => run("正在读取版本与原文…", async signal => {
    const result = await client.conversationMemoryRevision(worldId, conversationId, number, signal);
    if (!signal.aborted) setHistory(result);
  });
  const sourceList = (messages: ChatMessage[]) => <ol className="history-results">{messages.map(message => <li key={message.message_id}>
    <div className="history-source"><strong>{senderName(message)}</strong><time dateTime={message.created_at_utc}>{new Date(message.created_at_utc).toLocaleString("zh-CN")}</time><small>第 {message.position} 条消息</small></div><ChatMessageBody text={message.text} />
  </li>)}</ol>;
  const editable = draft && ["ready", "previewed"].includes(draft.state);
  const stale = !!draft && draft.base_revision !== (view?.current?.revision ?? 0);
  const valid = !!content.trim() && new TextEncoder().encode(content).byteLength <= 8192;
  return <dialog ref={dialog} className="chat-history-dialog conversation-memory-dialog" aria-labelledby="conversation-memory-title" onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="history-heading"><h2 id="conversation-memory-title">记忆摘要</h2><button type="button" className="text-action" onClick={onClose}>关闭</button></div>
    <p className="inline-hint">只整理这段共同对话。确认后供本会话角色参考；原文保留，不会变成世界事实。</p>
    {busy ? <p role="status" aria-live="polite">{busy}</p> : null}
    {error ? <p role="alert" className="history-error">{error}</p> : null}
    {notice ? <p role="status" aria-live="polite">{notice}</p> : null}
    <button type="button" className="text-action" disabled={!!busy} onClick={() => void refresh()}>读取最新状态</button>
    {view ? <>
      <section className="memory-current" aria-label="已确认记忆">
        <h3>已确认摘要</h3>
        {view.current ? <><p className="inline-hint">第 {view.current.revision} 版 · 整理到第 {view.current.through_position} 条消息{view.current.user_edited ? " · 含用户修改" : ""}</p><ChatMessageBody text={view.current.content} /><button type="button" className="text-action" disabled={!!busy} onClick={() => void revision(view.current!.revision)}>查看版本与来源</button></> : <p>还没有已确认的记忆。</p>}
      </section>
      <div className="history-actions"><button type="button" className="primary-button" disabled={!!busy || !canGenerate || !view.model_available || view.latest_position <= (view.current?.through_position ?? 0) || draft?.state === "generating"} onClick={() => void create("summarize")}>{view.current ? "整理后续对话" : "生成摘要初稿"}</button><button type="button" disabled={!!busy || !view.current || draft?.state === "generating"} onClick={() => void create("correct")}>手动修正记忆</button></div>
      <p className="history-footnote">生成使用现有模型，按实际用量计费，使用独立任务额度；每批最多整理 32 条 / 96 KiB 原文，不自动调用。当前已保存至第 {view.latest_position} 条。长对话请逐批确认继续整理。</p>
      {!view.model_available ? <p className="inline-hint">模型暂不可用，仍能阅读或修正已有摘要。</p> : null}
    </> : null}
    {draft && draft.state !== "committed" ? <section className="memory-draft" aria-label="记忆草稿">
      <h3>待确认草稿</h3><p className="inline-hint">基于第 {draft.base_revision} 版，整理至第 {draft.through_position} 条；本批 {draft.source_ids.length} 条新原文。</p>
      {draft.state === "generating" ? <p role="status">任务仍在生成。稍后点击读取最新状态，不要重复调用。</p> : null}
      {draft.error ? <p className="history-error">{feedback(new CoreRequestError(409, draft.error))}</p> : null}
      {stale ? <p className="history-error">基础版本已变化，这份草稿不能覆盖当前记忆。</p> : null}
      {editable ? <>
        <label htmlFor="conversation-memory-editor">摘要内容（可自由修正）</label>
        <textarea id="conversation-memory-editor" rows={8} maxLength={8192} value={content} disabled={!!busy || stale} onChange={event => { setContent(event.target.value); setDraft(current => current ? { ...current, state: "ready", reviewed_hash: null } : current); setSources(null); setNotice(""); }} />
        {!valid ? <p className="history-error">填写非空摘要，最多 8,192 字节。</p> : null}
        <button type="button" disabled={!!busy || stale || !valid} onClick={() => void preview()}>预览摘要与原文</button>
        {draft.state === "previewed" ? <section className="history-context" aria-label="待保存预览"><h3>本次预览</h3><ChatMessageBody text={draft.content ?? ""} />
          <h4>本批原文</h4>{sources === null ? <p>点击“预览摘要与原文”读取来源后才能确认。</p> : sources.length ? sourceList(sources) : <p>本次是手动修正，沿用基础版本的来源。</p>}
          {draft.base_revision > 0 ? <button type="button" className="text-action" disabled={!!busy} onClick={() => void revision(draft.base_revision)}>核对基础版本与更早来源</button> : null}
          <p className="inline-hint">来源供核对，不保证摘要每句话都正确。保存修正会留下旧版本。</p><button type="button" className="primary-button" disabled={!!busy || sources === null || stale || !draft.reviewed_hash} onClick={() => void save()}>确认保存这份记忆</button>
        </section> : null}
      </> : null}
    </section> : null}
    {history ? <section className="history-context" aria-label="历史版本"><div className="history-heading"><h3>第 {history.memory.revision} 版 · 至第 {history.memory.through_position} 条</h3><button type="button" className="text-action" onClick={() => setHistory(null)}>收起版本</button></div><ChatMessageBody text={history.memory.content} />{sourceList(history.sources)}<div className="history-actions">{history.memory.base_revision > 0 ? <button type="button" disabled={!!busy} onClick={() => void revision(history.memory.base_revision)}>上一版与更早来源</button> : <span>这是首个版本。</span>}{view?.current && history.memory.revision < view.current.revision ? <button type="button" disabled={!!busy} onClick={() => void revision(history.memory.revision + 1)}>下一版</button> : null}</div></section> : null}
    <p className="history-footnote">关闭不会确认或重新生成。已生成及已预览草稿可重开读取；尚未预览的本地修改在关闭后不会保留。</p>
  </dialog>;
}
