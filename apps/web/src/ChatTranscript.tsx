import { useRef } from "react";
import { CoreClient, type ChatConversation, type ChatMessage } from "@dreamtalk/api-client";
import { useConversationRead } from "./useChatUnread";
import { SpeechFeedback, useSpeechPreviews } from "./SpeechPlayback";
import { useChatReplyWorkflow } from "./useChatReplyWorkflow";
import { useChatScroll } from "./useChatScroll";
import { StickerPicker } from "./ChatMedia";
import { submitChatOnEnter } from "./chatComposerKeys";
import { characterTint } from "./world/tint";
import { ComposerShell, SendButton, ThreadFrame, ThreadHeader, ThreadNote, ThreadStage, WorldAvatar } from "./world/chat/ThreadParts";
import { CHECKPOINT_NOTE, ComposerMeta, ComposerStatus, ThreadMessages, ThreadTools, composerLocked, sendLabel, useClosePanelsOn, useStageSprite, useThreadPanels } from "./world/chat/ConversationParts";
import { expressionLabel, type ChatVisualState } from "./useChatVisuals";
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
  const conversationId = conversation.conversation_id, readOnly = !!conversation.read_only;
  const people = [{ character_id: conversation.character_id, character_name: conversation.character_name, root_import_id: conversation.root_import_id }];
  const panels = useThreadPanels();
  const chat = useChatReplyWorkflow({
    client, worldId, playerId, conversationId, kind: "direct", readOnly: conversation.read_only,
    extraDirty: panels.pathAction !== null, speakers: [conversation.character_id], tokenCeiling, suggestedDraft, onSuggestionUsed, onDirtyChange,
  });
  useClosePanelsOn(chat.pathKey, panels.closePanels);
  const readReceipt = useConversationRead(client, worldId, conversationId, chat.messages);
  useSpeechPreviews(conversationId, chat.messages);
  const { thread, beforePrepend, followBottom } = useChatScroll(chat.messages, chat.visibleStreamDraft?.text);
  const sprite = useStageSprite(chat.messages, people, visualState);
  const tint = characterTint(conversation.character_id);
  const senderName = (message: ChatMessage) => message.sender_kind === "player" && message.sender_id === playerId ? "我" : conversation.character_name;
  const { draft, setDraft, sticker, setSticker, available, sending, pending, budgetFeedback } = chat;

  return <ThreadFrame label={`${conversation.character_name}的会话`} tint={tint} staged={immersive} portrait={immersive && !!sprite.url} scrollRef={thread}
    stage={immersive ? <ThreadStage url={sprite.url} label={`${conversation.character_name}，${expressionLabel(sprite.expression)}表情`} /> : null}
    header={<ThreadHeader title={conversation.character_name} kind="私聊" portrait={<WorldAvatar name={conversation.character_name} url={avatarUrl} tint={tint} size="l" />}
      onBack={onBack} onRefresh={() => { chat.setRefresh(value => value + 1); chat.paths.refresh(); }} onPaths={() => chat.paths.setOpen(true)} onLongMemory={() => panels.setLongMemoryOpen(true)}
      onMemory={() => panels.setMemoryOpen(true)} onHistory={() => panels.setHistoryOpen(true)} onExport={() => panels.setExportOpen(true)}
      visualControl={visualState ? <ChatBackgroundControl client={client} worldId={worldId} rootImportId={conversation.root_import_id} state={visualState} /> : undefined} />}
    tools={<ThreadTools client={client} worldId={worldId} conversationId={conversationId} kind="direct" readOnly={readOnly} chat={chat} panels={panels} people={people}
      senderName={senderName} tokenCeiling={tokenCeiling} draftInput={draftInput} />}
    composer={chat.paths.snapshot?.active.kind === "checkpoint" ? <ThreadNote>{CHECKPOINT_NOTE}</ThreadNote>
      : readOnly ? <ThreadNote>角色卡已删除，此会话保留为只读历史。</ThreadNote>
      : <ComposerShell onSubmit={event => void chat.send(event)}
        status={<ComposerStatus client={client} worldId={worldId} conversationId={conversationId} kind="direct" chat={chat} tokenCeiling={tokenCeiling} onModelSettings={onModelSettings} />}
        sticker={<StickerPicker client={client} worldId={worldId} selected={sticker} onSelect={setSticker} disabled={composerLocked(chat)} />}
        input={<><label htmlFor="direct-chat-draft" className="sr-only">发送给{conversation.character_name}的消息</label>
          <textarea ref={draftInput} id="direct-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={composerLocked(chat)} maxLength={65536} placeholder={`对${conversation.character_name}说点什么……`} rows={1} /></>}
        send={<SendButton label={sendLabel(chat)} disabled={!available || sending || (!!budgetFeedback && !pending) || (!draft.trim() && !sticker && !pending)} />}
        meta={<ComposerMeta chat={chat} tokenCeiling={tokenCeiling} ceilingLabel="本轮输入与输出共用" />} />}>
    <ThreadMessages client={client} worldId={worldId} conversationId={conversationId} playerId={playerId} readOnly={readOnly} chat={chat} panels={panels}
      nameOf={() => conversation.character_name} tintOf={() => tint} emptyText="发一条消息，开始与角色聊天。" failedText="无法读取会话记录，请刷新后重试。"
      readReceipt={readReceipt} followBottom={followBottom} beforePrepend={beforePrepend} />
    <SpeechFeedback />
  </ThreadFrame>;
}
