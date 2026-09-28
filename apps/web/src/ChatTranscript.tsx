import { useEffect, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatConversation } from "@dreamtalk/api-client";
import { useChatScroll } from "./useChatScroll";
import { useTranscriptPages } from "./useTranscriptPages";
import { ChatMessageBody } from "./ChatMessageBody";
import { submitChatOnEnter } from "./chatComposerKeys";
import { chatPhaseFeedback, chatReplyFailureFeedback, chatReplyStateFeedback, chatSaveFailureFeedback, type ChatRequestPhase } from "./chatFeedback";

interface Props {
  client: CoreClient;
  worldId: string;
  playerId: string;
  conversation: ChatConversation;
  tokenCeiling: number;
  suggestedDraft?: string | null;
  onSuggestionUsed?: () => void;
  onBack: () => void;
}

export function ChatTranscript({ client, worldId, playerId, conversation, tokenCeiling, suggestedDraft, onSuggestionUsed, onBack }: Props) {
  const [refresh, setRefresh] = useState(0);
  const [available, setAvailable] = useState(false);
  const [draft, setDraft] = useState("");
  const [pendingSend, setPendingSend] = useState<{ text: string; ceiling: number; requestId: string } | null>(null);
  const [phase, setPhase] = useState<ChatRequestPhase>(null);
  const sending = phase !== null;
  const [feedback, setFeedback] = useState("");
  const { messages, failed, hasOlder, loadingOlder, loadOlder } = useTranscriptPages(client, worldId, conversation.conversation_id, refresh);
  const { thread, beforePrepend } = useChatScroll(messages);

  useEffect(() => {
    if (suggestedDraft) {
      setDraft(suggestedDraft);
      onSuggestionUsed?.();
    }
  }, [suggestedDraft, onSuggestionUsed]);

  useEffect(() => {
    let active = true;
    setAvailable(false);
    void client.directReplyAvailability(worldId).then(result => {
      if (active) setAvailable(result.available);
    }).catch(() => { if (active) setAvailable(false); });
    return () => { active = false; };
  }, [client, worldId]);

  const latestPlayerMessage = messages?.filter(message => message.sender_kind === "player" && message.sender_id === playerId).at(-1);
  const checkReply = async () => {
    if (sending || pendingSend || !latestPlayerMessage) return;
    setPhase("checking");
    setFeedback("");
    try {
      const turn = await client.directTurn(worldId, conversation.conversation_id, latestPlayerMessage.turn_id);
      setRefresh(value => value + 1);
      setFeedback(chatReplyStateFeedback(turn.state, "direct"));
    } catch { setFeedback(chatReplyStateFeedback(null, "direct")); }
    finally { setPhase(null); }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (sending || !available || (!draft.trim() && !pendingSend)) return;
    const current = pendingSend ?? { text: draft, ceiling: tokenCeiling, requestId: crypto.randomUUID() };
    setPendingSend(current);
    setPhase("saving");
    setFeedback("");
    try {
      const sent = await client.sendPlayerMessage(worldId, conversation.conversation_id, current.text, current.ceiling, current.requestId);
      setPendingSend(null);
      setDraft("");
      setRefresh(value => value + 1);
      setPhase("replying");
      try {
        await client.generateDirectReply(worldId, conversation.conversation_id, sent.turn_id);
        setRefresh(value => value + 1);
      } catch (failure) {
        // Query once for a completed reply; never replay an uncertain model call.
        setPhase("checking");
        const turn = await client.directTurn(worldId, conversation.conversation_id, sent.turn_id).catch(() => null);
        setRefresh(value => value + 1);
        setFeedback(turn?.state === "completed"
          ? chatReplyStateFeedback(turn.state, "direct")
          : chatReplyFailureFeedback(failure, "direct"));
      }
    } catch (failure) {
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500) {
        setPendingSend(null);
        setFeedback(chatSaveFailureFeedback(failure));
      } else {
        setFeedback("消息保存结果尚未确认。可重试保存同一条消息，不会创建重复回合。");
      }
    } finally {
      setPhase(null);
    }
  };

  return <section ref={thread} className="chat-thread" aria-label={`${conversation.character_name}的会话`}>
    <div className="thread-heading">
      <button type="button" className="text-action" onClick={onBack}>返回聊天</button>
      <h2>{conversation.character_name}</h2><span>私聊</span>
      <button type="button" className="text-action transcript-refresh" onClick={() => setRefresh(value => value + 1)}>刷新记录</button>
    </div>
    {failed ? <p className="thread-hint" role="alert">无法读取会话记录，请刷新后重试。</p> : null}
    {messages === null ? failed ? null : <p className="thread-hint">正在读取消息…</p>
        : messages.length === 0 ? <div className="conversation-placeholder"><h2>还没有消息</h2><p>发一条消息，开始与角色聊天。</p></div>
          : <>{hasOlder ? <div className="transcript-history"><button type="button" className="text-action" disabled={loadingOlder} onClick={() => void loadOlder(beforePrepend)}>{loadingOlder ? "正在加载…" : "加载更早消息"}</button></div> : null}<ol className="message-list">{messages.map(message => {
            const own = message.sender_kind === "player" && message.sender_id === playerId;
            return <li key={message.message_id} className={`message-row ${own ? "own" : ""}`}>
              <div className="message-bubble">
                <span className="message-sender">{own ? "我" : conversation.character_name}</span>
                <ChatMessageBody text={message.text} />
                <time dateTime={message.created_at_utc}>{new Date(message.created_at_utc).toLocaleString("zh-CN")}</time>
              </div>
            </li>;
          })}</ol></>}
    <form className="chat-composer" onSubmit={event => void send(event)}>
      {phase || feedback ? <p role="status" aria-live="polite" className="chat-feedback">{chatPhaseFeedback(phase, "direct") || feedback}</p> : null}
      {!available ? <p className="chat-feedback">尚未配置可用的聊天模型或路由及可信 Token 上限，暂时无法发送。</p> : null}
      <label htmlFor="direct-chat-draft" className="sr-only">发送给{conversation.character_name}的消息</label>
      <textarea id="direct-chat-draft" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={submitChatOnEnter} disabled={!available || sending || !!pendingSend} maxLength={65536} placeholder="输入消息…" rows={3} />
      <div className="chat-composer-actions"><small>回车发送 · Shift+回车换行 · 本轮输入与输出共用 {tokenCeiling.toLocaleString("zh-CN")} Token 上限</small>{latestPlayerMessage ? <button type="button" className="text-action" disabled={sending || !!pendingSend} onClick={() => void checkReply()}>检查回复状态</button> : null}<button type="submit" className="primary-button" disabled={!available || sending || (!draft.trim() && !pendingSend)}>{phase === "saving" ? "正在保存…" : phase === "replying" ? "等待回复…" : phase === "checking" ? "检查中…" : pendingSend ? "重试保存" : "发送"}</button></div>
    </form>
  </section>;
}
