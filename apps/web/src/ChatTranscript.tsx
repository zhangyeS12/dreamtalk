import { useConversationRead } from "./useChatUnread";
import { ContextReferencePanel } from "./ContextReferencePanel";
import { MessageTime } from "./MessageTime";
import { Fragment, useRef, useState } from "react";
import { CoreClient, type ChatConversation } from "@dreamtalk/api-client";
import { useChatReplyWorkflow } from "./useChatReplyWorkflow";
import { ReplyRecoveryControls } from "./ReplyRecoveryControls";
import { StreamingReplyBubble } from "./StreamingReplyBubble";
import { useChatScroll } from "./useChatScroll";
import { ChatMessageBody } from "./ChatMessageBody";
import { ChatHistoryPanel } from "./ChatHistoryPanel";
import { LongChatMemoryPanel } from "./LongChatMemoryPanel";
import { ConversationMemoryPanel } from "./ConversationMemoryPanel";
import { submitChatOnEnter } from "./chatComposerKeys";
import { chatPhaseFeedback } from "./chatFeedback";

import { ConversationHeading, transcriptDay } from "./ConversationHeading";
import { ContactAvatar } from "./ContactSocial";
import { FileExportDialog } from "./FileExportDialog";

interface Props {
  client: CoreClient;
  worldId: string;
  playerId: string;
  conversation: ChatConversation;
  avatarUrl?: string;
  tokenCeiling: number;
  suggestedDraft?: string | null;
  onSuggestionUsed?: () => void;
  onBack: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

export function ChatTranscript({ client, worldId, playerId, conversation, avatarUrl, tokenCeiling, suggestedDraft, onSuggestionUsed, onBack, onDirtyChange }: Props) {
  const draftInput = useRef<HTMLTextAreaElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [longMemoryOpen, setLongMemoryOpen] = useState(false);
  const [referenceTurn, setReferenceTurn] = useState<string | null>(null);
  const {
    refresh, setRefresh, available, availabilityReading, availabilityFailed, budgetFeedback,
    draft, setDraft, pending: pendingSend, phase, sending, setRecoveryBusy, feedback, stream,
    messages, failed, hasOlder, loadingOlder, loadOlder, followingLatest, showLatest, visibleStreamDraft,
    latestPlayerMessage, checkReply, generateSavedReply, send,
  } = useChatReplyWorkflow({
    client, worldId, playerId, conversationId: conversation.conversation_id, kind: "direct", readOnly: conversation.read_only,
    speakers: [conversation.character_id], tokenCeiling, suggestedDraft, onSuggestionUsed, onDirtyChange,
  });
  const readReceipt = useConversationRead(client, worldId, conversation.conversation_id, messages);
  const { thread, beforePrepend, followBottom } = useChatScroll(messages, visibleStreamDraft?.text);

  return <section ref={thread} className="chat-thread" aria-label={`${conversation.character_name}的会话`}>
    <ConversationHeading title={conversation.character_name} kind="私聊" portrait={<ContactAvatar name={conversation.character_name} url={avatarUrl} />}
      onBack={onBack} onRefresh={() => setRefresh(value => value + 1)} onLongMemory={() => setLongMemoryOpen(true)}
      onMemory={() => setMemoryOpen(true)} onHistory={() => setHistoryOpen(true)} onExport={() => setExportOpen(true)} />
    {exportOpen && <FileExportDialog client={client} worldId={worldId} conversationId={conversation.conversation_id} onClose={() => setExportOpen(false)} />}
    {referenceTurn ? <ContextReferencePanel key={`${worldId}:${conversation.conversation_id}:${referenceTurn}`} client={client} worldId={worldId} conversationId={conversation.conversation_id} turnId={referenceTurn} names={new Map([[conversation.character_id, conversation.character_name]])} onClose={() => setReferenceTurn(null)} /> : null}
    {longMemoryOpen ? <LongChatMemoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} characters={[{ character_id: conversation.character_id, character_name: conversation.character_name }]} onClose={() => setLongMemoryOpen(false)} /> : null}
    {memoryOpen ? <ConversationMemoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} senderName={message => message.sender_kind === "player" && message.sender_id === playerId ? "我" : conversation.character_name} canGenerate={!conversation.read_only && !sending && !pendingSend} onClose={() => setMemoryOpen(false)} /> : null}
    {historyOpen ? <ChatHistoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} senderName={message => message.sender_kind === "player" && message.sender_id === playerId ? "我" : conversation.character_name} canQuote={available && !sending && !pendingSend} onClose={() => setHistoryOpen(false)} onQuote={text => {
      if (!available || sending || pendingSend) return false;
      const combined = draft.trim() ? `${draft}\n\n${text}` : text;
      if (new TextEncoder().encode(combined).byteLength > 65536) return false;
      setDraft(combined); setHistoryOpen(false);
      requestAnimationFrame(() => { draftInput.current?.focus(); draftInput.current?.scrollIntoView({ block: "nearest" }); });
      return true;
    }} /> : null}
    {!followingLatest ? <div className="transcript-history"><button type="button" className="text-action" onClick={() => { followBottom(); showLatest(); }}>返回最新消息</button></div> : null}
    {failed ? <p className="thread-hint" role="alert">无法读取会话记录，请刷新后重试。</p> : null}
    {readReceipt.error ? <p className="thread-hint" role="alert">消息已显示，但未能保存已读状态。<button type="button" className="text-action" onClick={readReceipt.retry}>重新确认已读</button></p> : null}
    {messages === null ? failed ? null : <p className="thread-hint">正在读取消息…</p>
        : messages.length === 0 ? <div className="conversation-placeholder"><h2>还没有消息</h2><p>发一条消息，开始与角色聊天。</p></div>
          : <>{hasOlder ? <div className="transcript-history"><button type="button" className="text-action" disabled={loadingOlder} onClick={() => void loadOlder(beforePrepend)}>{loadingOlder ? "正在加载…" : "加载更早消息"}</button></div> : null}<ol className="message-list">{messages.map((message, index) => {
            const own = message.sender_kind === "player" && message.sender_id === playerId;
            const day = transcriptDay(message.story_sent_at_utc ?? message.created_at_utc);
            const previous = messages[index - 1];
            return <Fragment key={message.message_id}>{!previous || transcriptDay(previous.story_sent_at_utc ?? previous.created_at_utc) !== day ? <li className="message-day">{day}</li> : null}<li data-message-id={message.message_id} className={`message-row ${own ? "own" : ""}`}>
              {!own && <ContactAvatar name={conversation.character_name} url={avatarUrl} className="message-portrait" />}
              <div className="message-bubble">
                <span className="message-sender">{own ? "我" : conversation.character_name}</span>
                <ChatMessageBody text={message.text} />
                <MessageTime message={message} />{!own ? <button type="button" className="text-action message-reference" onClick={() => setReferenceTurn(message.turn_id)}>本次参考内容</button> : null}
              </div>
            </li></Fragment>;
          })}{visibleStreamDraft ? <StreamingReplyBubble name={conversation.character_name} avatarUrl={avatarUrl} text={visibleStreamDraft.text} /> : null}</ol></>}
    {conversation.read_only ? <p className="thread-hint" role="status">角色卡已删除，此会话保留为只读历史。</p> : <form className="chat-composer" onSubmit={event => void send(event)}>
      {phase || feedback ? <p role="status" aria-live="polite" className="chat-feedback">{(phase === "replying" && stream.stage === "preparing" ? "消息已保存，正在准备角色回复…" : chatPhaseFeedback(phase, "direct")) || feedback}</p> : null}
      <ReplyRecoveryControls client={client} worldId={worldId} conversationId={conversation.conversation_id} sourceTurnId={latestPlayerMessage?.turn_id} refresh={refresh} tokenCeiling={tokenCeiling} blocked={!available || phase !== null || !!pendingSend} onGenerate={generateSavedReply} onBusyChange={setRecoveryBusy} />
      {budgetFeedback ? <p className="chat-feedback" role="alert">{budgetFeedback}</p> : null}
      {availabilityReading ? <p className="chat-feedback" role="status">正在核对聊天模型状态…</p>
        : availabilityFailed ? <p className="chat-feedback" role="alert">未能读取聊天模型状态，请点击“刷新记录”重试；这不代表配置已丢失。</p>
        : !available ? <p className="chat-feedback">当前聊天模型尚不可用，请在设置中核对模型与路由。</p> : null}
      <label htmlFor="direct-chat-draft" className="sr-only">发送给{conversation.character_name}的消息</label>
      <textarea ref={draftInput} id="direct-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={!available || sending || !!pendingSend} maxLength={65536} placeholder="输入消息…" rows={3} />
      <div className="chat-composer-actions"><small>回车发送 · Shift+回车换行 · 本轮输入与输出共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small>{latestPlayerMessage ? <button type="button" className="text-action" disabled={sending || !!pendingSend} onClick={() => void checkReply()}>检查回复状态</button> : null}{phase === "replying" ? <button type="button" className="text-action" disabled={stream.stopping} onClick={stream.stop}>{stream.stopping ? "正在停止…" : "停止生成"}</button> : null}<button type="submit" className="primary-button" disabled={!available || sending || (!!budgetFeedback && !pendingSend) || (!draft.trim() && !pendingSend)}>{phase === "saving" ? "正在保存…" : phase === "replying" ? "等待回复…" : phase === "checking" ? "检查中…" : pendingSend ? "重试保存" : "发送"}</button></div>
    </form>}
  </section>;
}
