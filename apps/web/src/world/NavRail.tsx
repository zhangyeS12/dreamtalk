import type { ReactElement } from "react";
import styles from "./NavRail.module.css";

export type WorldTab = "chats" | "contacts" | "settings" | "me";

/** Product order is fixed: 聊天／通讯录／设置／我. */
export const WORLD_TABS: ReadonlyArray<{ id: WorldTab; label: string }> = [
  { id: "chats", label: "聊天" },
  { id: "contacts", label: "通讯录" },
  { id: "settings", label: "设置" },
  { id: "me", label: "我" },
];

const ICONS: Record<WorldTab, ReactElement> = {
  chats: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5 9 9 0 0 1-3.6-.7L4 20l1.5-4.2a7.5 7.5 0 1 1 14.5-4.3Z" /><path d="M8.5 11.5h7" /></>,
  contacts: <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16.5 5.5a3 3 0 0 1 0 5.5M17 14a5 5 0 0 1 3.5 5" /></>,
  settings: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>,
  me: <><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
};

export function NavRail({ tab, unread, onSelect }: { tab: WorldTab; unread: boolean; onSelect: (tab: WorldTab) => void }) {
  return <nav className={styles.rail} aria-label="主导航">
    {WORLD_TABS.map(item => <button key={item.id} type="button" className={styles.item}
      aria-label={item.label} aria-current={tab === item.id ? "page" : undefined}
      onClick={() => { if (tab !== item.id) onSelect(item.id); }}>
      <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">{ICONS[item.id]}</svg>
      <span className={styles.label} aria-hidden="true">{item.label}</span>
      {item.id === "chats" && unread && <span className={styles.unread} role="img" aria-label="有未读角色消息" />}
    </button>)}
  </nav>;
}
