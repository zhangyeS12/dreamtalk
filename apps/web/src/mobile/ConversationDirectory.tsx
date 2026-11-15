import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, MessageCircle, Pin, Plus, Search, ShieldCheck, Users, X } from "lucide-react";
import type { ChatConversation, CoreClient, GroupChatConversation } from "@dreamtalk/api-client";
import { useChatAvatars } from "../useChatAvatars";
import { WorldAvatar } from "../world/chat/ThreadParts";
import { characterTint } from "../world/tint";

export type MobileConversation = ChatConversation | GroupChatConversation;
export function MobileConversationDirectory({ client, worldId, conversations, unread, onOpen, onNewGroup, onContacts, onPinned, busy = false }: {
  client: CoreClient; worldId: string; conversations: MobileConversation[]; unread: Record<string, number>;
  onOpen: (item: MobileConversation) => void; onNewGroup: () => void; onContacts: () => void;
  onPinned: (id: string, value: boolean) => void; busy?: boolean;
}) {
  const [query, setQuery] = useState(""), [kind, setKind] = useState("全部"), [page, setPage] = useState(0);
  const [pinning, setPinning] = useState<string | null>(null), [error, setError] = useState("");
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const entries = useMemo(() => conversations.map((item, index) => ({ item, index }))
    .filter(({ item }) => (kind === "全部" || item.kind === (kind === "私聊" ? "direct" : "group")) &&
      (item.kind === "direct" ? item.character_name : item.participants.map(p => p.character_name).join(" ")).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
    .sort((a, b) => Number(!!b.item.pinned) - Number(!!a.item.pinned) ||
      Number((unread[b.item.conversation_id] ?? 0) > 0) - Number((unread[a.item.conversation_id] ?? 0) > 0) || a.index - b.index),
  [conversations, kind, query, unread]);
  const last = Math.max(0, Math.ceil(entries.length / 30) - 1), currentPage = Math.min(page, last);
  const shown = entries.slice(currentPage * 30, currentPage * 30 + 30);
  const roots = shown.flatMap(({ item }) => item.kind === "direct" ? [item.root_import_id] : item.participants.slice(0, 2).map(p => p.root_import_id));
  const avatars = useChatAvatars(client, worldId, roots, true);
  async function pin(item: MobileConversation) {
    if (pinning || busy) return;
    setPinning(item.conversation_id); setError("");
    try {
      const result = await client.setConversationPinned(worldId, item.conversation_id, !item.pinned);
      if (mounted.current) onPinned(item.conversation_id, result.pinned);
    } catch { if (mounted.current) setError("置顶状态尚未确认，请重新读取会话后再试。"); }
    finally { if (mounted.current) setPinning(null); }
  }
  return <section className="mobile-directory" aria-label="会话目录">
    <div className="mobile-section-heading"><div><h2>你的对话</h2><p className="mobile-muted">从上次说到的地方，继续。</p></div>
      <button type="button" className="mobile-icon-action" aria-label="新建群聊" disabled={busy} onClick={onNewGroup}><Plus size={21}/></button></div>
    <label className="mobile-search"><Search size={18}/><input type="search" aria-label="搜索角色或群聊成员" placeholder="搜索角色或群聊成员" maxLength={120}
      value={query} onChange={e => { setQuery(e.target.value); setPage(0); }}/>{query && <button type="button" aria-label="清除会话搜索" onClick={() => { setQuery(""); setPage(0); }}><X size={16}/></button>}</label>
    <div className="mobile-segmented" role="group" aria-label="会话类型">{["全部","私聊","群聊"].map(label => <button type="button" key={label} aria-pressed={kind === label}
      onClick={() => { setKind(label); setPage(0); }}>{label}</button>)}</div>
    {error && <p className="mobile-error" role="alert">{error}</p>}
    {conversations.length === 0 ? <div className="mobile-empty"><MessageCircle size={30}/><h3>还没有会话</h3><p>在通讯录选择一位角色，开始新的故事。</p><button type="button" className="primary-button" onClick={onContacts}>打开通讯录</button></div>
      : entries.length === 0 ? <div className="mobile-empty"><Search size={28}/><h3>没有匹配的会话</h3><p>试试角色姓名，或切换会话类型。</p><button className="text-action" type="button" onClick={() => { setQuery(""); setKind("全部"); setPage(0); }}>查看全部会话</button></div>
      : <><div className="mobile-list-caption"><span>会话</span><small>置顶 · 未读 · 最近活动</small></div><ul className="mobile-conversation-list">{shown.map(({ item }) => {
        const name = item.kind === "direct" ? item.character_name : item.participants.map(p => p.character_name).join("、");
        const count = unread[item.conversation_id] ?? 0;
        return <li key={item.conversation_id} data-pinned={item.pinned || undefined}><button type="button" className="mobile-conversation-open" onClick={() => onOpen(item)}>
          {item.kind === "direct" ? <WorldAvatar name={name} url={avatars[item.root_import_id]} tint={characterTint(item.character_id)}/>
            : <span className="mobile-group-avatar" aria-hidden="true">{item.participants.length ? item.participants.slice(0, 2).map(p => <WorldAvatar key={p.character_id} name={p.character_name} url={avatars[p.root_import_id]} tint={characterTint(p.character_id)} size="s"/>) : <Users size={23}/>}</span>}
          <span className="mobile-conversation-copy"><strong>{name}</strong><small>{item.kind === "direct" ? "私聊" : "群聊 · " + item.participants.length + " 位角色"}{item.read_only ? " · 历史只读" : count > 0 ? " · 有新消息" : ""}</small></span>
          {count > 0 && <span className="mobile-unread-badge" aria-label={count + " 条未读"}>{count > 99 ? "99+" : count}</span>}
        </button><button type="button" className="mobile-pin-action" aria-label={(item.pinned ? "取消置顶" : "置顶") + name} aria-pressed={!!item.pinned}
          disabled={busy || pinning !== null} onClick={() => void pin(item)}><Pin size={15}/></button></li>;
      })}</ul>
      {last > 0 && <div className="mobile-pagination" aria-label="会话分页"><button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={17}/>上一页</button><span>{currentPage + 1} / {last + 1}</span><button type="button" disabled={currentPage === last} onClick={() => setPage(currentPage + 1)}>下一页<ChevronRight size={17}/></button></div>}</>}
    <p className="mobile-quiet-note"><ShieldCheck size={14}/>对话与身份按当前世界独立保存</p>
  </section>;
}
