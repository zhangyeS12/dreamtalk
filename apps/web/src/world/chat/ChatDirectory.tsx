import { useId } from "react";
import type { ChatConversation, GroupChatConversation } from "@dreamtalk/api-client";
import { characterTint, companyTints } from "../tint";
import { WorldAvatar } from "./ThreadParts";
import styles from "./ChatDirectory.module.css";

type Kind = "direct" | "group";

/** The conversation directory: world events first, then real conversations only. */
export function ChatDirectory({
  conversations, groups, total, loading, failed, query, onQuery, unread, unreadError, onUnreadRetry, avatars,
  eventsOpen, selectedConversationId, selectedGroupId, canCreateGroup, onEvents, onSelect, onPin, onNewGroup, onContacts, onRetry,
}: {
  conversations: ChatConversation[]; groups: GroupChatConversation[]; total: number; loading: boolean; failed: boolean;
  query: string; onQuery: (value: string) => void; unread: (conversationId: string) => boolean; unreadError: boolean; onUnreadRetry: () => void;
  avatars: Record<string, string>; eventsOpen: boolean; selectedConversationId: string | null; selectedGroupId: string | null;
  canCreateGroup: boolean; onEvents: () => void; onSelect: (kind: Kind, id: string) => void; onPin: (kind: Kind, id: string, pinned: boolean) => void;
  onNewGroup: () => void; onContacts: () => void; onRetry: () => void;
}) {
  const searchId = useId();
  const filtering = query.trim().length > 0;
  return <aside className={styles.directory} aria-label="会话列表">
    <header className={styles.head}>
      <div><strong>聊天</strong><small>{loading ? "读取中" : failed ? "读取未完成" : `${total} 个会话`}</small></div>
      {canCreateGroup && <button type="button" className={styles.round} aria-label="新建群聊" title="新建群聊" onClick={onNewGroup}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      </button>}
    </header>
    <div className={styles.search}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
      <label className="sr-only" htmlFor={searchId}>搜索角色或群聊成员</label>
      <input id={searchId} className="dt-bare" type="search" value={query} onChange={event => onQuery(event.target.value)} placeholder="搜索角色或群聊成员" autoComplete="off" maxLength={120} />
      {query && <button type="button" aria-label="清除搜索" onClick={() => { onQuery(""); document.getElementById(searchId)?.focus(); }}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M7 17 17 7" /></svg>
      </button>}
    </div>
    <div className={styles.list}>
      <button type="button" className={styles.row} aria-pressed={eventsOpen} onClick={onEvents}>
        <span className={styles.event} aria-hidden="true">✦</span>
        <span className={styles.copy}><strong>世界事件</strong><small>你已获知的事件</small></span>
        <span className={styles.pinned}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 14.4 9l5.6.5-4.3 3.7 1.3 5.6L12 15.9 7 18.8l1.3-5.6L4 9.5 9.6 9Z" /></svg><span className="sr-only">置顶</span></span>
      </button>
      <div className={styles.section}>会话</div>
      {unreadError && <p className={styles.hint} role="status">新消息提示暂未更新。<button type="button" onClick={onUnreadRetry}>重新读取消息提示</button></p>}
      {failed && <div className={styles.hint} role="alert"><p>会话读取未完成，已读取的会话仍保留。</p><button type="button" disabled={loading} onClick={onRetry}>重新读取会话</button></div>}
      {loading && total === 0 ? <p className={styles.hint}>正在读取会话…</p>
        : failed && total === 0 ? null
        : total === 0 ? <div className={styles.empty}><h2>还没有会话</h2><p>在通讯录中选择角色，打开与他的会话。</p><button type="button" onClick={onContacts}>前往通讯录</button></div>
        : <>
          {groups.map(item => {
            const selected = !eventsOpen && selectedGroupId === item.conversation_id;
            const fresh = unread(item.conversation_id);
            const tints = companyTints(item.participants.map(person => person.character_id));
            return <div key={item.conversation_id} className={styles.wrap} data-selected={selected || undefined}>
              <button type="button" className={styles.row} aria-pressed={selected} onClick={() => onSelect("group", item.conversation_id)}>
                <span className={styles.stack} aria-hidden="true">{item.participants.slice(0, 2).map(person => <WorldAvatar key={person.character_id} name={person.character_name} url={avatars[person.root_import_id]} tint={tints.get(person.character_id)} size="s" />)}</span>
                <span className={styles.copy}><strong>{item.participants.map(member => member.character_name).join("、")}{fresh && <span className={styles.dot} role="img" aria-label="有未读角色消息" />}</strong><small>群聊 · {item.participants.length} 位角色</small></span>
              </button>
              <PinButton pinned={!!item.pinned} label={item.pinned ? "取消置顶群聊" : "置顶群聊"} onClick={() => onPin("group", item.conversation_id, !item.pinned)} />
            </div>;
          })}
          {conversations.map(item => {
            const selected = !eventsOpen && selectedConversationId === item.conversation_id;
            const fresh = unread(item.conversation_id);
            return <div key={item.conversation_id} className={styles.wrap} data-selected={selected || undefined}>
              <button type="button" className={styles.row} aria-pressed={selected} onClick={() => onSelect("direct", item.conversation_id)}>
                <WorldAvatar name={item.character_name} url={avatars[item.root_import_id]} tint={characterTint(item.character_id)} />
                <span className={styles.copy}><strong>{item.character_name}{fresh && <span className={styles.dot} role="img" aria-label="有未读角色消息" />}</strong><small>{fresh ? "新消息" : "私聊"}</small></span>
              </button>
              <PinButton pinned={!!item.pinned} label={item.pinned ? `取消置顶${item.character_name}` : `置顶${item.character_name}`} onClick={() => onPin("direct", item.conversation_id, !item.pinned)} />
            </div>;
          })}
        </>}
      {filtering && total > 0 && conversations.length + groups.length === 0 && <p className={styles.hint} role="status">没有匹配的会话。试试角色的名字。</p>}
    </div>
  </aside>;
}

function PinButton({ pinned, label, onClick }: { pinned: boolean; label: string; onClick: () => void }) {
  return <button type="button" className={styles.pin} data-active={pinned || undefined} aria-label={label} aria-pressed={pinned} title={pinned ? "取消置顶" : "置顶会话"} onClick={onClick}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 14.4 9l5.6.5-4.3 3.7 1.3 5.6L12 15.9 7 18.8l1.3-5.6L4 9.5 9.6 9Z" /></svg>
  </button>;
}
