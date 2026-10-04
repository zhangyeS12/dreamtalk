import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type LongChatMemory, type LongChatMemorySnapshot } from "@dreamtalk/api-client";

import { SourceMessageDialog } from "./SourceMessageDialog";

const kinds = { identity: "身份与称呼", preference: "偏好", promise: "约定", experience: "经历" };
const states = { active: "正在使用", forgotten: "已停用", superseded: "已有新记录" };

export function LongChatMemoryPanel({ client, worldId, conversationId, characters, onClose }: {
  client: CoreClient; worldId: string; conversationId: string;
  characters: { character_id: string; character_name: string }[]; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const lifetime = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const [characterId, setCharacterId] = useState(characters[0]?.character_id ?? "");
  const [view, setView] = useState<LongChatMemorySnapshot | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [source, setSource] = useState<LongChatMemory | null>(null);

  useEffect(() => {
    const element = dialog.current; element?.showModal();
    return () => element?.close();
  }, []);
  useEffect(() => {
    const request = new AbortController(); lifetime.current = request; lock.current = true;
    setBusy(true); setView(null); setError(""); setNotice(""); setQuery(""); setSource(null);
    void client.longChatMemory(worldId, conversationId, characterId, "", undefined, request.signal)
      .then(result => { if (!request.signal.aborted) { setView(result); setError(""); setNotice(""); setQuery(""); } })
      .catch(failure => { if (!request.signal.aborted) setError(feedback(failure)); })
      .finally(() => { if (!request.signal.aborted) { lock.current = false; setBusy(false); } });
    return () => request.abort();
  }, [client, worldId, conversationId, characterId]);

  function feedback(failure: unknown): string {
    const code = failure instanceof CoreRequestError ? failure.code : "";
    if (code === "long_memory_changed") return "记忆状态已有变化，请读取最新记忆后再操作。";
    if (code === "long_memory_not_found") return "当前身份无法访问这些记忆，请关闭后重新打开会话。";
    return "未能确认操作结果，请读取最新记忆。没有额外调用模型。";
  }
  const run = async (action: (signal: AbortSignal) => Promise<LongChatMemorySnapshot>, append = false, message = "") => {
    const request = lifetime.current;
    if (!request || request.signal.aborted || lock.current) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const result = await action(request.signal);
      if (!request.signal.aborted) {
        setView(previous => append && previous ? { ...result, items: [...previous.items, ...result.items] } : result);
        setNotice(message);
        if (message) setQuery("");
      }
    } catch (failure) { if (!request.signal.aborted) setError(feedback(failure)); }
    finally { if (!request.signal.aborted) { lock.current = false; setBusy(false); } }
  };
  const mark = (entry: LongChatMemory, active: boolean, pinned: boolean) => void run(signal =>
    client.markLongChatMemory(worldId, conversationId, characterId, entry, active, pinned, signal), false,
    active ? "记忆状态已保存。" : "这条记忆已停止用于长期回忆，原聊天记录仍保留。");

  return <dialog ref={dialog} className="memory-dialog" onCancel={onClose}>
    <div className="thread-heading"><h2>长期记忆</h2><button type="button" onClick={onClose}>关闭</button></div>
    <p>角色会从聊天中记住重要信息、偏好、约定和经历。重启后仍保留，也能在该角色参与的其他会话中取用。</p>
    {characters.length > 1 && <label>查看角色 <select disabled={busy} value={characterId} onChange={event => { setBusy(true); setView(null); setCharacterId(event.target.value); }}>{characters.map(character => <option key={character.character_id} value={character.character_id}>{character.character_name}</option>)}</select></label>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="controls">
      <button type="button" disabled={busy} onClick={() => { setQuery(""); void run(signal => client.longChatMemory(worldId, conversationId, characterId, "", undefined, signal)); }}>读取最新记忆</button>
      {view && <button type="button" disabled={busy} onClick={() => void run(signal => client.configureLongChatMemory(worldId, conversationId, characterId, !view.enabled, view.settings_revision, signal), false, view.enabled ? "已停止自动记录，已有记忆仍可使用。" : "已开启后续聊天的自动记录。")}>{view.enabled ? "关闭自动记录" : "开启自动记录"}</button>}
    </div>
    <p className="inline-hint">自动记录随正常回复完成，不额外调用提取 API；提示和记忆会增加有限 Token 用量。当前自动提取优先支持官方 DeepSeek；旧聊天可按关键词召回相关原句，不需要先调用模型整理。停用或置顶不调用模型。</p>
    <form className="controls" onSubmit={event => { event.preventDefault(); void run(signal => client.longChatMemory(worldId, conversationId, characterId, query, undefined, signal)); }}>
      <label>搜索记忆 <input value={query} disabled={busy} maxLength={200} onChange={event => setQuery(event.target.value)} /></label><button type="submit" disabled={busy}>搜索</button>
    </form>
    {busy && <p role="status">正在处理记忆…</p>}
    {view && view.items.length === 0 && <p>还没有符合条件的长期记忆。后续聊天中明确告诉角色重要信息后，可以回来核对。</p>}
    {view?.items.map(entry => <article key={entry.entry_id} className="memory-entry">
      <h3>{entry.topic} <small>{kinds[entry.kind]} · {states[entry.state]}{entry.pinned ? " · 已置顶" : ""}</small></h3>
      <p>{entry.content}</p>
      <p className="inline-hint">记录于 {new Date(entry.created_at).toLocaleString()} · {entry.source_kind === "player" ? "玩家原话" : "角色原话"}</p>
      <details><summary>查看来源</summary><blockquote>{entry.quote}</blockquote><p className="inline-hint">来源保留于原会话；自述和约定仍可能变化。{entry.replaces ? "这条记录更新了此前的记忆。" : ""}</p><button type="button" className="text-action" disabled={busy} onClick={() => setSource(entry)}>查看原文前后文</button></details>
      {entry.state !== "superseded" && <div className="controls"><button type="button" disabled={busy} onClick={() => mark(entry, entry.state === "active", !entry.pinned)}>{entry.pinned ? "取消置顶" : "置顶"}</button><button type="button" disabled={busy} onClick={() => mark(entry, entry.state !== "active", entry.pinned)}>{entry.state === "active" ? "停用此条" : "重新使用"}</button></div>}
    </article>)}
    {view?.next_cursor && <button type="button" disabled={busy} onClick={() => void run(signal => client.longChatMemory(worldId, conversationId, characterId, "", view.next_cursor ?? undefined, signal), true)}>加载更早记忆</button>}
    <p className="inline-hint">同一主题的补充信息可以并存；明确纠正时才更新旧记录。特别重要的偏好可置顶，保证长期取用优先；记错时也可停用该条。私聊记忆只供对方使用，群聊中的公开原话供固定成员使用。</p>
    {source && <SourceMessageDialog key={`${worldId}:${source.conversation_id}:${source.message_id}`} client={client} worldId={worldId} conversationId={source.conversation_id} messageId={source.message_id} characters={characters} onClose={() => setSource(null)} />}
  </dialog>;
}
