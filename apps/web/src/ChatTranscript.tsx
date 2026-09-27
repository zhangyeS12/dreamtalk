import { useEffect, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatConversation, type ChatMessage } from "@dreamtalk/api-client";
import { useChatScroll } from "./useChatScroll";
import { ChatMessageBody } from "./ChatMessageBody";
import { submitChatOnEnter } from "./chatComposerKeys";

interface Props {
  client: CoreClient;
  worldId: string;
  playerId: string;
  conversation: ChatConversation;
  tokenCeiling: number;
  onBack: () => void;
}

export function ChatTranscript({ client, worldId, playerId, conversation, tokenCeiling, onBack }: Props) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [available, setAvailable] = useState(false);
  const [draft, setDraft] = useState("");
  const [pendingSend, setPendingSend] = useState<{ text: string; ceiling: number; requestId: string } | null>(null);
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState("");
  const thread = useChatScroll(messages);

  useEffect(() => {
    let active = true;
    setFailed(false);
    void client.conversationMessages(worldId, conversation.conversation_id).then(items => {
      if (active) setMessages(items);
    }).catch(() => {
      if (active) setFailed(true);
    });
    return () => { active = false; };
  }, [client, worldId, conversation.conversation_id, refresh]);

  useEffect(() => {
    let active = true;
    setAvailable(false);
    void client.directReplyAvailability(worldId).then(result => {
      if (active) setAvailable(result.available);
    }).catch(() => { if (active) setAvailable(false); });
    return () => { active = false; };
  }, [client, worldId]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (sending || !available || (!draft.trim() && !pendingSend)) return;
    const current = pendingSend ?? { text: draft, ceiling: tokenCeiling, requestId: crypto.randomUUID() };
    setPendingSend(current);
    setSending(true);
    setFeedback("");
    try {
      const sent = await client.sendPlayerMessage(worldId, conversation.conversation_id, current.text, current.ceiling, current.requestId);
      setPendingSend(null);
      setDraft("");
      setRefresh(value => value + 1);
      try {
        await client.generateDirectReply(worldId, conversation.conversation_id, sent.turn_id);
        setRefresh(value => value + 1);
      } catch (failure) {
        // Query once for a completed reply; never replay an uncertain model call.
        const turn = await client.directTurn(worldId, conversation.conversation_id, sent.turn_id).catch(() => null);
        if (turn?.state === "completed") setRefresh(value => value + 1);
        else setFeedback(failure instanceof CoreRequestError && failure.status === 422
          ? "这轮回复未获预算授权。请核对每轮 Token 额度、模型可信上界与费用预算；消息已保存，系统不会自动重试模型调用。"
          : "这轮回复未完成。为避免重复消耗，系统不会自动重试；你可以继续发送新消息。");
      }
    } catch (failure) {
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500) {
        setPendingSend(null);
        setFeedback("消息未保存。请检查内容、当前世界和会话后修改重试。");
      } else {
        setFeedback("消息保存结果尚未确认。可重试保存同一条消息，不会创建重复回合。");
      }
    } finally {
      setSending(false);
    }
  };

  return <section ref={thread} className="chat-thread" aria-label={`${conversation.character_name}的会话`}>
    <div className="thread-heading">
      <button type="button" className="text-action" onClick={onBack}>返回聊天</button>
      <h2>{conversation.character_name}</h2><span>私聊</span>
      <button type="button" className="text-action transcript-refresh" onClick={() => setRefresh(value => value + 1)}>刷新记录</button>
    </div>
    {failed ? <p className="thread-hint" role="alert">无法读取会话记录，请重试。</p>
      : messages === null ? <p className="thread-hint">正在读取消息…</p>
        : messages.length === 0 ? <div className="conversation-placeholder"><h2>还没有消息</h2><p>发一条消息，开始与角色聊天。</p></div>
          : <ol className="message-list">{messages.map(message => {
            const own = message.sender_kind === "player" && message.sender_id === playerId;
            return <li key={message.message_id} className={`message-row ${own ? "own" : ""}`}>
              <div className="message-bubble">
                <span className="message-sender">{own ? "我" : conversation.character_name}</span>
                <ChatMessageBody text={message.text} />
                <time dateTime={message.created_at_utc}>{new Date(message.created_at_utc).toLocaleString("zh-CN")}</time>
              </div>
            </li>;
          })}</ol>}
    <form className="chat-composer" onSubmit={event => void send(event)}>
      {feedback ? <p role="status" className="chat-feedback">{feedback}</p> : null}
      {!available ? <p className="chat-feedback">尚未配置可用的聊天模型或路由及可信 Token 上限，暂时无法发送。</p> : null}
      <label htmlFor="direct-chat-draft" className="sr-only">发送给{conversation.character_name}的消息</label>
      <textarea id="direct-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={!available || sending || !!pendingSend} maxLength={65536} placeholder="输入消息…" rows={3} />
      <div className="chat-composer-actions"><small>回车发送 · Shift+回车换行 · 本轮输入与输出共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small><button type="submit" className="primary-button" disabled={!available || sending || (!draft.trim() && !pendingSend)}>{sending ? "正在处理…" : pendingSend ? "重试保存" : "发送"}</button></div>
    </form>
  </section>;
}
