import { useEffect, useRef, type ReactNode } from "react";
import { CoreClient, type WorldSettings } from "@dreamtalk/api-client";
import { BookFaces } from "./BookFaces";
import { useWorldCovers } from "./useWorldCovers";
import "./settings-handbook.css";

export const settingsPages = [
  { id: "model", label: "模型与聊天", scope: "当前世界", hint: "当前世界模型与本机共用聊天额度" },
  { id: "background", label: "后台运行", scope: "应用设置", hint: "登录启动与系统托盘" },
  { id: "time", label: "世界时间", scope: "当前世界", hint: "时间状态与推进速度" },
  { id: "activities", label: "角色活动", scope: "当前世界", hint: "日常活动、相遇与共同休闲" },
  { id: "offline", label: "主动联系", scope: "当前世界", hint: "共同邀请、未回复限制与离线消息" },
  { id: "news", label: "世界动态", scope: "当前世界", hint: "批量事件池与发布状态" },
  { id: "about", label: "关于与诊断", scope: "应用设置", hint: "版本、程序位置与本机连接" },
] as const;
export type SettingsPage = typeof settingsPages[number]["id"];
export function SettingsHandbook({ client, world, visible, page, onPage, dirtyPages, panels, onArchive }: {
  client: CoreClient; world: WorldSettings | undefined; visible: boolean; page: SettingsPage;
  onPage: (page: SettingsPage) => void; dirtyPages: Partial<Record<SettingsPage, boolean>>;
  panels: Record<SettingsPage, ReactNode>; onArchive: () => void;
}) {
  const covers = useWorldCovers(client, world?.world_id, visible && Boolean(world));
  const heading = useRef<HTMLHeadingElement>(null);
  const previous = useRef(page);
  useEffect(() => {
    if (visible && previous.current !== page) heading.current?.focus({ preventScroll: true });
    previous.current = page;
  }, [page, visible]);
  const selected = settingsPages.find(item => item.id === page)!;
  return <div className="settings-handbook" hidden={!visible}>
    <aside className="handbook-index">
      <div className="handbook-world">
        <div className="handbook-mini-book" aria-hidden="true"><span className="book-volume"><BookFaces name={world?.name ?? "世界档案"} appearance={world ? covers.appearances[world.world_id] : undefined} /></span></div>
        <div><span>当前世界</span><strong>{world?.name ?? "正在读取…"}</strong><small>世界管理手册</small></div>
      </div>
      <nav aria-label="设置分类">{settingsPages.map(item => <button key={item.id} type="button" aria-current={page === item.id ? "page" : undefined} aria-controls={`settings-${item.id}`} onClick={() => onPage(item.id)}>
        <span>{item.label}{dirtyPages[item.id] && <small className="handbook-dirty">未保存</small>}</span><small>{item.scope}</small>
      </button>)}</nav>
      {covers.error && <p className="handbook-cover-error">封面暂未读取，使用文字外观。<button type="button" className="text-action" onClick={() => void covers.refresh()}>重试封面</button></p>}
      <button type="button" className="text-action handbook-return" onClick={onArchive}>返回世界书架</button>
    </aside>
    <div className="handbook-sheet">
      <header className="handbook-page-heading"><div><h2 ref={heading} tabIndex={-1}>{selected.label}</h2><p>{selected.hint}</p></div><span className="handbook-scope">{selected.scope}{selected.scope !== "应用设置" && world ? ` · ${world.name}` : ""}</span></header>
      {settingsPages.map(item => <div key={item.id} id={`settings-${item.id}`} className="handbook-panel" hidden={page !== item.id}>{panels[item.id]}</div>)}
    </div>
  </div>;
}
export function SettingsFold({ title, summary, children, open = false }: { title: string; summary: string; children: ReactNode; open?: boolean }) {
  return <details className="handbook-fold" open={open}><summary><strong>{title}</strong><span>{summary}</span></summary>{children}</details>;
}
