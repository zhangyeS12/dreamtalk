import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatMessage } from "@dreamtalk/api-client";
import { ChatMessageBody } from "./ChatMessageBody";

export function ChatHistoryPanel({ client, worldId, conversationId, senderName, canQuote, onQuote, onClose }: {
  client: CoreClient; worldId: string; conversationId: string;
  senderName: (message: ChatMessage) => string; canQuote: boolean;
  onQuote: (text: string) => boolean; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const queryInput = useRef<HTMLInputElement>(null);
  const searchRequest = useRef<AbortController | null>(null);
  const contextRequest = useRef<AbortController | null>(null);
  const [query, setQuery] = useState("");
  const [searchedQuery, setSearchedQuery] = useState("");
  const [matches, setMatches] = useState<ChatMessage[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [scanned, setScanned] = useState(0);
  const [skipped, setSkipped] = useState(0);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<ChatMessage | null>(null);
  const [context, setContext] = useState<ChatMessage[] | null>(null);
  const [contextError, setContextError] = useState("");
  const [quoteError, setQuoteError] = useState("");

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    queryInput.current?.focus();
    return () => {
      searchRequest.current?.abort();
      contextRequest.current?.abort();
      element?.close();
    };
  }, []);

  const search = async (older: boolean) => {
    const topic = older ? searchedQuery : query.trim();
    if (!topic || (older && cursor === null)) return;
    searchRequest.current?.abort();
    contextRequest.current?.abort();
    const request = new AbortController();
    searchRequest.current = request;
    setSearching(true); setError(""); setSelected(null); setContext(null); setQuoteError("");
    if (!older) {
      setMatches([]); setCursor(null); setScanned(0); setSkipped(0); setSearchedQuery(topic);
    }
    try {
      const result = await client.searchChatHistory(worldId, conversationId, topic, older ? cursor! : undefined, request.signal);
      if (request.signal.aborted) return;
      setMatches(current => [...(older ? current : []), ...result.items.filter(item => !older || !current.some(saved => saved.message_id === item.message_id))].slice(0, 64));
      setCursor(result.next_before_position);
      setScanned(current => (older ? current : 0) + result.scanned_count);
      setSkipped(current => (older ? current : 0) + result.skipped_count);
    } catch (failure) {
      if (!request.signal.aborted) setError(failure instanceof CoreRequestError && [404, 409].includes(failure.status)
        ? "当前身份已变化或无法访问这段对话，请关闭后重新打开会话。"
        : "回忆检索未完成，请重试。不会调用模型。");
    } finally { if (!request.signal.aborted) setSearching(false); }
  };
  const submit = (event: FormEvent) => { event.preventDefault(); void search(false); };
  const viewContext = async (message: ChatMessage) => {
    contextRequest.current?.abort();
    const request = new AbortController();
    contextRequest.current = request;
    setSelected(message); setContext(null); setContextError(""); setQuoteError("");
    try {
      const page = await client.chatMessageContext(worldId, conversationId, message.position, request.signal);
      if (request.signal.aborted) return;
      if (!page.items.some(item => item.message_id === message.message_id)) {
        setContextError("这条消息暂时无法读取，请重新检索。");
        return;
      }
      setContext(page.items);
    } catch { if (!request.signal.aborted) setContextError("原文暂时无法读取，请重试。"); }
  };
  const quote = (message: ChatMessage) => {
    const text = `我们之前聊到过这段（${new Date(message.created_at_utc).toLocaleString("zh-CN")}）：\n${senderName(message)}说：“${message.text}”\n现在你怎么看？`;
    if (!onQuote(text)) setQuoteError("当前草稿加上这段原文会过长，请先缩短草稿再试。");
  };
  const source = (message: ChatMessage) => <><strong>{senderName(message)}</strong><time dateTime={message.created_at_utc}>{new Date(message.created_at_utc).toLocaleString("zh-CN")}</time><small>第 {message.position} 条消息</small></>;
  return <dialog ref={dialog} className="chat-history-dialog" aria-labelledby="chat-history-title" onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="history-heading"><h2 id="chat-history-title">聊天回忆</h2><button type="button" className="text-action" onClick={onClose}>关闭回忆</button></div>
    <p className="inline-hint">搜索这段共同对话，查看当时的原文，再接着聊。</p>
    <form className="history-search" onSubmit={submit}>
      <label htmlFor="history-query">回忆关键词</label>
      <div><input ref={queryInput} id="history-query" value={query} onChange={event => setQuery(event.target.value)} maxLength={256} placeholder="例如：生日、约定、喜欢的食物" /><button type="submit" className="primary-button" disabled={!query.trim() || searching}>{searching ? "正在检索…" : "查找回忆"}</button></div>
    </form>
    {error ? <p role="alert" className="history-error">{error}</p> : null}
    {quoteError ? <p role="alert" className="history-error">{quoteError}</p> : null}
    {selected ? <section className="history-context" aria-label="原文前后文">
      <div className="history-heading"><h3>原文前后文</h3><button type="button" className="text-action" onClick={() => { contextRequest.current?.abort(); setSelected(null); }}>返回检索结果</button></div>
      {contextError ? <p role="alert">{contextError} <button type="button" className="text-action" onClick={() => void viewContext(selected)}>重试读取</button></p> : context === null ? <p role="status">正在读取原文…</p> : <ol className="history-results">{context.map(message => <li key={message.message_id} className={message.message_id === selected.message_id ? "history-target" : ""} aria-current={message.message_id === selected.message_id ? "true" : undefined}><div className="history-source">{source(message)}{message.message_id === selected.message_id ? <span>命中消息</span> : null}</div><ChatMessageBody text={message.text} /></li>)}</ol>}
      {context !== null ? <button type="button" className="text-action" disabled={!canQuote} onClick={() => quote(selected)}>引用这段，继续聊</button> : null}
    </section> : <>
      {searchedQuery ? <p className="inline-hint" role="status">{searching ? "正在查找相关原文…" : `“${searchedQuery}”：已检索 ${scanned} 条，显示 ${matches.length} 条相关原文。`}</p> : null}
      {!searching && searchedQuery && scanned > 0 && matches.length === 0 ? <p>这些记录里没有相关原文。可以换关键词{cursor !== null ? "，或继续检索更早记录" : ""}。</p> : null}
      {!searching && searchedQuery && scanned === 0 && !error ? <p>这段对话还没有已保存的消息。</p> : null}
      <ol className="history-results">{matches.map(message => <li key={message.message_id}><div className="history-source">{source(message)}</div><ChatMessageBody text={message.text} /><div className="history-actions"><button type="button" className="text-action" onClick={() => void viewContext(message)}>查看前后文</button><button type="button" className="text-action" disabled={!canQuote} onClick={() => quote(message)}>引用这段，继续聊</button></div></li>)}</ol>
      {cursor !== null ? <button type="button" className="text-action" disabled={searching || matches.length >= 64} onClick={() => void search(true)}>继续检索更早记录</button> : scanned > 0 && !searching ? <p className="inline-hint">已检索到这段对话的开头。</p> : null}
      {matches.length >= 64 ? <p className="inline-hint">最多显示 64 条结果，请缩小关键词后重新检索。</p> : null}
      {skipped > 0 ? <p className="inline-hint">有 {skipped} 条较长消息未参与检索，可在聊天记录中查看。</p> : null}
    </>}
    <p className="history-footnote">本地检索，不调用模型。每批最多检索 100 条并显示 8 条相关原文。引用只填入草稿，确认发送后才会继续对话。</p>
  </dialog>;
}
