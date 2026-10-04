import { useConversationRead } from "./useChatUnread";
import { ContextReferencePanel } from "./ContextReferencePanel";
import { MessageTime } from "./MessageTime";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatReplyAvailability, type GroupChatConversation, type WorldContentItem } from "@dreamtalk/api-client";
import { useReplyStream } from "./useReplyStream";
import { ReplyRecoveryControls } from "./ReplyRecoveryControls";
import { StreamingReplyBubble } from "./StreamingReplyBubble";
import { useChatScroll } from "./useChatScroll";
import { useTranscriptPages } from "./useTranscriptPages";
import { ChatMessageBody } from "./ChatMessageBody";
import { ChatHistoryPanel } from "./ChatHistoryPanel";
import { LongChatMemoryPanel } from "./LongChatMemoryPanel";
import { ConversationMemoryPanel } from "./ConversationMemoryPanel";
import { submitChatOnEnter } from "./chatComposerKeys";
import { chatTokenReservationFeedback, chatPhaseFeedback, chatReplyFailureFeedback, chatReplyStateFeedback, chatSaveFailureFeedback, type ChatRequestPhase } from "./chatFeedback";

export function GroupChatSetup({ client, worldId, onCreated, onBack, onDirtyChange }: {
  client: CoreClient;
  worldId: string;
  onCreated: (group: GroupChatConversation) => void;
  onBack: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [contacts, setContacts] = useState<WorldContentItem[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState<{ importIds: string[]; requestId: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { onDirtyChange?.(selected.length > 0 || !!pending || saving); }, [selected, pending, saving, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  useEffect(() => {
    let active = true;
    void client.worldContent(worldId).then(items => {
      if (active) setContacts(items.filter(item => item.kind === "character" && item.characters.length === 1));
    }).catch(() => { if (active) setError("无法读取当前世界的角色，请重试。"); });
    return () => { active = false; };
  }, [client, worldId]);

  const toggle = (importId: string) => {
    if (pending) return;
    setSelected(current => current.includes(importId) ? current.filter(id => id !== importId) : [...current, importId]);
  };
  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || (!pending && selected.length < 2)) return;
    const attempt = pending ?? { importIds: selected, requestId: crypto.randomUUID() };
    setPending(attempt);
    setSaving(true);
    setError("");
    try {
      onCreated(await client.createGroupConversation(worldId, attempt.importIds, attempt.requestId));
      setPending(null);
    } catch (failure) {
      if (failure instanceof CoreRequestError && [404, 409, 422].includes(failure.status)) {
        setPending(null);
        setError("所选角色已变化或不属于当前世界。请重新选择成员。");
      } else {
        setError("群聊保存结果尚未确认。可以重试同一次创建，不会重复建立会话。");
      }
    } finally { setSaving(false); }
  };

  return <section className="group-setup" aria-label="创建群聊">
    <div className="thread-heading"><button type="button" className="text-action" onClick={onBack}>返回聊天</button><h2>新建群聊</h2></div>
    <form onSubmit={event => void create(event)}>
      <p className="inline-hint">从当前世界选择至少两位角色。聊天时可以用 @角色名 指定下一位发言者。</p>
      {contacts === null ? <p className="thread-hint">正在读取角色…</p> : contacts.length < 2 ? <p className="thread-hint">当前世界至少需要两张已确认的角色卡。</p> : <div className="group-contact-list">{contacts.map(item => <label key={item.import_id} className="group-contact"><input type="checkbox" checked={selected.includes(item.import_id)} disabled={saving || !!pending} onChange={() => toggle(item.import_id)} /><span>{item.characters[0].name}</span></label>)}</div>}
      {error ? <p className="app-alert" role="alert">{error}</p> : null}
      <div className="group-actions"><button type="submit" className="primary-button" disabled={saving || (selected.length < 2 && !pending)}>{saving ? "正在创建…" : pending ? "重试创建" : "创建群聊"}</button></div>
    </form>
  </section>;
}

export function GroupChatDetails({ client, worldId, playerId, group, tokenCeiling, suggestedDraft, onSuggestionUsed, onBack, onDirtyChange }: {
  client: CoreClient; worldId: string; playerId: string; group: GroupChatConversation; tokenCeiling: number;
  suggestedDraft?: string | null; onSuggestionUsed?: () => void; onBack: () => void; onDirtyChange?: (dirty: boolean) => void;
}) {
  const draftInput = useRef<HTMLTextAreaElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [longMemoryOpen, setLongMemoryOpen] = useState(false);
  const [referenceTurn, setReferenceTurn] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [availability, setAvailability] = useState<ChatReplyAvailability | null>(null);
  const [availabilityReading, setAvailabilityReading] = useState(true);
  const [availabilityFailed, setAvailabilityFailed] = useState(false);
  const available = availability?.available === true && !availabilityReading && !availabilityFailed;
  const budgetFeedback = chatTokenReservationFeedback(availability, tokenCeiling, "group");
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<{ text: string; ceiling: number; requestId: string } | null>(null);
  const [phase, setPhase] = useState<ChatRequestPhase>(null);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const actionLock = useRef(false);
  const sending = phase !== null || recoveryBusy;
  useEffect(() => { onDirtyChange?.(Boolean(draft.trim() || pending || sending)); }, [draft, pending, sending, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const [feedback, setFeedback] = useState("");
  const [replyFailure, setReplyFailure] = useState<{ turnId: string; message: string } | null>(null);
  const stream = useReplyStream();
  const { messages, failed, hasOlder, loadingOlder, loadOlder, acceptMessage } = useTranscriptPages(client, worldId, group.conversation_id, refresh, true);
  useConversationRead(client, worldId, group.conversation_id, messages);
  const { thread, beforePrepend } = useChatScroll(messages, stream.draft?.text);

  useEffect(() => {
    if (suggestedDraft) {
      setDraft(suggestedDraft);
      onSuggestionUsed?.();
    }
  }, [suggestedDraft, onSuggestionUsed]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setAvailabilityReading(true); setAvailabilityFailed(false);
    void client.groupReplyAvailability(worldId, controller.signal)
      .then(result => { if (active) setAvailability(result); })
      .catch(() => { if (active) setAvailabilityFailed(true); })
      .finally(() => { if (active) setAvailabilityReading(false); });
    return () => { active = false; controller.abort(); };
  }, [client, worldId, refresh]);

  const visibleStreamDraft = stream.draft && (messages?.filter(message => message.turn_id === stream.draft?.turnId && message.sender_kind === "character").length ?? 0) <= stream.draft.index ? stream.draft : null;
  const latestPlayerMessage = messages?.filter(message => message.sender_kind === "player" && message.sender_id === playerId).at(-1);
  const checkReply = async () => {
    if (actionLock.current || sending || pending || !latestPlayerMessage) return;
    actionLock.current = true;
    setPhase("checking");
    setFeedback("");
    try {
      const recovery = await client.replyRecovery(worldId, group.conversation_id, latestPlayerMessage.turn_id);
      const turn = await client.groupTurn(worldId, group.conversation_id, recovery.attempt_turn_id);
      setRefresh(value => value + 1);
      setFeedback(turn.state !== "completed" && replyFailure?.turnId === turn.turn_id
        ? replyFailure.message
        : chatReplyStateFeedback(turn.state, "group"));
    } catch { setFeedback(chatReplyStateFeedback(null, "group")); }
    finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  const generateSavedReply = async (turnId: string) => {
    if (actionLock.current || pending || !available) return;
    actionLock.current = true;
    setPhase("replying"); setFeedback(""); setReplyFailure(null);
    try {
      await stream.run(client, worldId, group.conversation_id, turnId, "group", group.participants.map(item => item.character_id), acceptMessage);
      if (stream.isMounted()) setRefresh(value => value + 1);
    } catch (failure) {
      if (!stream.isMounted()) return;
      setPhase("checking");
      const turn = await client.groupTurn(worldId, group.conversation_id, turnId).catch(() => null);
      if (!stream.isMounted()) return;
      setRefresh(value => value + 1);
      const message = turn?.state === "completed" ? chatReplyStateFeedback(turn.state, "group") : chatReplyFailureFeedback(failure, "group");
      setFeedback(message);
      if (turn?.state !== "completed") setReplyFailure({ turnId, message });
    } finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (actionLock.current || sending || !available || (!draft.trim() && !pending)) return;
    if (budgetFeedback && !pending) { setFeedback(budgetFeedback); return; }
    actionLock.current = true;
    const current = pending ?? { text: draft, ceiling: tokenCeiling, requestId: crypto.randomUUID() };
    setPending(current);
    setPhase("saving");
    setFeedback("");
    try {
      const sent = await client.sendGroupMessage(worldId, group.conversation_id, current.text, current.ceiling, current.requestId);
      setPending(null);
      if (!stream.isMounted()) return;
      setDraft("");
      setReplyFailure(null);
      setRefresh(value => value + 1);
      setPhase("replying");
      try {
        await stream.run(client, worldId, group.conversation_id, sent.turn_id, "group", group.participants.map(item => item.character_id), acceptMessage);
        setRefresh(value => value + 1);
      } catch (failure) {
        if (!stream.isMounted()) return;
        setPhase("checking");
        const turn = await client.groupTurn(worldId, group.conversation_id, sent.turn_id).catch(() => null);
        setRefresh(value => value + 1);
        const message = turn?.state === "completed"
          ? chatReplyStateFeedback(turn.state, "group")
          : stream.wasStopped()
            ? "已请求停止生成。已保存的发言会保留；可检查回复状态，系统不会自动重新调用模型。"
            : chatReplyFailureFeedback(failure, "group");
        setFeedback(message);
        if (turn?.state !== "completed") setReplyFailure({ turnId: sent.turn_id, message });
      }
    } catch (failure) {
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500) {
        setPending(null);
        setFeedback(chatSaveFailureFeedback(failure));
      } else {
        setFeedback("消息保存结果尚未确认。可重试保存同一条消息，不会创建重复回合。");
      }
    } finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  const insertMention = (name: string) => {
    if (!available || sending || pending) return;
    const input = draftInput.current;
    const start = input?.selectionStart ?? draft.length;
    const end = input?.selectionEnd ?? start;
    const before = draft.slice(0, start);
    const after = draft.slice(end);
    const insertion = `${before && !/\s$/.test(before) ? " " : ""}@${name}${after && /^\s/.test(after) ? "" : " "}`;
    if (before.length + insertion.length + after.length > 65536) return;
    setDraft(before + insertion + after);
    const caret = before.length + insertion.length;
    requestAnimationFrame(() => { input?.focus(); input?.setSelectionRange(caret, caret); });
  };

  const names = new Map(group.participants.map(item => [item.character_id, item.character_name]));
  const nameCounts = new Map<string, number>();
  for (const item of group.participants) nameCounts.set(item.character_name, (nameCounts.get(item.character_name) ?? 0) + 1);
  const mentionable = group.participants.filter(item => nameCounts.get(item.character_name) === 1);
  return <section ref={thread} className="chat-thread" aria-label="群聊">
    <div className="thread-heading"><button type="button" className="text-action" onClick={onBack}>返回聊天</button><h2>{group.participants.map(item => item.character_name).join("、")}</h2><span>群聊</span><button type="button" className="text-action transcript-refresh" onClick={() => setLongMemoryOpen(true)}>长期记忆</button><button type="button" className="text-action transcript-refresh" onClick={() => setMemoryOpen(true)}>会话摘要</button><button type="button" className="text-action transcript-refresh" onClick={() => setHistoryOpen(true)}>聊天回忆</button><button type="button" className="text-action transcript-refresh" onClick={() => setRefresh(value => value + 1)}>刷新记录</button></div>
    {referenceTurn ? <ContextReferencePanel key={`${worldId}:${group.conversation_id}:${referenceTurn}`} client={client} worldId={worldId} conversationId={group.conversation_id} turnId={referenceTurn} names={names} onClose={() => setReferenceTurn(null)} /> : null}
    {longMemoryOpen ? <LongChatMemoryPanel client={client} worldId={worldId} conversationId={group.conversation_id} characters={group.participants} onClose={() => setLongMemoryOpen(false)} /> : null}
    {memoryOpen ? <ConversationMemoryPanel client={client} worldId={worldId} conversationId={group.conversation_id} senderName={message => message.sender_kind === "player" && message.sender_id === playerId ? "我" : names.get(message.sender_id) ?? "角色"} canGenerate={!sending && !pending} onClose={() => setMemoryOpen(false)} /> : null}
    {historyOpen ? <ChatHistoryPanel client={client} worldId={worldId} conversationId={group.conversation_id} senderName={message => message.sender_kind === "player" && message.sender_id === playerId ? "我" : names.get(message.sender_id) ?? "角色"} canQuote={available && !sending && !pending} onClose={() => setHistoryOpen(false)} onQuote={text => {
      if (!available || sending || pending) return false;
      const combined = draft.trim() ? `${draft}\n\n${text}` : text;
      if (new TextEncoder().encode(combined).byteLength > 65536) return false;
      setDraft(combined); setHistoryOpen(false);
      requestAnimationFrame(() => { draftInput.current?.focus(); draftInput.current?.scrollIntoView({ block: "nearest" }); });
      return true;
    }} /> : null}
    {failed ? <p className="thread-hint" role="alert">无法读取群聊记录，请刷新后重试。</p> : null}
    {messages === null ? failed ? null : <p className="thread-hint">正在读取消息…</p> : messages.length === 0 ? <div className="conversation-placeholder"><h2>还没有消息</h2><p>发一条消息，开始群聊。</p></div> : <>{hasOlder ? <div className="transcript-history"><button type="button" className="text-action" disabled={loadingOlder} onClick={() => void loadOlder(beforePrepend)}>{loadingOlder ? "正在加载…" : "加载更早消息"}</button></div> : null}<ol className="message-list">{messages.map(message => {
      const own = message.sender_kind === "player" && message.sender_id === playerId;
      return <li key={message.message_id} data-message-id={message.message_id} className={`message-row ${own ? "own" : ""}`}><div className="message-bubble"><span className="message-sender">{own ? "我" : names.get(message.sender_id) ?? "角色"}</span><ChatMessageBody text={message.text} /><MessageTime message={message} />{!own ? <button type="button" className="text-action message-reference" onClick={() => setReferenceTurn(message.turn_id)}>本次参考内容</button> : null}</div></li>;
    })}{visibleStreamDraft ? <StreamingReplyBubble name={names.get(visibleStreamDraft.speakerId) ?? "角色"} text={visibleStreamDraft.text} /> : null}</ol></>}
    <form className="chat-composer" onSubmit={event => void send(event)}>
      {phase || feedback ? <p role="status" aria-live="polite" className="chat-feedback">{(phase === "replying" && stream.stage === "selecting" ? "正在选择下一位发言者…" : chatPhaseFeedback(phase, "group")) || feedback}</p> : null}
      <ReplyRecoveryControls client={client} worldId={worldId} conversationId={group.conversation_id} sourceTurnId={latestPlayerMessage?.turn_id} refresh={refresh} tokenCeiling={tokenCeiling} blocked={!available || phase !== null || !!pending} onGenerate={generateSavedReply} onBusyChange={setRecoveryBusy} />
      {budgetFeedback ? <p className="chat-feedback" role="alert">{budgetFeedback}</p> : null}
      {availabilityReading ? <p className="chat-feedback" role="status">正在核对聊天模型状态…</p>
        : availabilityFailed ? <p className="chat-feedback" role="alert">未能读取聊天模型状态，请点击“刷新记录”重试；这不代表配置已丢失。</p>
        : !available ? <p className="chat-feedback">当前聊天模型尚不可用，请在设置中核对模型与路由。</p> : null}
      <label htmlFor="group-chat-draft" className="sr-only">发送群聊消息</label>
      <textarea ref={draftInput} id="group-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={!available || sending || !!pending} maxLength={65536} placeholder="输入消息，或用 @角色名 指定下一位发言者…" rows={3} />
      {mentionable.length > 0 ? <div className="chat-mention-actions"><span>指定下一位</span>{mentionable.map(item => <button key={item.character_id} type="button" disabled={!available || sending || !!pending} onClick={() => insertMention(item.character_name)}>@{item.character_name}</button>)}</div> : null}
      <div className="chat-composer-actions"><small>回车发送 · Shift+回车换行 · 本轮所有发言共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small>{latestPlayerMessage ? <button type="button" className="text-action" disabled={sending || !!pending} onClick={() => void checkReply()}>检查回复状态</button> : null}{phase === "replying" ? <button type="button" className="text-action" disabled={stream.stopping} onClick={stream.stop}>{stream.stopping ? "正在停止…" : "停止生成"}</button> : null}<button type="submit" className="primary-button" disabled={!available || sending || (!!budgetFeedback && !pending) || (!draft.trim() && !pending)}>{phase === "saving" ? "正在保存…" : phase === "replying" ? "等待回复…" : phase === "checking" ? "检查中…" : pending ? "重试保存" : "发送"}</button></div>
    </form>
  </section>;
}
