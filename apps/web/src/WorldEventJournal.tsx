import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type ChatStoryEntry, type KnownWorldEvent, type NewsMark, type PublicNewsEntry, type WorldStoryEntries } from "@dreamtalk/api-client";

const kinds = { activity: "活动", plan: "计划", rumor: "传闻", invitation: "邀请", change: "变更" };
const marks = { pending: "未经历", experienced: "已经历", skipped: "跳过" };

export function WorldEventJournal({ client, worldId, witnessed, onTopic, displayTime }: {
  client: CoreClient; worldId: string; witnessed: KnownWorldEvent[];
  onTopic: (event: KnownWorldEvent) => void; displayTime: (time: string) => string;
}) {
  const [entries, setEntries] = useState<WorldStoryEntries | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const olderEntries = useRef<ChatStoryEntry[]>([]);
  const olderCursor = useRef<string | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<ChatStoryEntry | null>(null);
  const [correction, setCorrection] = useState("");
  const busyRef = useRef(false);
  const serial = useRef(0);
  const alive = useRef(true);
  const refresh = useCallback(async () => {
    if (busyRef.current) return;
    const request = ++serial.current;
    try {
      const next = await client.worldStories(worldId);
      if (alive.current && request === serial.current) {
        setEntries({ ...next, chat: [...next.chat, ...olderEntries.current.filter(item => !next.chat.some(newer => newer.entry_id === item.entry_id))], next_before: olderCursor.current === undefined ? next.next_before : olderCursor.current });
        setLoadError("");
      }
    } catch { if (alive.current && request === serial.current) setLoadError("未能读取世界事件，请检查核心连接后刷新。"); }
  }, [client, worldId]);
  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { alive.current = false; ++serial.current; window.clearInterval(timer); };
  }, [refresh]);

  async function act(operation: () => Promise<unknown>, removed?: string, corrected?: ChatStoryEntry) {
    if (busyRef.current) return;
    busyRef.current = true; ++serial.current; setBusy(true); setError("");
    try {
      await operation();
      if (alive.current) {
        if (corrected) {
          olderEntries.current = olderEntries.current.map(item => item.entry_id === corrected.entry_id ? corrected : item);
          setEntries(current => current ? { ...current, chat: current.chat.map(item => item.entry_id === corrected.entry_id ? corrected : item) } : current);
        }
        if (removed) olderEntries.current = olderEntries.current.filter(item => item.entry_id !== removed);
        if (removed) setEntries(current => current ? { ...current, chat: current.chat.filter(item => item.entry_id !== removed) } : current);
        setEditing(null);
      }
    } catch (failure) {
      if (alive.current) setError(failure instanceof CoreRequestError && failure.status === 409 ? "记录已变化，请刷新后重试。" : "未能保存，请检查核心连接后刷新；未自动重试。");
    } finally {
      busyRef.current = false;
      if (alive.current) { setBusy(false); await refresh(); }
    }
  }

  async function older() {
    if (!entries?.next_before || busyRef.current) return;
    const cursor = entries.next_before;
    await act(async () => {
      const next = await client.worldStories(worldId, cursor);
      if (alive.current) { olderEntries.current = [...olderEntries.current, ...next.chat.filter(item => !olderEntries.current.some(existing => existing.entry_id === item.entry_id))]; olderCursor.current = next.next_before; setEntries(current => current ? { ...current, chat: [...current.chat, ...next.chat.filter(item => !current.chat.some(existing => existing.entry_id === item.entry_id))], next_before: next.next_before } : next); }
    });
  }

  const topic = (item: PublicNewsEntry) => onTopic({ event_id: item.event_id, title: item.title, description: item.body, occurred_at: item.occurred_at, observed_at: item.occurred_at, ledger_position: 0 });
  return <div className="world-journal">
    <div className="journal-refresh"><p>历史记录有时间范围，旧消息不代表角色此刻仍在做同一件事。</p><button type="button" className="secondary-button" disabled={busy} onClick={() => void refresh()}>刷新事件</button></div>
    {(error || loadError) && <p role="alert" className="product-error">{error || loadError}</p>}
    <section aria-labelledby="chat-events-title"><h3 id="chat-events-title">聊天获知</h3><p className="inline-hint">在角色回复的同一次请求中提取具体活动、计划、传闻和邀请。先适配 DeepSeek；原话保留，AI 的归类需要你核对。</p>
      {!entries ? <p>正在读取……</p> : entries.chat.length === 0 ? <p className="thread-hint">还没有从聊天中记录事件。普通寒暄不会记录，旧聊天不会自动补录。</p> : <ol className="event-list">{entries.chat.map(item => <li key={item.entry_id} className="event-item">
        <div className="journal-entry-heading"><strong>{item.title}</strong><span>{kinds[item.kind]} · {item.character_name}</span></div>
        <blockquote>{item.quote}</blockquote><small>获知时间：<time dateTime={item.learned_at}>{new Date(item.learned_at).toLocaleString()}</time></small><small>获知时的世界时间：{item.learned_world_time !== null ? displayTime(item.learned_world_time) : "未记录"}</small><small>事件时间（原话）：{item.time_text || "原话未明确时间"}</small>
        {entries.chat.some(newer => newer.updates_entry_id === item.entry_id) && <small>后来有变更记录；此条保留当时的信息。</small>}
        {item.updates_entry_id && <small>关联旧记录：{entries.chat.find(old => old.entry_id === item.updates_entry_id)?.title || "较早的计划"}；旧记录保留。</small>}
        {item.correction && <p className="inline-hint">我的批注：{item.correction}</p>}
        <details><summary>来源原话</summary><p>会话 {item.conversation_id} · 消息 {item.message_id}</p>{item.source_event_id && <p>已授权事件引用：{item.source_event_id}</p>}<p>这是角色当时告诉你的说法，计划或传闻不代表已发生或已证实。</p></details>
        <div className="journal-entry-actions"><button type="button" className="text-action" disabled={busy} onClick={() => { setEditing(item); setCorrection(item.correction || ""); }}>批注／纠正</button><button type="button" className="text-action" disabled={busy} onClick={() => { if (window.confirm("从事件列表移除此条记录？聊天原文会保留。")) void act(() => client.correctChatStory(worldId, item, item.correction, true), item.entry_id); }}>移除记录</button></div>
        {editing?.entry_id === item.entry_id && <form onSubmit={event => { event.preventDefault(); void act(() => client.correctChatStory(worldId, item, correction.trim() || null), undefined, { ...item, correction: correction.trim() || null, revision: item.revision + 1 }); }}><label className="field"><span>补充或纠正（保留原话，不修改原始聊天）</span><textarea maxLength={500} value={correction} onChange={event => setCorrection(event.target.value)} /></label><button type="submit" className="primary-button" disabled={busy}>保存批注</button><button type="button" className="text-action" disabled={busy} onClick={() => setEditing(null)}>取消</button></form>}
      </li>)}</ol>}
      {entries?.next_before && <button type="button" className="secondary-button" disabled={busy} onClick={() => void older()}>读取更早记录</button>}
      <details className="witnessed-events"><summary>我亲历的活动记录（{witnessed.length}）</summary><ol className="event-list">{witnessed.map(item => <li key={item.event_id} className="event-item"><time>{displayTime(item.occurred_at)}</time><strong>{item.title}</strong>{item.description && <p>{item.description}</p>}<small>获知于 {displayTime(item.observed_at)}</small><button type="button" className="text-action" onClick={() => onTopic(item)}>聊聊这件事</button></li>)}</ol></details>
    </section>
    <section aria-labelledby="public-events-title"><h3 id="public-events-title">世界动态</h3><p className="inline-hint">公共动态分批生成、逐条发布。由你标记经历情况；显示出来不会自动变绿。每批达到 80% 的“已经历／跳过”后补充一批。</p>
      {!entries ? <p>正在读取……</p> : entries.news.length === 0 ? <p className="thread-hint">还没有已发布动态。先在设置中确认世界书的公共背景，再开启“世界动态事件池”。</p> : <ol className="event-list">{entries.news.map(item => <li key={item.entry_id} className={`event-item news-item news-${item.state}`}>
        <div className="news-copy"><strong>{item.title}</strong><p>{item.body}</p><small>发布于 {displayTime(item.occurred_at)}</small>{item.time_text && <small>活动时间：{item.time_text}</small>}<button type="button" className="text-action" onClick={() => topic(item)}>聊聊这件事</button></div>
        <div className="news-marks" role="group" aria-label={`经历状态：${item.title}`}>{(["pending", "experienced", "skipped"] as NewsMark[]).map(mark => <button type="button" key={mark} className={`news-mark mark-${mark}`} aria-pressed={item.state === mark} disabled={busy || item.state === mark} onClick={() => void act(() => client.markWorldNews(worldId, item, mark))}>{marks[mark]}</button>)}</div>
      </li>)}</ol>}
    </section>
  </div>;
}
