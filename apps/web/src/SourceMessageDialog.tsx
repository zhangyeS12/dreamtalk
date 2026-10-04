import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CoreClient, CoreRequestError, type ChatMessage } from "@dreamtalk/api-client";
import { ChatMessageBody } from "./ChatMessageBody";
import { MessageTime } from "./MessageTime";

export function SourceMessageDialog({ client, worldId, conversationId, messageId, characters, onClose }: {
  client: CoreClient; worldId: string; conversationId: string; messageId: string;
  characters: readonly { character_id: string; character_name: string }[]; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef<AbortController | null>(null);
  const headingId = useId();
  const [items, setItems] = useState<ChatMessage[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const element = dialog.current; element?.showModal();
    return () => { request.current?.abort(); element?.close(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController(); request.current = controller;
    setItems(null); setError("");
    void client.chatMessageSource(worldId, conversationId, messageId, controller.signal)
      .then(page => {
        if (controller.signal.aborted) return;
        if (!page.items.some(message => message.message_id === messageId)) {
          setError("原消息暂时无法访问，已保存的来源原句仍保留。请关闭后核对当前世界和身份。");
          return;
        }
        setItems(page.items);
      })
      .catch(failure => {
        if (controller.signal.aborted) return;
        setError(failure instanceof CoreRequestError && [404, 409].includes(failure.status)
          ? "原消息暂时无法访问，已保存的来源原句仍保留。请关闭后核对当前世界和身份。"
          : "未能读取原文，请检查核心连接后重试。已保存的来源原句仍保留。");
      });
    return () => controller.abort();
  }, [client, worldId, conversationId, messageId, attempt]);

  const close = () => { request.current?.abort(); onClose(); };
  return createPortal(<dialog ref={dialog} className="memory-dialog chat-history-dialog" aria-labelledby={headingId}
    onCancel={event => { event.preventDefault(); event.stopPropagation(); close(); }}>
    <div className="thread-heading"><h2 id={headingId}>来源原文与前后文</h2><button type="button" onClick={close}>关闭原文</button></div>
    <p className="inline-hint">来自原会话，显示来源消息及前后各最多 3 条。原话可能是计划、传闻或自述，需要结合当时的时间和语境理解。</p>
    {error ? <p role="alert">{error} <button type="button" className="text-action" onClick={() => setAttempt(value => value + 1)}>重试读取</button></p>
      : items === null ? <p role="status">正在读取原文…</p>
      : <ol className="history-results">{items.map(message => <li key={message.message_id}
        className={message.message_id === messageId ? "history-target" : ""}
        aria-current={message.message_id === messageId ? "true" : undefined}>
        <div className="history-source"><strong>{message.sender_kind === "player" ? "玩家" : characters.find(character => character.character_id === message.sender_id)?.character_name ?? "其他角色"}</strong>
          <MessageTime message={message} />{message.message_id === messageId && <span>来源消息</span>}</div>
        <ChatMessageBody text={message.text} />
      </li>)}</ol>}
    <p className="history-footnote">只读取本地已保存的聊天，不调用模型。关闭后可以继续查看记忆或编辑批注。</p>
  </dialog>, document.body);
}
