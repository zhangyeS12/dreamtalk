import { Component, lazy, Suspense, useState, type ReactNode } from "react";
import type { SocialSnapshot } from "@dreamtalk/api-client";
import "./contact-social.css";

const RelationshipUniverse = lazy(() => import("./RelationshipUniverse"));

class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <p className="social-scene-error" role="alert">三维视图未能加载。可从左侧选择人物查看资料，重新打开程序后重试。</p> : this.props.children;
  }
}

export function ContactAvatar({ name, url, className = "" }: { name: string; url?: string; className?: string }) {
  return <span className={`contact-portrait ${className}`} aria-hidden="true">{url ? <img src={url} alt="" /> : Array.from(name.trim())[0] ?? "?"}</span>;
}

function factionPaths(social: SocialSnapshot): Map<string, string> {
  const byId = new Map(social.factions.map(item => [item.faction_id, item]));
  return new Map(social.factions.map(item => {
    const parts = [item.name], seen = new Set([item.faction_id]);
    let parent = item.parent_id;
    while (parent && !seen.has(parent)) {
      seen.add(parent); const ancestor = byId.get(parent); if (!ancestor) break;
      parts.unshift(ancestor.name); parent = ancestor.parent_id;
    }
    return [item.faction_id, parts.join(" / ")];
  }));
}

export function SocialGraph({ social, urls, selected, onSelect, onChat, canChat, openingChat, visible }: {
  social: SocialSnapshot; urls: Record<string, string>; selected: string | null; onSelect: (root: string) => void;
  onChat: (importId: string) => void; canChat: boolean; openingChat: boolean; visible: boolean;
}) {
  const person = social.characters.find(item => item.root_import_id === selected);
  const paths = factionPaths(social);
  const names = social.memberships.filter(item => item.root_import_id === selected).map(item => paths.get(item.faction_id)).filter(Boolean);
  return <div className="social-stage"><div className="social-stage-caption"><strong>人物关系网</strong><span>点击头像聚焦 · 拖动移动 · 滚轮缩放</span><span>右键拖动旋转视角 · 连线表示已确认相识</span></div>
    <SceneBoundary><Suspense fallback={<p className="social-scene-loading" role="status">正在打开人物星图…</p>}>{visible && social.characters.length > 0 && <RelationshipUniverse social={social} urls={urls} selected={selected} onSelect={onSelect} />}</Suspense></SceneBoundary>
    {social.characters.length === 0 && <p className="social-empty">添加角色并设置阵营后，在这里查看关系网。</p>}
    {person && <aside className="social-focus-panel" aria-label="选中角色详情"><button type="button" className="text-action social-close" onClick={() => onSelect("")}>收起详情</button><ContactAvatar name={person.name} url={urls[person.avatar_digest ?? ""]} className="social-focus-avatar" />
      <h3>{person.name}</h3><p>所属阵营</p><div className="social-faction-tags">{names.length ? names.map((name, index) => <span key={index}>{name}</span>) : <span>尚未加入阵营</span>}</div>
      <button className="primary-button" type="button" disabled={!canChat || openingChat} onClick={() => onChat(person.current_import_id)}>{openingChat ? "正在打开…" : canChat ? "打开会话" : "先进入世界"}</button>
    </aside>}
  </div>;
}

export function FactionManager({ social, selectedRoot, busy, onSelect, onCreate, onEdit, onRemove, onMembership }: {
  social: SocialSnapshot; selectedRoot: string | null; busy: boolean; onSelect: (root: string) => void;
  onCreate: (name: string, parent: string | null) => Promise<boolean>; onEdit: (id: string, name: string, parent: string | null) => Promise<boolean>;
  onRemove: (id: string) => void; onMembership: (id: string, root: string, enabled: boolean) => void;
}) {
  const [newName, setNewName] = useState("");
  const [newParent, setNewParent] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editParent, setEditParent] = useState("");
  const paths = factionPaths(social);
  const memberships = new Set(social.memberships.filter(item => item.root_import_id === selectedRoot).map(item => item.faction_id));
  const hierarchy: { item: SocialSnapshot["factions"][number]; depth: number }[] = [];
  const stack = social.factions.filter(item => !item.parent_id).reverse().map(item => ({ item, depth: 0 }));
  while (stack.length) {
    const branch = stack.pop()!; hierarchy.push(branch);
    stack.push(...social.factions.filter(item => item.parent_id === branch.item.faction_id).reverse().map(item => ({ item, depth: branch.depth + 1 })));
  }
  const options = social.factions.map(item => <option key={item.faction_id} value={item.faction_id}>{paths.get(item.faction_id)}</option>);
  return <section className="faction-manager"><h3>阵营与成员</h3><p>同一阵营的直接成员相互认识；父子阵营不共享成员。退出阵营保留已经建立的相识。</p>
    <label className="field faction-character-picker">编辑哪位角色的归属<select value={selectedRoot ?? ""} disabled={busy} onChange={event => onSelect(event.target.value)}><option value="">请选择角色</option>{social.characters.map(person => <option key={person.root_import_id} value={person.root_import_id}>{person.name}</option>)}</select></label>
    <form className="faction-create" onSubmit={event => { event.preventDefault(); void onCreate(newName, newParent || null).then(saved => { if (saved) setNewName(""); }); }}><label className="field faction-name-field">新阵营名称<input type="text" value={newName} maxLength={120} onChange={event => setNewName(event.target.value)} placeholder="例如：维多利亚家政" disabled={busy} /></label>
      <label className="field faction-parent-field">所属父阵营<select value={newParent} onChange={event => setNewParent(event.target.value)} disabled={busy}><option value="">无 · 顶层阵营</option>{options}</select></label>
      <button type="submit" className="primary-button" disabled={busy || !newName.trim()}>创建阵营</button></form>
    {editing && <form className="faction-create" onSubmit={event => { event.preventDefault(); void onEdit(editing, editName, editParent || null).then(saved => { if (saved) setEditing(null); }); }}><label className="field faction-name-field">修改名称<input type="text" value={editName} maxLength={120} onChange={event => setEditName(event.target.value)} disabled={busy} /></label>
      <label className="field faction-parent-field">父阵营<select value={editParent} onChange={event => setEditParent(event.target.value)} disabled={busy}><option value="">无 · 顶层阵营</option>{social.factions.filter(item => item.faction_id !== editing).map(item => <option key={item.faction_id} value={item.faction_id}>{paths.get(item.faction_id)}</option>)}</select></label>
      <button type="submit" disabled={busy || !editName.trim()}>保存修改</button><button type="button" className="text-action" disabled={busy} onClick={() => setEditing(null)}>取消</button></form>}
    <div className="faction-tree">{hierarchy.length ? hierarchy.map(({ item, depth }) => {
      const members = social.memberships.filter(member => member.faction_id === item.faction_id).map(member => social.characters.find(person => person.root_import_id === member.root_import_id)?.name).filter(Boolean);
      const hasMembers = social.memberships.some(member => member.faction_id === item.faction_id);
      const hasChildren = social.factions.some(child => child.parent_id === item.faction_id);
      const deletionHint = hasChildren && hasMembers ? "先移除直接成员，并删除或移走子阵营，再删除此阵营。" : hasChildren ? "先删除子阵营，或编辑子阵营并更换父阵营，再删除此阵营。" : hasMembers ? "先选择下方直接成员，取消所属阵营勾选，再删除此阵营。" : "删除空阵营不会清除已经建立的相识。";
      return <div key={item.faction_id} className="faction-branch" style={{ marginLeft: Math.min(depth, 10) * 18 }} title={paths.get(item.faction_id)}>
        <div className="faction-line"><span className="faction-indent">{depth ? "↳" : "◇"}</span><strong>{item.name}</strong>
          <button type="button" className="text-action" disabled={busy} onClick={() => { setNewParent(item.faction_id); setNewName(""); }}>创建子阵营</button>
          <button type="button" className="text-action" disabled={busy} onClick={() => { setEditing(item.faction_id); setEditName(item.name); setEditParent(item.parent_id ?? ""); }}>编辑</button>
          <button type="button" className="text-action destructive-action" disabled={busy || hasMembers || hasChildren || editing === item.faction_id} title={deletionHint} onClick={() => onRemove(item.faction_id)}>删除阵营</button>
        </div><p className="faction-members-copy">直接成员：{members.length ? members.join("、") : "尚无"}</p>
        <p className="inline-hint">{deletionHint}</p>
        {selectedRoot && <label className="faction-member"><input type="checkbox" checked={memberships.has(item.faction_id)} disabled={busy} onChange={event => onMembership(item.faction_id, selectedRoot, event.target.checked)} />{social.characters.find(person => person.root_import_id === selectedRoot)?.name}属于该阵营</label>}
      </div>;
    }) : <p>尚无阵营。创建后，选择角色并勾选所属阵营。</p>}</div>
  </section>;
}
