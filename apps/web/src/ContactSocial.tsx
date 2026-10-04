import { useCallback, useMemo, useState } from "react";
import { ReactFlow, Background, Controls, Handle, Position, ReactFlowProvider, type Node, type NodeProps, useReactFlow } from "@xyflow/react";
import type { SocialSnapshot } from "@dreamtalk/api-client";
import "@xyflow/react/dist/style.css";
import "./contact-social.css";

type Person = SocialSnapshot["characters"][number];
type PortraitData = { name: string; url?: string; focused: boolean; focus: () => void };
type PortraitNode = Node<PortraitData, "portrait">;

export function ContactAvatar({ name, url, className = "" }: { name: string; url?: string; className?: string }) {
  return <span className={`contact-portrait ${className}`} aria-hidden="true">{url ? <img src={url} alt="" /> : Array.from(name.trim())[0] ?? "?"}</span>;
}

function Portrait({ data }: NodeProps<PortraitNode>) {
  return <>
    <Handle type="target" position={Position.Left} isConnectable={false} className="social-anchor" />
    <button type="button" className={`social-node nodrag ${data.focused ? "is-focused" : ""}`} aria-label={`查看${data.name}的阵营与会话`} aria-pressed={data.focused} onClick={data.focus}>
      <ContactAvatar name={data.name} url={data.url} /><span className="social-node-name">{data.name}</span>
    </button>
    <Handle type="source" position={Position.Right} isConnectable={false} className="social-anchor" />
  </>;
}

const nodeTypes = { portrait: Portrait };

function layout(characters: Person[], connections: SocialSnapshot["connections"]): Map<string, { x: number; y: number }> {
  const adjacency = new Map(characters.map(person => [person.root_import_id, new Set<string>()]));
  for (const edge of connections) {
    adjacency.get(edge.first_root_import_id)?.add(edge.second_root_import_id);
    adjacency.get(edge.second_root_import_id)?.add(edge.first_root_import_id);
  }
  const positions = new Map<string, { x: number; y: number }>();
  const seen = new Set<string>();
  const rowWidth = Math.max(1000, Math.sqrt(characters.length) * 270);
  let offsetX = 0, offsetY = 0, rowHeight = 0;
  const ordered = [...characters].sort((a, b) => (adjacency.get(b.root_import_id)?.size ?? 0) - (adjacency.get(a.root_import_id)?.size ?? 0) || a.name.localeCompare(b.name));
  for (const person of ordered) {
    if (seen.has(person.root_import_id)) continue;
    const queue = [person.root_import_id], group: string[] = [];
    seen.add(person.root_import_id);
    for (let index = 0; index < queue.length; index++) {
      const identity = queue[index]; group.push(identity);
      for (const peer of adjacency.get(identity) ?? []) if (!seen.has(peer)) { seen.add(peer); queue.push(peer); }
    }
    const rings = Math.ceil((Math.sqrt(group.length) - 1) / 2);
    const radius = group.length === 1 ? 0 : 185 + Math.max(0, rings - 1) * 145;
    const width = 180 + radius * 2, height = 170 + radius * 1.5;
    if (offsetX && offsetX + width > rowWidth) { offsetX = 0; offsetY += rowHeight + 90; rowHeight = 0; }
    const centerX = offsetX + width / 2, centerY = offsetY + height / 2;
    positions.set(group[0], { x: centerX, y: centerY });
    for (let index = 1; index < group.length; index++) {
      const ring = Math.ceil((Math.sqrt(index + 1) - 1) / 2);
      const start = (2 * ring - 1) ** 2;
      const count = Math.min(8 * ring, group.length - start);
      const angle = -Math.PI / 2 + 2 * Math.PI * (index - start) / count;
      const distance = 185 + (ring - 1) * 145;
      positions.set(group[index], { x: centerX + Math.cos(angle) * distance, y: centerY + Math.sin(angle) * distance * .75 });
    }
    offsetX += width + 90; rowHeight = Math.max(rowHeight, height);
  }
  return positions;
}

function Network({ social, urls, selected, onSelect }: {
  social: SocialSnapshot; urls: Record<string, string>; selected: string | null; onSelect: (root: string) => void;
}) {
  const { setCenter } = useReactFlow();
  const positions = useMemo(() => layout(social.characters, social.connections), [social]);
  const focus = useCallback((root: string) => {
    const point = positions.get(root);
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 250;
    if (point) void setCenter(point.x + 49, point.y + 45, { zoom: 1.12, duration });
    onSelect(root);
  }, [onSelect, positions, setCenter]);
  const nodes = useMemo<PortraitNode[]>(() => social.characters.map(person => ({
    id: person.root_import_id, type: "portrait", position: positions.get(person.root_import_id) ?? { x: 0, y: 0 },
    data: { name: person.name, url: urls[person.avatar_digest ?? ""], focused: selected === person.root_import_id, focus: () => focus(person.root_import_id) },
    draggable: false, selectable: false,
  })), [social, positions, selected, urls, focus]);
  const edges = useMemo(() => social.connections.map(edge => ({
    id: `${edge.first_root_import_id}-${edge.second_root_import_id}`, source: edge.first_root_import_id, target: edge.second_root_import_id,
    type: "straight", className: "social-link", selectable: false,
  })), [social]);
  return <ReactFlow<PortraitNode> nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: .35 }}
    nodesDraggable={false} nodesConnectable={false} nodesFocusable={false} edgesFocusable={false} panOnDrag zoomOnScroll minZoom={.15} maxZoom={1.8}
    ariaLabelConfig={{ "controls.zoomIn.ariaLabel": "放大关系网", "controls.zoomOut.ariaLabel": "缩小关系网", "controls.fitView.ariaLabel": "查看全部人物" }}
    aria-label="人物关系网，拖动空白处移动，滚轮缩放，点击头像查看人物">
    <Background color="#cbd7d2" gap={32} size={1} /><Controls showInteractive={false} />
  </ReactFlow>;
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

export function SocialGraph({ social, urls, selected, onSelect, onChat, canChat, openingChat }: {
  social: SocialSnapshot; urls: Record<string, string>; selected: string | null; onSelect: (root: string) => void;
  onChat: (importId: string) => void; canChat: boolean; openingChat: boolean;
}) {
  const person = social.characters.find(item => item.root_import_id === selected);
  const paths = factionPaths(social);
  const names = social.memberships.filter(item => item.root_import_id === selected).map(item => paths.get(item.faction_id)).filter(Boolean);
  return <div className="social-stage"><div className="social-stage-caption"><strong>人物关系网</strong><span>拖动移动 · 滚轮缩放 · 点击头像聚焦</span><span>连线表示已确认相识</span></div>
    <ReactFlowProvider><Network social={social} urls={urls} selected={selected} onSelect={onSelect} /></ReactFlowProvider>
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
    <label className="faction-character-picker">编辑哪位角色的归属<select value={selectedRoot ?? ""} disabled={busy} onChange={event => onSelect(event.target.value)}><option value="">请选择角色</option>{social.characters.map(person => <option key={person.root_import_id} value={person.root_import_id}>{person.name}</option>)}</select></label>
    <form className="faction-create" onSubmit={event => { event.preventDefault(); void onCreate(newName, newParent || null).then(saved => { if (saved) setNewName(""); }); }}><label>新阵营名称<input value={newName} maxLength={120} onChange={event => setNewName(event.target.value)} placeholder="例如：维多利亚家政" disabled={busy} /></label>
      <label>所属父阵营<select value={newParent} onChange={event => setNewParent(event.target.value)} disabled={busy}><option value="">无 · 顶层阵营</option>{options}</select></label>
      <button type="submit" className="primary-button" disabled={busy || !newName.trim()}>创建阵营</button></form>
    {editing && <form className="faction-create" onSubmit={event => { event.preventDefault(); void onEdit(editing, editName, editParent || null).then(saved => { if (saved) setEditing(null); }); }}><label>修改名称<input value={editName} maxLength={120} onChange={event => setEditName(event.target.value)} disabled={busy} /></label>
      <label>父阵营<select value={editParent} onChange={event => setEditParent(event.target.value)} disabled={busy}><option value="">无 · 顶层阵营</option>{social.factions.filter(item => item.faction_id !== editing).map(item => <option key={item.faction_id} value={item.faction_id}>{paths.get(item.faction_id)}</option>)}</select></label>
      <button type="submit" disabled={busy || !editName.trim()}>保存修改</button><button type="button" className="text-action" disabled={busy} onClick={() => setEditing(null)}>取消</button></form>}
    <div className="faction-tree">{hierarchy.length ? hierarchy.map(({ item, depth }) => {
      const members = social.memberships.filter(member => member.faction_id === item.faction_id).map(member => social.characters.find(person => person.root_import_id === member.root_import_id)?.name).filter(Boolean);
      return <div key={item.faction_id} className="faction-branch" style={{ marginLeft: Math.min(depth, 10) * 18 }} title={paths.get(item.faction_id)}>
        <div className="faction-line"><span className="faction-indent">{depth ? "↳" : "◇"}</span><strong>{item.name}</strong>
          <button type="button" className="text-action" disabled={busy} onClick={() => { setNewParent(item.faction_id); setNewName(""); }}>创建子阵营</button>
          <button type="button" className="text-action" disabled={busy} onClick={() => { setEditing(item.faction_id); setEditName(item.name); setEditParent(item.parent_id ?? ""); }}>编辑</button>
          <button type="button" className="text-action" disabled={busy} onClick={() => onRemove(item.faction_id)}>删除</button>
        </div><p className="faction-members-copy">直接成员：{members.length ? members.join("、") : "尚无"}</p>
        {selectedRoot && <label className="faction-member"><input type="checkbox" checked={memberships.has(item.faction_id)} disabled={busy} onChange={event => onMembership(item.faction_id, selectedRoot, event.target.checked)} />{social.characters.find(person => person.root_import_id === selectedRoot)?.name}属于该阵营</label>}
      </div>;
    }) : <p>尚无阵营。创建后，选择角色并勾选所属阵营。</p>}</div>
  </section>;
}
