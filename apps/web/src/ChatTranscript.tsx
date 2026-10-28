import { ChatPathTools, MessagePathActions, type PathAction } from "./ChatPathTools";
import { useConversationRead } from "./useChatUnread";
import { ContextReferencePanel } from "./ContextReferencePanel";
import { MessageTime, transcriptDay } from "./MessageTime";
import { SpeechControls, SpeechFeedback, useSpeechPreviews } from "./SpeechPlayback";
import { Fragment, useEffect, useRef, useState } from "react";
import { CoreClient, type ChatConversation, type ChatMessage } from "@dreamtalk/api-client";
import { useChatReplyWorkflow } from "./useChatReplyWorkflow";
import { ReplyRecoveryControls } from "./ReplyRecoveryControls";
import { StreamingReplyBubble } from "./StreamingReplyBubble";
import { useChatScroll } from "./useChatScroll";
import { MessageMedia, StickerPicker } from "./ChatMedia";
import { ChatMessageBody } from "./ChatMessageBody";
import { MessageFeedback } from "./MessageFeedback";
import { ChatHistoryPanel } from "./ChatHistoryPanel";
import { LongChatMemoryPanel } from "./LongChatMemoryPanel";
import { ConversationMemoryPanel } from "./ConversationMemoryPanel";
import { submitChatOnEnter } from "./chatComposerKeys";
import { chatPhaseFeedback } from "./chatFeedback";

import { characterTint } from "./world/tint";
import { ComposerShell, DayDivider, ScriptMessage, SendButton, ThreadEmpty, ThreadFrame, ThreadHeader, ThreadNote, ThreadStage, TranscriptButton, WorldAvatar } from "./world/chat/ThreadParts";
import { FileExportDialog } from "./FileExportDialog";
import { expressionLabel, inferExpression, type ChatVisualState } from "./useChatVisuals";
import { ChatBackgroundControl } from "./ChatBackgroundControl";

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
  onModelSettings?: () => void;
  visualState?: ChatVisualState;
  immersive?: boolean;
}

export function ChatTranscript({ client, worldId, playerId, conversation, avatarUrl, tokenCeiling, suggestedDraft, onSuggestionUsed, onBack, onDirtyChange, onModelSettings, visualState, immersive = false }: Props) {
  const draftInput = useRef<HTMLTextAreaElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [longMemoryOpen, setLongMemoryOpen] = useState(false);
  const [pathAction, setPathAction] = useState<PathAction | null>(null);
  const [referenceTurn, setReferenceTurn] = useState<string | null>(null);
  const {
    paths, pathKey, modelReady, refresh, setRefresh, available, availabilityReading, availabilityFailed, budgetFeedback,
    draft, setDraft, sticker, setSticker, pending: pendingSend, phase, sending, setRecoveryBusy, feedback, stream,
    messages, failed, hasOlder, loadingOlder, loadOlder, followingLatest, showLatest, visibleStreamDraft,
    latestPlayerMessage, checkReply, generateSavedReply, send, modelSettingsSuggested,
  } = useChatReplyWorkflow({
    client, worldId, playerId, conversationId: conversation.conversation_id, kind: "direct", readOnly: conversation.read_only,
    extraDirty: pathAction !== null, speakers: [conversation.character_id], tokenCeiling, suggestedDraft, onSuggestionUsed, onDirtyChange,
  });
  useEffect(() => { setHistoryOpen(false); setExportOpen(false); setMemoryOpen(false); setLongMemoryOpen(false); setReferenceTurn(null); }, [pathKey]);
  const readReceipt = useConversationRead(client, worldId, conversation.conversation_id, messages);
  useSpeechPreviews(conversation.conversation_id, messages);
  const { thread, beforePrepend, followBottom } = useChatScroll(messages, visibleStreamDraft?.text);
  const latestCharacter = [...(messages ?? [])].reverse().find(message => message.sender_kind === "character");
  const expression = inferExpression(latestCharacter?.text ?? "");
  const expressionDigest = visualState?.visuals?.expressions.find(item => item.root_import_id === conversation.root_import_id && item.expression === expression)?.digest
    ?? visualState?.visuals?.expressions.find(item => item.root_import_id === conversation.root_import_id && item.expression === "neutral")?.digest;
  // Only a sprite the user uploaded may stand on the stage; never substitute the avatar.
  const spriteUrl = expressionDigest ? visualState?.urls[expressionDigest] : undefined;

  const tint = characterTint(conversation.character_id);
  const composerLocked = !available || sending || !!pendingSend;
  const sendLabel = phase === "saving" ? "正在保存…" : phase === "replying" ? "等待回复…" : phase === "checking" ? "检查中…" : pendingSend ? "重试保存" : "发送";
  const senderName = (message: ChatMessage) => message.sender_kind === "player" && message.sender_id === playerId ? "我" : conversation.character_name;

  return <ThreadFrame label={`${conversation.character_name}的会话`} tint={tint} staged={immersive} portrait={immersive && !!spriteUrl} scrollRef={thread}
    stage={immersive ? <ThreadStage url={spriteUrl} label={`${conversation.character_name}，${expressionLabel(expression)}表情`} /> : null}
    header={<ThreadHeader title={conversation.character_name} kind="私聊" portrait={<WorldAvatar name={conversation.character_name} url={avatarUrl} tint={tint} size="l" />}
      onBack={onBack} onRefresh={() => { setRefresh(value => value + 1); paths.refresh(); }} onPaths={() => paths.setOpen(true)} onLongMemory={() => setLongMemoryOpen(true)}
      onMemory={() => setMemoryOpen(true)} onHistory={() => setHistoryOpen(true)} onExport={() => setExportOpen(true)}
      visualControl={visualState ? <ChatBackgroundControl client={client} worldId={worldId} rootImportId={conversation.root_import_id} state={visualState} /> : undefined} />}
    tools={<>
      <ChatPathTools key={`${pathAction?.action ?? ""}:${pathAction?.message?.message_id ?? pathAction?.path?.path_id ?? ""}`} client={client} worldId={worldId} conversationId={conversation.conversation_id} paths={paths} blocked={sending || !!pendingSend || !!conversation.read_only} tokenCeiling={tokenCeiling} action={pathAction} onAction={setPathAction} onGenerate={turn => generateSavedReply(turn, true)} />
      {exportOpen && <FileExportDialog client={client} worldId={worldId} conversationId={conversation.conversation_id} onClose={() => setExportOpen(false)} />}
      {referenceTurn ? <ContextReferencePanel key={`${worldId}:${conversation.conversation_id}:${referenceTurn}`} client={client} worldId={worldId} conversationId={conversation.conversation_id} turnId={referenceTurn} names={new Map([[conversation.character_id, conversation.character_name]])} onClose={() => setReferenceTurn(null)} /> : null}
      {longMemoryOpen ? <LongChatMemoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} characters={[{ character_id: conversation.character_id, character_name: conversation.character_name }]} onClose={() => setLongMemoryOpen(false)} /> : null}
      {memoryOpen ? <ConversationMemoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} senderName={senderName} canGenerate={!conversation.read_only && !sending && !pendingSend} onClose={() => setMemoryOpen(false)} /> : null}
      {historyOpen ? <ChatHistoryPanel client={client} worldId={worldId} conversationId={conversation.conversation_id} senderName={senderName} canQuote={available && !sending && !pendingSend} onClose={() => setHistoryOpen(false)} onQuote={text => {
        if (!available || sending || pendingSend) return false;
        const combined = draft.trim() ? `${draft}\n\n${text}` : text;
        if (new TextEncoder().encode(combined).byteLength > 65536) return false;
        setDraft(combined); setHistoryOpen(false);
        requestAnimationFrame(() => { draftInput.current?.focus(); draftInput.current?.scrollIntoView({ block: "nearest" }); });
        return true;
      }} /> : null}
    </>}
    composer={paths.snapshot?.active.kind === "checkpoint" ? <ThreadNote>当前为只读检查点。展开一条消息的“消息操作”，选择“从此分支”继续。</ThreadNote>
      : conversation.read_only ? <ThreadNote>角色卡已删除，此会话保留为只读历史。</ThreadNote>
      : <ComposerShell onSubmit={event => void send(event)}
        status={<>
          {phase || feedback ? <p role="status" aria-live="polite" className="chat-feedback">{(phase === "replying" && stream.stage === "preparing" ? "消息已保存，正在准备角色回复…" : chatPhaseFeedback(phase, "direct")) || feedback}</p> : null}
          {feedback && !phase && modelSettingsSuggested && onModelSettings && <button type="button" className="text-action" onClick={onModelSettings}>打开当前世界模型设置</button>}
          <ReplyRecoveryControls client={client} worldId={worldId} conversationId={conversation.conversation_id} sourceTurnId={latestPlayerMessage?.turn_id} refresh={refresh} tokenCeiling={tokenCeiling} blocked={!available || phase !== null || !!pendingSend} onGenerate={generateSavedReply} onBusyChange={setRecoveryBusy} />
          {budgetFeedback ? <p className="chat-feedback" role="alert">{budgetFeedback}</p> : null}
          {availabilityReading ? <p className="chat-feedback" role="status">正在核对聊天模型状态…</p>
            : availabilityFailed ? <p className="chat-feedback" role="alert">未能读取聊天模型状态，请点击“刷新记录”重试；这不代表配置已丢失。</p>
            : !modelReady ? <p className="chat-feedback">当前聊天模型尚不可用，请在设置中核对模型与路由。</p> : null}
        </>}
        sticker={<StickerPicker client={client} worldId={worldId} selected={sticker} onSelect={setSticker} disabled={composerLocked} />}
        input={<><label htmlFor="direct-chat-draft" className="sr-only">发送给{conversation.character_name}的消息</label>
          <textarea ref={draftInput} id="direct-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={composerLocked} maxLength={65536} placeholder={`对${conversation.character_name}说点什么……`} rows={1} /></>}
        send={<SendButton label={sendLabel} disabled={!available || sending || (!!budgetFeedback && !pendingSend) || (!draft.trim() && !sticker && !pendingSend)} />}
        meta={<><small>回车发送 · Shift+回车换行 · 本轮输入与输出共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small>
          {latestPlayerMessage ? <button type="button" className="text-action" disabled={sending || !!pendingSend} onClick={() => void checkReply()}>检查回复状态</button> : null}
          {phase === "replying" ? <button type="button" className="text-action" disabled={stream.stopping} onClick={stream.stop}>{stream.stopping ? "正在停止…" : "停止生成"}</button> : null}</>} />}>
    {!followingLatest ? <TranscriptButton onClick={() => { followBottom(); showLatest(); }}>返回最新消息</TranscriptButton> : null}
    {failed ? <ThreadNote tone="alert">无法读取会话记录，请刷新后重试。</ThreadNote> : null}
    {readReceipt.error ? <ThreadNote tone="alert">消息已显示，但未能保存已读状态。<button type="button" className="text-action" onClick={readReceipt.retry}>重新确认已读</button></ThreadNote> : null}
    {messages === null ? failed ? null : <ThreadNote>正在读取消息…</ThreadNote>
      : messages.length === 0 ? <ThreadEmpty title="还没有消息">发一条消息，开始与角色聊天。</ThreadEmpty>
      : <>{hasOlder ? <TranscriptButton disabled={loadingOlder} onClick={() => void loadOlder(beforePrepend)}>{loadingOlder ? "正在加载…" : "加载更早消息"}</TranscriptButton> : null}
        <ol className="message-list">{messages.map((message, index) => {
          const own = message.sender_kind === "player" && message.sender_id === playerId;
          const day = transcriptDay(message.story_sent_at_utc ?? message.created_at_utc);
          const previous = messages[index - 1];
          return <Fragment key={message.message_id}>{!previous || transcriptDay(previous.story_sent_at_utc ?? previous.created_at_utc) !== day ? <DayDivider>{day}</DayDivider> : null}
            <ScriptMessage message={message} own={own} name={conversation.character_name} tint={tint} time={<MessageTime message={message} compact />}
              body={<>{!message.media?.only_media && <ChatMessageBody text={message.text} character={!own} />}<MessageMedia client={client} worldId={worldId} media={message.media} /></>}
              tools={<>{!conversation.read_only && <MessagePathActions message={message} disabled={sending || !!pendingSend || paths.busy || !paths.snapshot} onAction={setPathAction} />}
                {!own ? <><MessageFeedback client={client} worldId={worldId} conversationId={conversation.conversation_id} message={message} disabled={conversation.read_only} /><button type="button" className="text-action message-reference" onClick={() => setReferenceTurn(message.turn_id)}>本次参考内容</button>{!message.media?.only_media && <SpeechControls conversation={conversation.conversation_id} message={message.message_id} />}</> : null}</>} />
          </Fragment>;
        })}{visibleStreamDraft ? <StreamingReplyBubble name={conversation.character_name} tint={tint} text={visibleStreamDraft.text} /> : null}</ol></>}
    <SpeechFeedback />
  </ThreadFrame>;
}
