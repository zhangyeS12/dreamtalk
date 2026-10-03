import { ContextReferencePanel } from "./ContextReferencePanel";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { MessageTime } from "./MessageTime";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatReplyAvailability, type ChatConversation } from "@dreamtalk/api-client";
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

interface Props {
  client: CoreClient;
  worldId: string;
  playerId: string;
  conversation: ChatConversation;
  tokenCeiling: number;
  suggestedDraft?: string | null;
  onSuggestionUsed?: () => void;
  onBack: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

export function ChatTranscript({ client, worldId, playerId, conversation, tokenCeiling, suggestedDraft, onSuggestionUsed, onBack, onDirtyChange }: Props) {
  const draftInput = useRef<HTMLTextAreaElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [longMemoryOpen, setLongMemoryOpen] = useState(false);
  const [referenceTurn, setReferenceTurn] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [availability, setAvailability] = useState<ChatReplyAvailability | null>(null);
  const available = availability?.available ?? false;
  const budgetFeedback = chatTokenReservationFeedback(availability, tokenCeiling, "direct");
  const [draft, setDraft] = useState("");
  const [pendingSend, setPendingSend] = useState<{ text: string; ceiling: number; requestId: string } | null>(null);
  const [phase, setPhase] = useState<ChatRequestPhase>(null);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const actionLock = useRef(false);
  const sending = phase !== null || recoveryBusy;
  useEffect(() => { onDirtyChange?.(Boolean(draft.trim() || pendingSend || sending)); }, [draft, pendingSend, sending, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const [feedback, setFeedback] = useState("");
  const [replyFailure, setReplyFailure] = useState<{ turnId: string; message: string } | null>(null);
  const stream = useReplyStream();
  const { messages, failed, hasOlder, loadingOlder, loadOlder, acceptMessage } = useTranscriptPages(client, worldId, conversation.conversation_id, refresh, true);
  const { thread, beforePrepend } = useChatScroll(messages, stream.draft?.text);

  const readAttempts = useRef(new Map<string, number>());
  useEffect(() => {
    let active = true;
    let reading = false;
    async function markRead() {
      if (reading || !active || document.visibilityState !== "visible" || !document.hasFocus()) return;
      const incoming = messages?.filter(message => message.story_sent_at_utc && (readAttempts.current.get(message.message_id) ?? 0) < 2) ?? [];
      if (!incoming.length) return;
      reading = true;
      try {
        if (isTauri() && !await invoke<boolean>("report_desktop_presence", { worldId, visible: true })) return;
        if (!active || !document.hasFocus()) return;
        for (const message of incoming) {
          readAttempts.current.set(message.message_id, (readAttempts.current.get(message.message_id) ?? 0) + 1);
          try { await client.markOfflineMessageRead(worldId, message.message_id);
            readAttempts.current.set(message.message_id, 2);
          } catch { /* One further visible-page read may retry acknowledgement; never model work. */ }
        }
      } catch { /* Hidden or disconnected UI never marks messages read. */ }
      finally { reading = false; }
    }
    const focused = () => { void markRead(); };
    window.addEventListener("focus", focused); void markRead();
    return () => { active = false; window.removeEventListener("focus", focused); };
  }, [client, worldId, messages]);

  useEffect(() => {
    if (suggestedDraft) {
      setDraft(suggestedDraft);
      onSuggestionUsed?.();
    }
  }, [suggestedDraft, onSuggestionUsed]);

  useEffect(() => {
    let active = true;
    setAvailability(null);
    void client.directReplyAvailability(worldId).then(result => {
      if (active) setAvailability(result);
    }).catch(() => { if (active) setAvailability(null); });
    return () => { active = false; };
  }, [client, worldId]);

  const visibleStreamDraft = stream.draft && (messages?.filter(message => message.turn_id === stream.draft?.turnId && message.sender_kind === "character").length ?? 0) <= stream.draft.index ? stream.draft : null;
  const latestPlayerMessage = messages?.filter(message => message.sender_kind === "player" && message.sender_id === playerId).at(-1);
  const checkReply = async () => {
    if (actionLock.current || sending || pendingSend || !latestPlayerMessage) return;
    actionLock.current = true;
    setPhase("checking");
    setFeedback("");
    try {
      const recovery = await client.replyRecovery(worldId, conversation.conversation_id, latestPlayerMessage.turn_id);
      const turn = await client.directTurn(worldId, conversation.conversation_id, recovery.attempt_turn_id);
      setRefresh(value => value + 1);
      setFeedback(turn.state !== "completed" && replyFailure?.turnId === turn.turn_id
        ? replyFailure.message
        : chatReplyStateFeedback(turn.state, "direct"));
    } catch { setFeedback(chatReplyStateFeedback(null, "direct")); }
    finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  const generateSavedReply = async (turnId: string) => {
    if (actionLock.current || pendingSend || !available) return;
    actionLock.current = true;
    setPhase("replying"); setFeedback(""); setReplyFailure(null);
    try {
      await stream.run(client, worldId, conversation.conversation_id, turnId, "direct", [conversation.character_id], acceptMessage);
      if (stream.isMounted()) setRefresh(value => value + 1);
    } catch (failure) {
      if (!stream.isMounted()) return;
      setPhase("checking");
      const turn = await client.directTurn(worldId, conversation.conversation_id, turnId).catch(() => null);
      if (!stream.isMounted()) return;
      setRefresh(value => value + 1);
      const message = turn?.state === "completed" ? chatReplyStateFeedback(turn.state, "direct") : chatReplyFailureFeedback(failure, "direct");
      setFeedback(message);
      if (turn?.state !== "completed") setReplyFailure({ turnId, message });
    } finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (actionLock.current || sending || !available || (!draft.trim() && !pendingSend)) return;
    if (budgetFeedback && !pendingSend) { setFeedback(budgetFeedback); return; }
    actionLock.current = true;
    const current = pendingSend ?? { text: draft, ceiling: tokenCeiling, requestId: crypto.randomUUID() };
    setPendingSend(current);
    setPhase("saving");
    setFeedback("");
    try {
      const sent = await client.sendPlayerMessage(worldId, conversation.conversation_id, current.text, current.ceiling, current.requestId);
      setPendingSend(null);
      if (!stream.isMounted()) return;
      setDraft("");
      setReplyFailure(null);
      setRefresh(value => value + 1);
      setPhase("replying");
      try {
        await stream.run(client, worldId, conversation.conversation_id, sent.turn_id, "direct", [conversation.character_id], acceptMessage);
        setRefresh(value => value + 1);
      } catch (failure) {
        if (!stream.isMounted()) return;
        // Query once for a completed reply; never replay an uncertain model call.
        setPhase("checking");
        const turn = await client.directTurn(worldId, conversation.conversation_id, sent.turn_id).catch(() => null);
        setRefresh(value => value + 1);
        const message = turn?.state === "completed"
          ? chatReplyStateFeedback(turn.state, "direct")
          : stream.wasStopped()
            ? "已请求停止生成。已保存的发言会保留；可检查回复状态，系统不会自动重新调用模型。"
            : chatReplyFailureFeedback(failure, "direct");
        setFeedback(message);
        if (turn?.state !== "completed") setReplyFailure({ turnId: sent.turn_id, message });
      }
    } catch (failure) {
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500) {
        setPendingSend(null);
        setFeedback(chatSaveFailureFeedback(failure));
      } else {
        setFeedback("消息保存结果尚未确认。可重试保存同一条消息，不会创建重复回合。");
      }
    } finally {
      actionLock.current = false;
      if (stream.isMounted()) setPhase(null);
    }
  };

  return <section ref={thread} className="chat-thread" aria-label={`${conversation.character_name}的会话`}>
    <div className="thread-heading">
      <button type="button" className="text-action" onClick={onBack}>返回聊天</button>
      <h2>{conversation.character_name}</h2><span>私聊</span>
      <button type="button" className="text-action transcript-refresh" onClick={() => setLongMemoryOpen(true)}>长期记忆</button><button type="button" className="text-action transcript-refresh" onClick={() => setMemoryOpen(true)}>会话摘要</button><button type="button" className="text-action transcript-refresh" onClick={() => setHistoryOpen(true)}>聊天回忆</button><button type="button" className="text-action transcript-refresh" onClick={() => setRefresh(value => value + 1)}>刷新记录</button>
    </div>
    {referenceTurn ? <ContextReferencePanel key={`${worldId}:${conversation.conversation_id}:${referenceTurn}`} client={client} worldId={worldId} conversationId={conversation.conversation_id} turnId={referenceTurn} names={new Map([[conversation.character_id, conversation.character_name]])} onClose={() => setReferenceTurn(null)} /> : null}
    {longMemoryOpen ? <LongChatMemoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} characters={[{ character_id: conversation.character_id, character_name: conversation.character_name }]} onClose={() => setLongMemoryOpen(false)} /> : null}
    {memoryOpen ? <ConversationMemoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} senderName={message => message.sender_kind === "player" && message.sender_id === playerId ? "我" : conversation.character_name} canGenerate={!sending && !pendingSend} onClose={() => setMemoryOpen(false)} /> : null}
    {historyOpen ? <ChatHistoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} senderName={message => message.sender_kind === "player" && message.sender_id === playerId ? "我" : conversation.character_name} canQuote={available && !sending && !pendingSend} onClose={() => setHistoryOpen(false)} onQuote={text => {
      if (!available || sending || pendingSend) return false;
      const combined = draft.trim() ? `${draft}\n\n${text}` : text;
      if (new TextEncoder().encode(combined).byteLength > 65536) return false;
      setDraft(combined); setHistoryOpen(false);
      requestAnimationFrame(() => { draftInput.current?.focus(); draftInput.current?.scrollIntoView({ block: "nearest" }); });
      return true;
    }} /> : null}
    {failed ? <p className="thread-hint" role="alert">无法读取会话记录，请刷新后重试。</p> : null}
    {messages === null ? failed ? null : <p className="thread-hint">正在读取消息…</p>
        : messages.length === 0 ? <div className="conversation-placeholder"><h2>还没有消息</h2><p>发一条消息，开始与角色聊天。</p></div>
          : <>{hasOlder ? <div className="transcript-history"><button type="button" className="text-action" disabled={loadingOlder} onClick={() => void loadOlder(beforePrepend)}>{loadingOlder ? "正在加载…" : "加载更早消息"}</button></div> : null}<ol className="message-list">{messages.map(message => {
            const own = message.sender_kind === "player" && message.sender_id === playerId;
            return <li key={message.message_id} className={`message-row ${own ? "own" : ""}`}>
              <div className="message-bubble">
                <span className="message-sender">{own ? "我" : conversation.character_name}</span>
                <ChatMessageBody text={message.text} />
                <MessageTime message={message} />{!own ? <button type="button" className="text-action message-reference" onClick={() => setReferenceTurn(message.turn_id)}>本次参考内容</button> : null}
              </div>
            </li>;
          })}{visibleStreamDraft ? <StreamingReplyBubble name={conversation.character_name} text={visibleStreamDraft.text} /> : null}</ol></>}
    <form className="chat-composer" onSubmit={event => void send(event)}>
      {phase || feedback ? <p role="status" aria-live="polite" className="chat-feedback">{(phase === "replying" && stream.stage === "preparing" ? "消息已保存，正在准备角色回复…" : chatPhaseFeedback(phase, "direct")) || feedback}</p> : null}
      <ReplyRecoveryControls client={client} worldId={worldId} conversationId={conversation.conversation_id} sourceTurnId={latestPlayerMessage?.turn_id} refresh={refresh} tokenCeiling={tokenCeiling} blocked={!available || phase !== null || !!pendingSend} onGenerate={generateSavedReply} onBusyChange={setRecoveryBusy} />
      {budgetFeedback ? <p className="chat-feedback" role="alert">{budgetFeedback}</p> : null}
      {!available ? <p className="chat-feedback">尚未配置可用的聊天模型或路由及可信 Token 上限，暂时无法发送。</p> : null}
      <label htmlFor="direct-chat-draft" className="sr-only">发送给{conversation.character_name}的消息</label>
      <textarea ref={draftInput} id="direct-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={!available || sending || !!pendingSend} maxLength={65536} placeholder="输入消息…" rows={3} />
      <div className="chat-composer-actions"><small>回车发送 · Shift+回车换行 · 本轮输入与输出共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small>{latestPlayerMessage ? <button type="button" className="text-action" disabled={sending || !!pendingSend} onClick={() => void checkReply()}>检查回复状态</button> : null}{phase === "replying" ? <button type="button" className="text-action" disabled={stream.stopping} onClick={stream.stop}>{stream.stopping ? "正在停止…" : "停止生成"}</button> : null}<button type="submit" className="primary-button" disabled={!available || sending || (!!budgetFeedback && !pendingSend) || (!draft.trim() && !pendingSend)}>{phase === "saving" ? "正在保存…" : phase === "replying" ? "等待回复…" : phase === "checking" ? "检查中…" : pendingSend ? "重试保存" : "发送"}</button></div>
    </form>
  </section>;
}
