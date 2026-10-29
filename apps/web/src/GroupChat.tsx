import { useRef, useState, useEffect, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatMessage, type GroupChatConversation, type WorldContentItem } from "@dreamtalk/api-client";
import { useConversationRead } from "./useChatUnread";
import { useDesktopUpdateBlock } from "./DesktopUpdates";
import { SpeechFeedback, useSpeechPreviews } from "./SpeechPlayback";
import { useChatReplyWorkflow } from "./useChatReplyWorkflow";
import { useChatScroll } from "./useChatScroll";
import { StickerPicker } from "./ChatMedia";
import { submitChatOnEnter } from "./chatComposerKeys";
import { companyTints } from "./world/tint";
import { ComposerShell, SendButton, ThreadFrame, ThreadHeader, ThreadNote, ThreadStage, WorldAvatar, threadStyles } from "./world/chat/ThreadParts";
import { CHECKPOINT_NOTE, ComposerMeta, ComposerStatus, ThreadMessages, ThreadTools, composerLocked, sendLabel, useClosePanelsOn, useStageSprite, useThreadPanels } from "./world/chat/ConversationParts";
import { expressionLabel, type ChatVisualState } from "./useChatVisuals";
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
  const conversationId = group.conversation_id, readOnly = !!group.read_only, people = group.participants;
  const [dissolving, setDissolving] = useState(false);
  const [dissolveError, setDissolveError] = useState("");
  const dissolveLock = useRef(false);
  useDesktopUpdateBlock(dissolving ? "群聊正在解散。" : null);
  const panels = useThreadPanels();
  const chat = useChatReplyWorkflow({
    client, worldId, playerId, conversationId, kind: "group", readOnly: group.read_only,
    extraDirty: panels.pathAction !== null, speakers: people.map(item => item.character_id), tokenCeiling, suggestedDraft, onSuggestionUsed, onDirtyChange,
  });
  useClosePanelsOn(chat.pathKey, panels.closePanels);
  const readReceipt = useConversationRead(client, worldId, conversationId, chat.messages);
  useSpeechPreviews(conversationId, chat.messages);
  const { thread, beforePrepend, followBottom } = useChatScroll(chat.messages, chat.visibleStreamDraft?.text);
  const sprite = useStageSprite(chat.messages, people, visualState);
  const { draft, setDraft, sticker, setSticker, available, sending, pending, budgetFeedback } = chat;

  const dissolve = async () => {
    if (dissolveLock.current || sending || pending) return;
    if (!window.confirm(`解散“${people.map(item => item.character_name).join("、")}”群聊？\n群聊将从聊天列表消失，不能继续发言。已有记忆及其原消息来源会保留。${draft.trim() ? "\n尚未发送的草稿会丢弃。" : ""}`)) return;
    dissolveLock.current = true; setDissolving(true); setDissolveError("");
    try { await client.dissolveGroup(worldId, conversationId); onDissolved(); }
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

  const names = new Map(people.map(item => [item.character_id, item.character_name]));
  const nameOf = (characterId: string) => names.get(characterId) ?? "角色";
  const nameCounts = new Map<string, number>();
  for (const item of people) nameCounts.set(item.character_name, (nameCounts.get(item.character_name) ?? 0) + 1);
  const mentionable = people.filter(item => nameCounts.get(item.character_name) === 1);
  const tints = companyTints(people.map(person => person.character_id));
  const tintOf = (characterId: string) => tints.get(characterId);
  const locked = composerLocked(chat);
  const senderName = (message: ChatMessage) => message.sender_kind === "player" && message.sender_id === playerId ? "我" : nameOf(message.sender_id);
  const title = people.map(item => item.character_name).join("、");

  return <ThreadFrame label="群聊" tint={sprite.person ? tintOf(sprite.person.character_id) : undefined} staged={immersive} portrait={immersive && !!sprite.url} scrollRef={thread}
    stage={immersive ? <ThreadStage url={sprite.url} label={`${sprite.person?.character_name ?? "角色"}，${expressionLabel(sprite.expression)}表情`} /> : null}
    header={<ThreadHeader title={title} kind={`群聊 · ${people.length} 位角色`}
      portrait={<span className={threadStyles.groupPortrait} aria-hidden="true">{people.slice(0, 3).map(person => <WorldAvatar key={person.character_id} name={person.character_name} url={avatarUrls[person.root_import_id]} tint={tintOf(person.character_id)} size="s" />)}</span>}
      onBack={() => { if (!dissolving) onBack(); }} onRefresh={() => { chat.setRefresh(value => value + 1); chat.paths.refresh(); }} onPaths={() => chat.paths.setOpen(true)}
      onLongMemory={() => panels.setLongMemoryOpen(true)} onMemory={() => panels.setMemoryOpen(true)} onHistory={() => panels.setHistoryOpen(true)} onExport={() => panels.setExportOpen(true)}
      visualControl={visualState && sprite.person ? <ChatBackgroundControl client={client} worldId={worldId} rootImportId={sprite.person.root_import_id} state={visualState} /> : undefined}
      onDissolve={() => void dissolve()} dissolveDisabled={dissolving || sending || !!pending} />}
    tools={<ThreadTools client={client} worldId={worldId} conversationId={conversationId} kind="group" readOnly={readOnly} chat={chat} panels={panels} people={people}
      senderName={senderName} tokenCeiling={tokenCeiling} draftInput={draftInput} />}
    composer={chat.paths.snapshot?.active.kind === "checkpoint" ? <ThreadNote>{CHECKPOINT_NOTE}</ThreadNote>
      : readOnly ? <ThreadNote>此群包含已删除的角色卡，消息保留为只读历史。可用其余角色建立新群。</ThreadNote>
      : <ComposerShell onSubmit={event => { if (dissolving) event.preventDefault(); else void chat.send(event); }}
        status={<ComposerStatus client={client} worldId={worldId} conversationId={conversationId} kind="group" chat={chat} tokenCeiling={tokenCeiling} onModelSettings={onModelSettings} />}
        mentions={mentionable.length > 0 ? <div className="chat-mention-actions"><span>指定下一位</span>{mentionable.map(item => <button key={item.character_id} type="button" disabled={locked || dissolving} onClick={() => insertMention(item.character_name)}>@{item.character_name}</button>)}</div> : null}
        sticker={<StickerPicker client={client} worldId={worldId} selected={sticker} onSelect={setSticker} disabled={locked} />}
        input={<><label htmlFor="group-chat-draft" className="sr-only">发送群聊消息</label>
          <textarea ref={draftInput} id="group-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={locked || dissolving} maxLength={65536} placeholder="说点什么，或用 @角色名 指定下一位发言者……" rows={1} /></>}
        send={<SendButton label={sendLabel(chat)} disabled={dissolving || !available || sending || (!!budgetFeedback && !pending) || (!draft.trim() && !sticker && !pending)} />}
        meta={<ComposerMeta chat={chat} tokenCeiling={tokenCeiling} ceilingLabel="本轮所有发言共用" />} />}>
    {dissolveError ? <ThreadNote tone="alert">{dissolveError}</ThreadNote> : null}
    {dissolving ? <ThreadNote>正在解散群聊…</ThreadNote> : null}
    <ThreadMessages client={client} worldId={worldId} conversationId={conversationId} playerId={playerId} readOnly={readOnly} chat={chat} panels={panels}
      nameOf={nameOf} tintOf={tintOf} emptyText="发一条消息，开始群聊。" failedText="无法读取群聊记录，请刷新后重试。"
      readReceipt={readReceipt} followBottom={followBottom} beforePrepend={beforePrepend} />
    <SpeechFeedback />
  </ThreadFrame>;
}
