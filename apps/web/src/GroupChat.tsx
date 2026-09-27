import { useEffect, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatMessage, type GroupChatConversation, type WorldContentItem } from "@dreamtalk/api-client";
import { useChatScroll } from "./useChatScroll";
import { ChatMessageBody } from "./ChatMessageBody";
import { submitChatOnEnter } from "./chatComposerKeys";

export function GroupChatSetup({ client, worldId, onCreated, onBack }: {
  client: CoreClient;
  worldId: string;
  onCreated: (group: GroupChatConversation) => void;
  onBack: () => void;
}) {
  const [contacts, setContacts] = useState<WorldContentItem[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState<{ importIds: string[]; requestId: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

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

export function GroupChatDetails({ client, worldId, playerId, group, tokenCeiling, suggestedDraft, onSuggestionUsed, onBack }: {
  client: CoreClient; worldId: string; playerId: string; group: GroupChatConversation; tokenCeiling: number;
  suggestedDraft?: string | null; onSuggestionUsed?: () => void; onBack: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [available, setAvailable] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<{ text: string; ceiling: number; requestId: string } | null>(null);
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState("");
  const thread = useChatScroll(messages);

  useEffect(() => {
    if (suggestedDraft) {
      setDraft(suggestedDraft);
      onSuggestionUsed?.();
    }
  }, [suggestedDraft, onSuggestionUsed]);

  useEffect(() => {
    let active = true;
    void client.conversationMessages(worldId, group.conversation_id)
      .then(items => { if (active) setMessages(items); })
      .catch(() => { if (active) setFeedback("无法读取群聊记录，请刷新后重试。"); });
    return () => { active = false; };
  }, [client, worldId, group.conversation_id, refresh]);

  useEffect(() => {
    let active = true;
    void client.groupReplyAvailability(worldId)
      .then(result => { if (active) setAvailable(result.available); })
      .catch(() => { if (active) setAvailable(false); });
    return () => { active = false; };
  }, [client, worldId]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (sending || !available || (!draft.trim() && !pending)) return;
    const current = pending ?? { text: draft, ceiling: tokenCeiling, requestId: crypto.randomUUID() };
    setPending(current);
    setSending(true);
    setFeedback("");
    try {
      const sent = await client.sendGroupMessage(worldId, group.conversation_id, current.text, current.ceiling, current.requestId);
      setPending(null);
      setDraft("");
      setRefresh(value => value + 1);
      try {
        await client.generateGroupReply(worldId, group.conversation_id, sent.turn_id);
        setRefresh(value => value + 1);
      } catch (failure) {
        const turn = await client.groupTurn(worldId, group.conversation_id, sent.turn_id).catch(() => null);
        setRefresh(value => value + 1);
        if (turn?.state !== "completed") setFeedback(failure instanceof CoreRequestError && failure.status === 422
          ? "这一轮未获预算授权或额度已耗尽。请核对每轮 Token 额度、模型可信上界与费用预算；已有发言会保留，系统不会自动重试。"
          : "这一轮未能完整结束，已有发言仍会保留。为避免重复消耗，系统不会自动重试；你可以发送新消息。");
      }
    } catch (failure) {
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500) {
        setPending(null);
        setFeedback("消息未保存。请检查内容、当前世界和会话后修改重试。");
      } else {
        setFeedback("消息保存结果尚未确认。可重试保存同一条消息，不会创建重复回合。");
      }
    } finally { setSending(false); }
  };

  const names = new Map(group.participants.map(item => [item.character_id, item.character_name]));
  return <section ref={thread} className="chat-thread" aria-label="群聊">
    <div className="thread-heading"><button type="button" className="text-action" onClick={onBack}>返回聊天</button><h2>{group.participants.map(item => item.character_name).join("、")}</h2><span>群聊</span><button type="button" className="text-action transcript-refresh" onClick={() => setRefresh(value => value + 1)}>刷新记录</button></div>
    {messages === null ? <p className="thread-hint">正在读取消息…</p> : messages.length === 0 ? <div className="conversation-placeholder"><h2>还没有消息</h2><p>发一条消息，开始群聊。</p></div> : <ol className="message-list">{messages.map(message => {
      const own = message.sender_kind === "player" && message.sender_id === playerId;
      return <li key={message.message_id} className={`message-row ${own ? "own" : ""}`}><div className="message-bubble"><span className="message-sender">{own ? "我" : names.get(message.sender_id) ?? "角色"}</span><ChatMessageBody text={message.text} /><time dateTime={message.created_at_utc}>{new Date(message.created_at_utc).toLocaleString("zh-CN")}</time></div></li>;
    })}</ol>}
    <form className="chat-composer" onSubmit={event => void send(event)}>
      {feedback ? <p role="status" className="chat-feedback">{feedback}</p> : null}
      {!available ? <p className="chat-feedback">尚未配置可用的聊天模型或可信 Token 上限，暂时无法发送。</p> : null}
      <label htmlFor="group-chat-draft" className="sr-only">发送群聊消息</label>
      <textarea id="group-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={!available || sending || !!pending} maxLength={65536} placeholder="输入消息，或用 @角色名 指定下一位发言者…" rows={3} />
      <div className="chat-composer-actions"><small>回车发送 · Shift+回车换行 · 本轮所有发言共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small><button type="submit" className="primary-button" disabled={!available || sending || (!draft.trim() && !pending)}>{sending ? "正在处理…" : pending ? "重试保存" : "发送"}</button></div>
    </form>
  </section>;
}
