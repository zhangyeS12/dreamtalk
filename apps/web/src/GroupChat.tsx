import { ChatPathTools, MessagePathActions, type PathAction } from "./ChatPathTools";
import { useConversationRead } from "./useChatUnread";
import { useDesktopUpdateBlock } from "./DesktopUpdates";
import { ContextReferencePanel } from "./ContextReferencePanel";
import { MessageTime, transcriptDay } from "./MessageTime";
import { SpeechControls, SpeechFeedback, useSpeechPreviews } from "./SpeechPlayback";
import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatMessage, type GroupChatConversation, type WorldContentItem } from "@dreamtalk/api-client";
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

import { companyTints } from "./world/tint";
import { ComposerShell, DayDivider, ScriptMessage, SendButton, ThreadEmpty, ThreadFrame, ThreadHeader, ThreadNote, ThreadStage, TranscriptButton, WorldAvatar, threadStyles } from "./world/chat/ThreadParts";
import { FileExportDialog } from "./FileExportDialog";
import { expressionLabel, inferExpression, type ChatVisualState } from "./useChatVisuals";
import { ChatBackgroundControl } from "./ChatBackgroundControl";

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

export function GroupChatDetails({ client, worldId, playerId, group, avatarUrls = {}, tokenCeiling, suggestedDraft, onSuggestionUsed, onBack, onDissolved = onBack, onDirtyChange, onModelSettings, visualState, immersive = false }: {
  client: CoreClient; worldId: string; playerId: string; group: GroupChatConversation; tokenCeiling: number; avatarUrls?: Record<string, string>;
  suggestedDraft?: string | null; onSuggestionUsed?: () => void; onBack: () => void; onDirtyChange?: (dirty: boolean) => void;
  onDissolved?: () => void;
  onModelSettings?: () => void;
  visualState?: ChatVisualState;
  immersive?: boolean;
}) {
  const draftInput = useRef<HTMLTextAreaElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [longMemoryOpen, setLongMemoryOpen] = useState(false);
  const [pathAction, setPathAction] = useState<PathAction | null>(null);
  const [referenceTurn, setReferenceTurn] = useState<string | null>(null);
  const [dissolving, setDissolving] = useState(false);
  const [dissolveError, setDissolveError] = useState("");
  const dissolveLock = useRef(false);
  useDesktopUpdateBlock(dissolving ? "群聊正在解散。" : null);
  const {
    paths, pathKey, modelReady, refresh, setRefresh, available, availabilityReading, availabilityFailed, budgetFeedback,
    draft, setDraft, sticker, setSticker, pending, phase, sending, setRecoveryBusy, feedback, stream,
    messages, failed, hasOlder, loadingOlder, loadOlder, followingLatest, showLatest, visibleStreamDraft,
    latestPlayerMessage, checkReply, generateSavedReply, send, modelSettingsSuggested,
  } = useChatReplyWorkflow({
    client, worldId, playerId, conversationId: group.conversation_id, kind: "group", readOnly: group.read_only,
    extraDirty: pathAction !== null, speakers: group.participants.map(item => item.character_id), tokenCeiling, suggestedDraft, onSuggestionUsed, onDirtyChange,
  });
  useEffect(() => { setHistoryOpen(false); setExportOpen(false); setMemoryOpen(false); setLongMemoryOpen(false); setReferenceTurn(null); }, [pathKey]);
  const readReceipt = useConversationRead(client, worldId, group.conversation_id, messages);
  useSpeechPreviews(group.conversation_id, messages);
  const { thread, beforePrepend, followBottom } = useChatScroll(messages, visibleStreamDraft?.text);
  const latestCharacter = [...(messages ?? [])].reverse().find(message => message.sender_kind === "character");
  const spritePerson = group.participants.find(person => person.character_id === latestCharacter?.sender_id) ?? group.participants[0];
  const expression = inferExpression(latestCharacter?.text ?? "");
  const expressionDigest = (spritePerson && visualState?.visuals?.expressions.find(item => item.root_import_id === spritePerson.root_import_id && item.expression === expression)?.digest)
    ?? (spritePerson && visualState?.visuals?.expressions.find(item => item.root_import_id === spritePerson.root_import_id && item.expression === "neutral")?.digest);
  // Only a sprite the user uploaded may stand on the stage; never substitute the avatar.
  const spriteUrl = expressionDigest ? visualState?.urls[expressionDigest] : undefined;

  const dissolve = async () => {
    if (dissolveLock.current || sending || pending) return;
    if (!window.confirm(`解散“${group.participants.map(item => item.character_name).join("、")}”群聊？\n群聊将从聊天列表消失，不能继续发言。已有记忆及其原消息来源会保留。${draft.trim() ? "\n尚未发送的草稿会丢弃。" : ""}`)) return;
    dissolveLock.current = true; setDissolving(true); setDissolveError("");
    try { await client.dissolveGroup(worldId, group.conversation_id); onDissolved(); }
    catch (error) { setDissolveError(error instanceof CoreRequestError && error.status === 409 ? error.code === "chat_group_waiting_reply" ? "群内有尚未回复的主动联系，请先在本群回复，再解散群聊。" : "仍有回复或主动联系正在生成，请结束后再解散。" : "解散结果未能确认，请重试；已有记忆不会被删除。"); }
    finally { dissolveLock.current = false; setDissolving(false); }
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
  const tints = companyTints(group.participants.map(person => person.character_id));
  const tintOf = (characterId: string) => tints.get(characterId);
  const composerLocked = !available || sending || !!pending;
  const sendLabel = phase === "saving" ? "正在保存…" : phase === "replying" ? "等待回复…" : phase === "checking" ? "检查中…" : pending ? "重试保存" : "发送";
  const senderName = (message: ChatMessage) => message.sender_kind === "player" && message.sender_id === playerId ? "我" : names.get(message.sender_id) ?? "角色";
  const title = group.participants.map(item => item.character_name).join("、");

  return <ThreadFrame label="群聊" tint={spritePerson ? tintOf(spritePerson.character_id) : undefined} staged={immersive} portrait={immersive && !!spriteUrl} scrollRef={thread}
    stage={immersive ? <ThreadStage url={spriteUrl} label={`${spritePerson?.character_name ?? "角色"}，${expressionLabel(expression)}表情`} /> : null}
    header={<ThreadHeader title={title} kind={`群聊 · ${group.participants.length} 位角色`}
      portrait={<span className={threadStyles.groupPortrait} aria-hidden="true">{group.participants.slice(0, 3).map(person => <WorldAvatar key={person.character_id} name={person.character_name} url={avatarUrls[person.root_import_id]} tint={tintOf(person.character_id)} size="s" />)}</span>}
      onBack={() => { if (!dissolving) onBack(); }} onRefresh={() => { setRefresh(value => value + 1); paths.refresh(); }} onPaths={() => paths.setOpen(true)}
      onLongMemory={() => setLongMemoryOpen(true)} onMemory={() => setMemoryOpen(true)} onHistory={() => setHistoryOpen(true)} onExport={() => setExportOpen(true)}
      visualControl={visualState && spritePerson ? <ChatBackgroundControl client={client} worldId={worldId} rootImportId={spritePerson.root_import_id} state={visualState} /> : undefined}
      onDissolve={() => void dissolve()} dissolveDisabled={dissolving || sending || !!pending} />}
    tools={<>
      <ChatPathTools key={`${pathAction?.action ?? ""}:${pathAction?.message?.message_id ?? pathAction?.path?.path_id ?? ""}`} client={client} worldId={worldId} conversationId={group.conversation_id} paths={paths} blocked={sending || !!pending || !!group.read_only} tokenCeiling={tokenCeiling} group action={pathAction} onAction={setPathAction} onGenerate={turn => generateSavedReply(turn, true)} />
      {exportOpen && <FileExportDialog client={client} worldId={worldId} conversationId={group.conversation_id} onClose={() => setExportOpen(false)} />}
      {referenceTurn ? <ContextReferencePanel key={`${worldId}:${group.conversation_id}:${referenceTurn}`} client={client} worldId={worldId} conversationId={group.conversation_id} turnId={referenceTurn} names={names} onClose={() => setReferenceTurn(null)} /> : null}
      {longMemoryOpen ? <LongChatMemoryPanel client={client} worldId={worldId} conversationId={group.conversation_id} characters={group.participants} onClose={() => setLongMemoryOpen(false)} /> : null}
      {memoryOpen ? <ConversationMemoryPanel client={client} worldId={worldId} conversationId={group.conversation_id} senderName={senderName} canGenerate={!group.read_only && !sending && !pending} onClose={() => setMemoryOpen(false)} /> : null}
      {historyOpen ? <ChatHistoryPanel client={client} worldId={worldId} conversationId={group.conversation_id} senderName={senderName} canQuote={available && !sending && !pending} onClose={() => setHistoryOpen(false)} onQuote={text => {
        if (!available || sending || pending) return false;
        const combined = draft.trim() ? `${draft}\n\n${text}` : text;
        if (new TextEncoder().encode(combined).byteLength > 65536) return false;
        setDraft(combined); setHistoryOpen(false);
        requestAnimationFrame(() => { draftInput.current?.focus(); draftInput.current?.scrollIntoView({ block: "nearest" }); });
        return true;
      }} /> : null}
    </>}
    composer={paths.snapshot?.active.kind === "checkpoint" ? <ThreadNote>当前为只读检查点。展开一条消息的“消息操作”，选择“从此分支”继续。</ThreadNote>
      : group.read_only ? <ThreadNote>此群包含已删除的角色卡，消息保留为只读历史。可用其余角色建立新群。</ThreadNote>
      : <ComposerShell onSubmit={event => { if (dissolving) event.preventDefault(); else void send(event); }}
        status={<>
          {phase || feedback ? <p role="status" aria-live="polite" className="chat-feedback">{(phase === "replying" && stream.stage === "selecting" ? "正在选择下一位发言者…" : chatPhaseFeedback(phase, "group")) || feedback}</p> : null}
          {feedback && !phase && modelSettingsSuggested && onModelSettings && <button type="button" className="text-action" onClick={onModelSettings}>打开当前世界模型设置</button>}
          <ReplyRecoveryControls client={client} worldId={worldId} conversationId={group.conversation_id} sourceTurnId={latestPlayerMessage?.turn_id} refresh={refresh} tokenCeiling={tokenCeiling} blocked={!available || phase !== null || !!pending} onGenerate={generateSavedReply} onBusyChange={setRecoveryBusy} />
          {budgetFeedback ? <p className="chat-feedback" role="alert">{budgetFeedback}</p> : null}
          {availabilityReading ? <p className="chat-feedback" role="status">正在核对聊天模型状态…</p>
            : availabilityFailed ? <p className="chat-feedback" role="alert">未能读取聊天模型状态，请点击“刷新记录”重试；这不代表配置已丢失。</p>
            : !modelReady ? <p className="chat-feedback">当前聊天模型尚不可用，请在设置中核对模型与路由。</p> : null}
        </>}
        mentions={mentionable.length > 0 ? <div className="chat-mention-actions"><span>指定下一位</span>{mentionable.map(item => <button key={item.character_id} type="button" disabled={composerLocked || dissolving} onClick={() => insertMention(item.character_name)}>@{item.character_name}</button>)}</div> : null}
        sticker={<StickerPicker client={client} worldId={worldId} selected={sticker} onSelect={setSticker} disabled={composerLocked} />}
        input={<><label htmlFor="group-chat-draft" className="sr-only">发送群聊消息</label>
          <textarea ref={draftInput} id="group-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={composerLocked || dissolving} maxLength={65536} placeholder="说点什么，或用 @角色名 指定下一位发言者……" rows={1} /></>}
        send={<SendButton label={sendLabel} disabled={dissolving || !available || sending || (!!budgetFeedback && !pending) || (!draft.trim() && !sticker && !pending)} />}
        meta={<><small>回车发送 · Shift+回车换行 · 本轮所有发言共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small>
          {latestPlayerMessage ? <button type="button" className="text-action" disabled={sending || !!pending} onClick={() => void checkReply()}>检查回复状态</button> : null}
          {phase === "replying" ? <button type="button" className="text-action" disabled={stream.stopping} onClick={stream.stop}>{stream.stopping ? "正在停止…" : "停止生成"}</button> : null}</>} />}>
    {dissolveError ? <ThreadNote tone="alert">{dissolveError}</ThreadNote> : null}
    {dissolving ? <ThreadNote>正在解散群聊…</ThreadNote> : null}
    {!followingLatest ? <TranscriptButton onClick={() => { followBottom(); showLatest(); }}>返回最新消息</TranscriptButton> : null}
    {failed ? <ThreadNote tone="alert">无法读取群聊记录，请刷新后重试。</ThreadNote> : null}
    {readReceipt.error ? <ThreadNote tone="alert">消息已显示，但未能保存已读状态。<button type="button" className="text-action" onClick={readReceipt.retry}>重新确认已读</button></ThreadNote> : null}
    {messages === null ? failed ? null : <ThreadNote>正在读取消息…</ThreadNote>
      : messages.length === 0 ? <ThreadEmpty title="还没有消息">发一条消息，开始群聊。</ThreadEmpty>
      : <>{hasOlder ? <TranscriptButton disabled={loadingOlder} onClick={() => void loadOlder(beforePrepend)}>{loadingOlder ? "正在加载…" : "加载更早消息"}</TranscriptButton> : null}
        <ol className="message-list">{messages.map((message, index) => {
          const own = message.sender_kind === "player" && message.sender_id === playerId;
          const day = transcriptDay(message.story_sent_at_utc ?? message.created_at_utc);
          const previous = messages[index - 1];
          return <Fragment key={message.message_id}>{!previous || transcriptDay(previous.story_sent_at_utc ?? previous.created_at_utc) !== day ? <DayDivider>{day}</DayDivider> : null}
            <ScriptMessage message={message} own={own} name={names.get(message.sender_id) ?? "角色"} tint={tintOf(message.sender_id)} time={<MessageTime message={message} compact />}
              body={<>{!message.media?.only_media && <ChatMessageBody text={message.text} character={!own} />}<MessageMedia client={client} worldId={worldId} media={message.media} /></>}
              tools={<>{!group.read_only && <MessagePathActions message={message} disabled={sending || !!pending || paths.busy || !paths.snapshot} onAction={setPathAction} />}
                {!own ? <><MessageFeedback client={client} worldId={worldId} conversationId={group.conversation_id} message={message} disabled={group.read_only} /><button type="button" className="text-action message-reference" onClick={() => setReferenceTurn(message.turn_id)}>本次参考内容</button>{!message.media?.only_media && <SpeechControls conversation={group.conversation_id} message={message.message_id} />}</> : null}</>} />
          </Fragment>;
        })}{visibleStreamDraft ? <StreamingReplyBubble name={names.get(visibleStreamDraft.speakerId) ?? "角色"} tint={tintOf(visibleStreamDraft.speakerId)} text={visibleStreamDraft.text} /> : null}</ol></>}
    <SpeechFeedback />
  </ThreadFrame>;
}
