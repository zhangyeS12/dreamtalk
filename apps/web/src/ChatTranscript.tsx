import { useEffect, useState } from "react";
import { CoreClient, type ChatConversation, type ChatMessage } from "@livingworld/api-client";

interface Props {
  client: CoreClient;
  worldId: string;
  playerId: string;
  conversation: ChatConversation;
  onBack: () => void;
}

export function ChatTranscript({ client, worldId, playerId, conversation, onBack }: Props) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setMessages(null);
    setFailed(false);
    void client.conversationMessages(worldId, conversation.conversation_id).then(items => {
      if (active) setMessages(items);
    }).catch(() => {
      if (active) setFailed(true);
    });
    return () => { active = false; };
  }, [client, worldId, conversation.conversation_id, refresh]);

  return <section className="chat-thread" aria-label={`${conversation.character_name}的会话`}>
    <div className="thread-heading">
      <button type="button" className="text-action" onClick={onBack}>返回聊天</button>
      <h2>{conversation.character_name}</h2><span>私聊</span>
      <button type="button" className="text-action transcript-refresh" onClick={() => setRefresh(value => value + 1)}>刷新记录</button>
    </div>
    {failed ? <p className="thread-hint" role="alert">无法读取会话记录，请重试。</p>
      : messages === null ? <p className="thread-hint">正在读取消息…</p>
        : messages.length === 0 ? <div className="conversation-placeholder"><h2>还没有消息</h2><p>会话已经保存。消息发送功能尚未开放。</p></div>
          : <ol className="message-list">{messages.map(message => {
            const own = message.sender_kind === "player" && message.sender_id === playerId;
            return <li key={message.message_id} className={`message-row ${own ? "own" : ""}`}>
              <div className="message-bubble">
                <span className="message-sender">{own ? "我" : conversation.character_name}</span>
                <p>{message.text}</p>
                <time dateTime={message.created_at_utc}>{new Date(message.created_at_utc).toLocaleString("zh-CN")}</time>
              </div>
            </li>;
          })}</ol>}
    {messages?.length ? <p className="transcript-status">消息发送功能尚未开放。</p> : null}
  </section>;
}
