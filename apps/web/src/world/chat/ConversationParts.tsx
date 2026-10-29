import { Fragment, useCallback, useEffect, useState, type ReactNode, type RefObject } from "react";
import type { ChatMessage, CoreClient } from "@dreamtalk/api-client";
import { ChatPathTools, MessagePathActions, type PathAction } from "../../ChatPathTools";
import { ContextReferencePanel } from "../../ContextReferencePanel";
import { MessageTime, transcriptDay } from "../../MessageTime";
import { SpeechControls } from "../../SpeechPlayback";
import { ReplyRecoveryControls } from "../../ReplyRecoveryControls";
import { StreamingReplyBubble } from "../../StreamingReplyBubble";
import { MessageMedia } from "../../ChatMedia";
import { ChatMessageBody } from "../../ChatMessageBody";
import { MessageFeedback } from "../../MessageFeedback";
import { ChatHistoryPanel } from "../../ChatHistoryPanel";
import { LongChatMemoryPanel } from "../../LongChatMemoryPanel";
import { ConversationMemoryPanel } from "../../ConversationMemoryPanel";
import { FileExportDialog } from "../../FileExportDialog";
import { chatPhaseFeedback } from "../../chatFeedback";
import { inferExpression, type ChatVisualState } from "../../useChatVisuals";
import type { useChatReplyWorkflow } from "../../useChatReplyWorkflow";
import { DayDivider, ScriptMessage, ThreadEmpty, ThreadNote, TranscriptButton } from "./ThreadParts";

/** Shared by direct and group chats: everything here behaves the same for both. */
export type ChatWorkflow = ReturnType<typeof useChatReplyWorkflow>;
export type ChatPerson = { character_id: string; character_name: string; root_import_id: string };
type Kind = "direct" | "group";
const MAX_DRAFT_BYTES = 65536;

/** Which side panels are open; call `useClosePanelsOn` so they close when the chat path changes. */
export function useThreadPanels() {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [longMemoryOpen, setLongMemoryOpen] = useState(false);
  const [pathAction, setPathAction] = useState<PathAction | null>(null);
  const [referenceTurn, setReferenceTurn] = useState<string | null>(null);
  const closePanels = useCallback(() => { setHistoryOpen(false); setExportOpen(false); setMemoryOpen(false); setLongMemoryOpen(false); setReferenceTurn(null); }, []);
  return { closePanels, historyOpen, setHistoryOpen, exportOpen, setExportOpen, memoryOpen, setMemoryOpen, longMemoryOpen, setLongMemoryOpen, pathAction, setPathAction, referenceTurn, setReferenceTurn };
}
export type ThreadPanels = ReturnType<typeof useThreadPanels>;

/** Panels belong to one chat path; switching branch or checkpoint closes them. */
export function useClosePanelsOn(pathKey: unknown, closePanels: () => void) {
  useEffect(() => { closePanels(); }, [pathKey, closePanels]);
}

/** The uploaded sprite for whoever spoke last (or the first person), never a substitute. */
export function useStageSprite(messages: ChatMessage[] | null, people: ChatPerson[], visualState?: ChatVisualState) {
  const latest = [...(messages ?? [])].reverse().find(message => message.sender_kind === "character");
  const person = people.find(item => item.character_id === latest?.sender_id) ?? people[0];
  const expression = inferExpression(latest?.text ?? "");
  const expressions = visualState?.visuals?.expressions.filter(item => person && item.root_import_id === person.root_import_id) ?? [];
  const digest = (expressions.find(item => item.expression === expression) ?? expressions.find(item => item.expression === "neutral"))?.digest;
  return { person, expression, url: digest ? visualState?.urls[digest] : undefined };
}

export function sendLabel(chat: ChatWorkflow): string {
  return chat.phase === "saving" ? "正在保存…" : chat.phase === "replying" ? "等待回复…" : chat.phase === "checking" ? "检查中…" : chat.pending ? "重试保存" : "发送";
}
export const composerLocked = (chat: ChatWorkflow) => !chat.available || chat.sending || !!chat.pending;

/** Path tools and the panels opened from the header's tool menu. */
export function ThreadTools({ client, worldId, conversationId, kind, readOnly, chat, panels, people, senderName, tokenCeiling, draftInput }: {
  client: CoreClient; worldId: string; conversationId: string; kind: Kind; readOnly: boolean; chat: ChatWorkflow; panels: ThreadPanels;
  people: ChatPerson[]; senderName: (message: ChatMessage) => string; tokenCeiling: number; draftInput: RefObject<HTMLTextAreaElement | null>;
}) {
  const { draft, setDraft, sending, pending, available, paths } = chat, busy = sending || !!pending;
  const quote = (text: string) => {
    if (!available || busy) return false;
    const combined = draft.trim() ? `${draft}\n\n${text}` : text;
    if (new TextEncoder().encode(combined).byteLength > MAX_DRAFT_BYTES) return false;
    setDraft(combined); panels.setHistoryOpen(false);
    requestAnimationFrame(() => { draftInput.current?.focus(); draftInput.current?.scrollIntoView({ block: "nearest" }); });
    return true;
  };
  const action = panels.pathAction;
  return <>
    <ChatPathTools key={`${action?.action ?? ""}:${action?.message?.message_id ?? action?.path?.path_id ?? ""}`} client={client} worldId={worldId} conversationId={conversationId}
      paths={paths} blocked={busy || readOnly} tokenCeiling={tokenCeiling} group={kind === "group"} action={action} onAction={panels.setPathAction} onGenerate={turn => chat.generateSavedReply(turn, true)} />
    {panels.exportOpen && <FileExportDialog client={client} worldId={worldId} conversationId={conversationId} onClose={() => panels.setExportOpen(false)} />}
    {panels.referenceTurn ? <ContextReferencePanel key={`${worldId}:${conversationId}:${panels.referenceTurn}`} client={client} worldId={worldId} conversationId={conversationId}
      turnId={panels.referenceTurn} names={new Map(people.map(item => [item.character_id, item.character_name]))} onClose={() => panels.setReferenceTurn(null)} /> : null}
    {panels.longMemoryOpen ? <LongChatMemoryPanel client={client} worldId={worldId} conversationId={conversationId} characters={people} onClose={() => panels.setLongMemoryOpen(false)} /> : null}
    {panels.memoryOpen ? <ConversationMemoryPanel client={client} worldId={worldId} conversationId={conversationId} senderName={senderName} canGenerate={!readOnly && !busy} onClose={() => panels.setMemoryOpen(false)} /> : null}
    {panels.historyOpen ? <ChatHistoryPanel client={client} worldId={worldId} conversationId={conversationId} senderName={senderName} canQuote={available && !busy}
      onClose={() => panels.setHistoryOpen(false)} onQuote={quote} /> : null}
  </>;
}

/** Status lines above the composer: progress, recovery, budget and model readiness. */
export function ComposerStatus({ client, worldId, conversationId, kind, chat, tokenCeiling, onModelSettings }: {
  client: CoreClient; worldId: string; conversationId: string; kind: Kind; chat: ChatWorkflow; tokenCeiling: number; onModelSettings?: () => void;
}) {
  const { phase, feedback, stream } = chat;
  const early = kind === "group" ? stream.stage === "selecting" && "正在选择下一位发言者…" : stream.stage === "preparing" && "消息已保存，正在准备角色回复…";
  return <>
    {/* One persistent live region, so screen readers hear every change rather than only the first. */}
    <p role="status" aria-live="polite" className="chat-feedback">{(phase === "replying" && early) || chatPhaseFeedback(phase, kind) || feedback}</p>
    {feedback && !phase && chat.modelSettingsSuggested && onModelSettings && <button type="button" className="text-action" onClick={onModelSettings}>打开当前世界模型设置</button>}
    <ReplyRecoveryControls client={client} worldId={worldId} conversationId={conversationId} sourceTurnId={chat.latestPlayerMessage?.turn_id} refresh={chat.refresh} tokenCeiling={tokenCeiling}
      blocked={!chat.available || phase !== null || !!chat.pending} onGenerate={chat.generateSavedReply} onBusyChange={chat.setRecoveryBusy} />
    {chat.budgetFeedback ? <p className="chat-feedback" role="alert">{chat.budgetFeedback}</p> : null}
    {chat.availabilityReading ? <p className="chat-feedback" role="status">正在核对聊天模型状态…</p>
      : chat.availabilityFailed ? <p className="chat-feedback" role="alert">未能读取聊天模型状态，请点击“刷新记录”重试；这不代表配置已丢失。</p>
      : !chat.modelReady ? <p className="chat-feedback">当前聊天模型尚不可用，请在设置中核对模型与路由。</p> : null}
  </>;
}

/** Hints under the composer: keys, the shared token ceiling, and reply controls. */
export function ComposerMeta({ chat, tokenCeiling, ceilingLabel }: { chat: ChatWorkflow; tokenCeiling: number; ceilingLabel: string }) {
  return <><small>回车发送 · Shift+回车换行 · {ceilingLabel} {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small>
    {chat.latestPlayerMessage ? <button type="button" className="text-action" disabled={chat.sending || !!chat.pending} onClick={() => void chat.checkReply()}>检查回复状态</button> : null}
    {chat.phase === "replying" ? <button type="button" className="text-action" disabled={chat.stream.stopping} onClick={chat.stream.stop}>{chat.stream.stopping ? "正在停止…" : "停止生成"}</button> : null}</>;
}

/** The script: day dividers, lines, per-line tools and the streaming reply. */
export function ThreadMessages({ client, worldId, conversationId, playerId, readOnly, chat, panels, nameOf, tintOf, emptyText, failedText, readReceipt, followBottom, beforePrepend }: {
  client: CoreClient; worldId: string; conversationId: string; playerId: string; readOnly: boolean; chat: ChatWorkflow; panels: ThreadPanels;
  nameOf: (characterId: string) => string; tintOf: (characterId: string) => string | undefined; emptyText: ReactNode; failedText: string;
  readReceipt: { error: unknown; retry: () => void }; followBottom: () => void; beforePrepend: () => void;
}) {
  const { messages, failed, sending, pending, paths } = chat;
  const dayOf = (message: ChatMessage) => transcriptDay(message.story_sent_at_utc ?? message.created_at_utc);
  return <>
    {!chat.followingLatest ? <TranscriptButton onClick={() => { followBottom(); chat.showLatest(); }}>返回最新消息</TranscriptButton> : null}
    {failed ? <ThreadNote tone="alert">{failedText}</ThreadNote> : null}
    {readReceipt.error ? <ThreadNote tone="alert">消息已显示，但未能保存已读状态。<button type="button" className="text-action" onClick={readReceipt.retry}>重新确认已读</button></ThreadNote> : null}
    {messages === null ? failed ? null : <ThreadNote>正在读取消息…</ThreadNote>
      : messages.length === 0 ? <ThreadEmpty title="还没有消息">{emptyText}</ThreadEmpty>
      : <>{chat.hasOlder ? <TranscriptButton disabled={chat.loadingOlder} onClick={() => void chat.loadOlder(beforePrepend)}>{chat.loadingOlder ? "正在加载…" : "加载更早消息"}</TranscriptButton> : null}
        <ol className="message-list">{messages.map((message, index) => {
          const own = message.sender_kind === "player" && message.sender_id === playerId, day = dayOf(message), previous = messages[index - 1];
          return <Fragment key={message.message_id}>{!previous || dayOf(previous) !== day ? <DayDivider>{day}</DayDivider> : null}
            <ScriptMessage message={message} own={own} name={nameOf(message.sender_id)} tint={tintOf(message.sender_id)} time={<MessageTime message={message} compact />}
              body={<>{!message.media?.only_media && <ChatMessageBody text={message.text} character={!own} />}<MessageMedia client={client} worldId={worldId} media={message.media} /></>}
              tools={<>{!readOnly && <MessagePathActions message={message} disabled={sending || !!pending || paths.busy || !paths.snapshot} onAction={panels.setPathAction} />}
                {!own ? <><MessageFeedback client={client} worldId={worldId} conversationId={conversationId} message={message} disabled={readOnly} />
                  <button type="button" className="text-action message-reference" onClick={() => panels.setReferenceTurn(message.turn_id)}>本次参考内容</button>
                  {!message.media?.only_media && <SpeechControls conversation={conversationId} message={message.message_id} />}</> : null}</>} />
          </Fragment>;
        })}{chat.visibleStreamDraft ? <StreamingReplyBubble name={nameOf(chat.visibleStreamDraft.speakerId)} tint={tintOf(chat.visibleStreamDraft.speakerId)} text={chat.visibleStreamDraft.text} /> : null}</ol></>}
  </>;
}

export const CHECKPOINT_NOTE = "当前为只读检查点。展开一条消息的“消息操作”，选择“从此分支”继续。";
