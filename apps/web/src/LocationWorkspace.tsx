import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { hierarchy, pack } from "d3-hierarchy";
import { CoreClient, CoreRequestError, type ActivityCharacter, type ActivityCharacterDirectory, type ActivityLocation, type LocationDraft, type Residency, type SocialSnapshot } from "@dreamtalk/api-client";
import { ContactAvatar } from "./ContactSocial";
import "./locations.css";

const messages: Record<string, string> = {
  invalid_location_name: "请输入 1 至 120 字的地点名称。",
  location_home_reserved: "“家”是系统初始地点，请使用其他名称。",
  location_not_editable: "系统初始“家”不能编辑。",
  location_name_exists: "当前世界已有同名地点。",
  location_parent_invalid: "父地点已不可用，或会造成循环包含。",
  location_occupied_access: "有角色当前或初始位置在这个分支。请先对该角色开放，或修改其初始地点后再隐藏。",
  location_scope_conflict: "这个调整会把角色当前位置移出活动范围。请先调整角色初始地点。",
  location_revision_changed: "地点已被更新，请刷新并重新选择这个地点后再编辑。草稿仍保留。",
  location_access_invalid: "开放对象已变化，请刷新角色列表。",
  location_catalog_capacity: "当前世界最多支持 32 个地点（含“家”）。",
  location_has_children: "此地点还有子地点。请先删除子地点，或修改子地点的父地点后再删除。",
  location_character_present: "有角色的初始地点或当前位置在这里。请先在角色资料中修改初始地点，将角色移到其他地点。",
  location_player_present: "玩家当前在这里，不能删除。请先调整玩家位置。",
  location_not_found: "此地点已不可用，请刷新地点目录。",
  activity_location_policy_changed: "位置规则已被更新，请刷新核对后重新保存。草稿仍保留。",
  activity_presence_changed: "角色已移动，请刷新当前位置后再保存；草稿仍保留。",
  activity_player_changed: "当前玩家身份已变化，请重新进入通讯录。",
  activity_location_hidden: "角色未获准进入这个隐藏分支，请先在地点编辑中对其开放。",
  activity_character_capacity: "当前世界最多支持 16 位活动角色。",
  activity_location_unavailable: "所选地点已不可用，请刷新后重新选择。",
  world_runtime_unavailable: "世界暂时不可修改，请恢复后用原请求重试。",
};
function failureText(error: unknown) { return error instanceof CoreRequestError ? messages[error.code ?? ""] ?? "保存未确认。草稿和原请求仍保留，请检查连接后用原请求重试。" : "保存未确认。草稿和原请求仍保留，请检查连接后用原请求重试。"; }
function terminal(error: unknown) { return error instanceof CoreRequestError && error.status >= 400 && error.status < 500; }

export function locationPaths(locations: ActivityLocation[]) {
  const byId = new Map(locations.map(item => [item.location_id, item]));
  return new Map(locations.map(item => {
    const names = [item.name], seen = new Set([item.location_id]); let parent = item.parent_id;
    while (parent && !seen.has(parent)) { seen.add(parent); const above = byId.get(parent); if (!above) break; names.unshift(above.name); parent = above.parent_id; }
    return [item.location_id, names.join(" / ")];
  }));
}
function canSee(locations: ActivityLocation[], character: string | undefined, location: string) {
  const seen = new Set<string>(); let item = locations.find(place => place.location_id === location);
  while (item) { if (seen.has(item.location_id) || (item.hidden && (!character || !item.allowed_character_ids.includes(character)))) return false; seen.add(item.location_id); if (!item.parent_id) return true; item = locations.find(place => place.location_id === item!.parent_id); }
  return false;
}

export function useLocationDirectory(client: CoreClient, worldId: string, visible: boolean) {
  const [locations, setLocations] = useState<ActivityLocation[]>([]);
  const [directory, setDirectory] = useState<ActivityCharacterDirectory | null>(null);
  const [error, setError] = useState("");
  const alive = useRef(true), serial = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++serial.current; }; }, []);
  const refresh = useCallback(async () => {
    const turn = ++serial.current;
    try { const [places, people] = await Promise.all([client.listActivityLocations(worldId), client.listActivityCharacters(worldId)]); if (alive.current && serial.current === turn) { setLocations(places); setDirectory(people); setError(""); } }
    catch { if (alive.current && serial.current === turn) setError("地点或角色位置读取未完成，保留上次读取的信息。请刷新重试。"); }
  }, [client, worldId]);
  useEffect(() => { if (!visible) return; void refresh(); const timer = window.setInterval(() => void refresh(), 5000); return () => { window.clearInterval(timer); ++serial.current; }; }, [refresh, visible]);
  return { locations, directory, error, refresh };
}

const blank: LocationDraft = { name: "", parent_id: null, hidden: false, is_region: false, allowed_character_ids: [] };
export function LocationManager({ client, worldId, locations, directory, refresh, onDirtyChange }: {
  client: CoreClient; worldId: string; locations: ActivityLocation[]; directory: ActivityCharacterDirectory | null; refresh: () => Promise<void>; onDirtyChange: (dirty: boolean) => void;
}) {
  const [editing, setEditing] = useState<ActivityLocation | null>(null);
  const [draft, setDraft] = useState<LocationDraft>(blank);
  const [changed, setChanged] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [pending, setPending] = useState<{ draft: LocationDraft; editing: ActivityLocation | null; requestId: string } | null>(null);
  const busyRef = useRef(false), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onDirtyChange(changed || !!pending || busy); return () => onDirtyChange(false); }, [changed, pending, busy, onDirtyChange]);
  const paths = locationPaths(locations);
  const choose = (item: ActivityLocation | null) => {
    if (busyRef.current || ((changed || pending) && !window.confirm("当前地点编辑尚未保存或结果未确认。请先核对列表；确定放弃草稿和本次重试吗？"))) return;
    setEditing(item); setDraft(item ? { name: item.name, parent_id: item.parent_id, hidden: item.hidden, is_region: item.is_region, allowed_character_ids: [...item.allowed_character_ids] } : blank); setChanged(false); setPending(null); setError(""); setNotice("");
  };
  const update = (value: Partial<LocationDraft>) => { setDraft(current => ({ ...current, ...value })); setChanged(true); };
  const descendants = (id: string) => { const seen = new Set<string>(); let parent: string | null = id; while (parent && !seen.has(parent)) { if (parent === editing?.location_id) return true; seen.add(parent); parent = locations.find(place => place.location_id === parent)?.parent_id ?? null; } return false; };
  async function save(event: FormEvent) {
    event.preventDefault(); if (busyRef.current || !draft.name.trim()) return;
    const request = pending ?? { draft: { ...draft, name: draft.name.trim() }, editing, requestId: crypto.randomUUID() };
    setPending(request); busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try {
      if (request.editing) await client.editActivityLocation(worldId, request.editing.location_id, request.draft, request.editing.revision, request.requestId);
      else await client.createActivityLocation(worldId, request.draft.name, request.requestId, request.draft);
      if (!alive.current) return; setPending(null); setChanged(false); setEditing(null); setDraft(blank); setNotice("地点已保存。新的包含关系与地区标记在下一常规规划批次使用。"); await refresh();
    } catch (failure) { if (alive.current) { setError(failureText(failure)); if (terminal(failure)) setPending(null); } }
    finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }
  async function remove() {
    if (!editing || busyRef.current || pending || !window.confirm(`删除地点“${editing.name}”？\n历史事件保留。存在子地点、玩家或未删除角色的初始／当前位置时，会提示先调整。${changed ? "\n当前未保存的地点编辑将被放弃。" : ""}`)) return;
    busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try {
      await client.removeActivityLocation(worldId, editing.location_id, editing.revision);
      if (!alive.current) return;
      setEditing(null); setDraft(blank); setChanged(false); setNotice("地点已删除，历史事件保留。"); await refresh();
    } catch (failure) { if (alive.current) setError(failure instanceof CoreRequestError && messages[failure.code ?? ""] ? messages[failure.code!] : "删除结果尚未确认，请刷新目录核对；可以再次删除同一地点。"); }
    finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }
  return <section className="location-manager" aria-label="添加与编辑地点"><div className="location-manager-heading"><div><h2>地点目录</h2><p>每个圆是一处可停留的地点，大圆包含小圆。</p></div><button className="text-action" disabled={busy} onClick={() => void refresh()}>刷新</button></div>
    <div className="location-editor-grid"><div className="location-catalog"><button type="button" className={`location-catalog-row ${!editing ? "selected" : ""}`} disabled={busy} onClick={() => choose(null)}>＋ 添加地点</button>{locations.map(item => <button type="button" key={item.location_id} className={`location-catalog-row ${editing?.location_id === item.location_id ? "selected" : ""}`} disabled={busy || item.is_home} onClick={() => choose(item)}><span>{paths.get(item.location_id)}</span><small>{item.is_home ? "系统初始地点" : item.hidden ? "隐藏分支" : item.is_region ? "地区节点" : "公开地点"}</small></button>)}</div>
    <form className="location-editor" onSubmit={event => void save(event)}><h3>{editing ? `编辑 ${editing.name}` : "添加地点"}</h3><label className="field"><span>地点名称</span><input maxLength={120} placeholder="例如：璃月城" disabled={busy || !!pending} value={draft.name} onChange={event => update({ name: event.target.value })} /></label><label className="field"><span>包含它的父地点</span><select value={draft.parent_id ?? ""} disabled={busy || !!pending} onChange={event => update({ parent_id: event.target.value || null })}><option value="">无父地点 · 独立区域</option>{locations.filter(place => !descendants(place.location_id)).map(place => <option key={place.location_id} value={place.location_id}>{paths.get(place.location_id)}</option>)}</select></label>
    <label className="location-check"><input type="checkbox" checked={draft.is_region} disabled={busy || !!pending} onChange={event => update({ is_region: event.target.checked })} /><span><strong>将此地点标记为地区</strong><small>例如璃月、蒙德。地区内可日常走动，跨地区只会极少远行；子地点归属最近的地区。未标记时按最上层地点划分。</small></span></label>
    <label className="location-check"><input type="checkbox" checked={draft.hidden} disabled={busy || !!pending} onChange={event => update({ hidden: event.target.checked })} /><span><strong>隐藏这个分支</strong><small>角色默认不能进入，也不会在活动规划中看到未获准地点。</small></span></label>
    {draft.hidden && <fieldset className="location-access"><legend>对以下角色开放</legend>{directory?.items.length ? directory.items.map(person => <label key={person.character_id} className="location-check"><input type="checkbox" disabled={busy || !!pending} checked={draft.allowed_character_ids.includes(person.character_id)} onChange={event => update({ allowed_character_ids: event.target.checked ? [...draft.allowed_character_ids, person.character_id] : draft.allowed_character_ids.filter(id => id !== person.character_id) })} />{person.name}</label>) : <p className="inline-hint">先在角色资料中保存初始地点，或打开一次会话，即可在这里选择开放对象。</p>}<p className="inline-hint">父地点隐藏时，整个分支继承限制；子地点也隐藏时，还需在子地点单独开放。</p></fieldset>}
    <button className="primary-button" type="submit" disabled={busy || (!pending && (!changed || !draft.name.trim()))}>{busy ? "正在保存…" : pending ? "用原请求重试" : editing ? "保存地点" : "添加地点"}</button>{pending && !busy && <button type="button" className="text-action" onClick={() => { if (window.confirm("原请求可能已经保存，请先刷新核对。确定结束重试并继续编辑吗？")) setPending(null); }}>结束本次重试</button>}
    {editing && <button type="button" className="text-action destructive-action" disabled={busy || !!pending} onClick={() => void remove()}>删除此地点</button>}
    {error && <p className="app-alert" role="alert">{error}</p>}{notice && <p className="app-notice" role="status">{notice}</p>}<p className="inline-hint">手动编辑不调用模型。自动活动会在已批准的常规批次中，将角色获准地点提供给已配置的模型。</p></form></div></section>;
}

export function CharacterLocationEditor({ client, worldId, person, activity, directory, locations, refresh, onDirtyChange }: {
  client: CoreClient; worldId: string; person: SocialSnapshot["characters"][number]; activity?: ActivityCharacter; directory: ActivityCharacterDirectory | null; locations: ActivityLocation[]; refresh: () => Promise<void>; onDirtyChange: (dirty: boolean) => void;
}) {
  const [root, setRoot] = useState(activity?.initial_location_id ?? ""), [locked, setLocked] = useState(activity?.locked ?? false);
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [residency, setResidency] = useState<Residency>(activity?.residency ?? "strong");
  const [pending, setPending] = useState<{ root: string; locked: boolean; residency: Residency; requestId: string; characterId: string | null; revision: number | null; policyRevision: number } | null>(null);
  const busyRef = useRef(false), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onDirtyChange(dirty || !!pending); return () => onDirtyChange(false); }, [dirty, pending, onDirtyChange]);
  const paths = locationPaths(locations), activeRoot = dirty || pending ? root : activity?.initial_location_id ?? root, activeLocked = dirty || pending ? locked : activity?.locked ?? locked, activeResidency = dirty || pending ? residency : activity?.residency ?? residency;
  async function save(event: FormEvent) {
    event.preventDefault(); if (busyRef.current || !activeRoot || !directory?.player_id) return;
    let request = pending ?? { root: activeRoot, locked: activeLocked, residency: activeResidency, requestId: crypto.randomUUID(), characterId: activity?.character_id ?? null, revision: activity?.revision ?? null, policyRevision: activity?.policy_revision ?? 0 };
    const playerId = directory.player_id; setPending(request); busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try {
      if (!request.characterId) { const contact = await client.openDirectConversation(worldId, person.current_import_id); request = { ...request, characterId: contact.character_id }; if (alive.current) setPending(request); }
      await client.configureCharacterLocation(worldId, playerId, request.characterId!, request.root, request.locked, request.revision, request.requestId, request.policyRevision, request.residency);
      if (!alive.current) return; setPending(null); setDirty(false); setRoot(request.root); setLocked(request.locked); setResidency(request.residency); setNotice(request.locked ? "已返回并锁定初始地点。" : "常驻中心与移动倾向已保存。新的倾向在下一常规规划批次使用。"); await refresh();
    } catch (failure) { if (alive.current) { setError(failureText(failure)); if (terminal(failure)) setPending(null); } }
    finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }
  return <form className="character-location-editor" onSubmit={event => void save(event)}><div><h3>初始地点与移动倾向</h3><p className="inline-hint">初始地点是常驻中心。角色可前往父地点、子地点和兄弟地点，离常驻中心越远越少见，并倾向返回；跨地区只会极少远行。</p></div><label className="field"><span>初始地点（常驻中心）</span><select value={activeRoot} disabled={busy || !!pending || !directory?.player_id} onChange={event => { setRoot(event.target.value); setLocked(activeLocked); setResidency(activeResidency); setDirty(true); }}><option value="">选择初始地点</option>{locations.map(place => <option key={place.location_id} value={place.location_id} disabled={!canSee(locations, activity?.character_id, place.location_id)}>{paths.get(place.location_id)}{canSee(locations, activity?.character_id, place.location_id) ? "" : " · 未开放"}</option>)}</select><small>首次保存或更改初始地点，会把角色放置到这里；已有活动会结束或中断。</small></label><label className="location-check"><input type="checkbox" checked={activeLocked} disabled={busy || !!pending || !activeRoot || !directory?.player_id} onChange={event => { setLocked(event.target.checked); setRoot(activeRoot); setResidency(activeResidency); setDirty(true); }} /><span><strong>锁定在初始地点</strong><small>若已在其他地点，会立即返回；原活动结束或中断。解锁后按常驻倾向活动。</small></span></label><label className="field"><span>常驻倾向</span><select value={activeResidency} disabled={busy || !!pending || !directory?.player_id} onChange={event => { setResidency(event.target.value as Residency); setRoot(activeRoot); setLocked(activeLocked); setDirty(true); }}><option value="normal">一般</option><option value="strong">强（默认）</option><option value="very_strong">很强</option></select><small>倾向越强，越常留在初始地点。锁定时此选项不产生移动；解锁后生效。</small></label>{activity?.current_location_id && <p className="location-current">当前位置：{paths.get(activity.current_location_id) ?? "目录外地点"}</p>}<button className="secondary-button" type="submit" disabled={busy || !activeRoot || !directory?.player_id || (!dirty && !pending)}>{busy ? "正在保存…" : pending ? "用原请求重试" : "保存位置规则"}</button>{!directory?.player_id && <p className="inline-hint">先在“我”中进入世界，再设置位置。</p>}{pending && !busy && <button className="text-action" type="button" onClick={() => { if (window.confirm("保存可能已完成，请先刷新核对。确定结束本次重试吗？")) setPending(null); }}>结束本次重试</button>}{error && <p className="app-alert" role="alert">{error}</p>}{notice && <p className="app-notice" role="status">{notice}</p>}</form>;
}

interface MapNode { id: string; kind: "root" | "place" | "label" | "person"; name: string; hidden?: boolean; person?: SocialSnapshot["characters"][number]; children?: MapNode[] }
export function LocationMap({ locations, directory, social, urls, selected, onSelect, onChat, openingChat, onEdit }: {
  locations: ActivityLocation[]; directory: ActivityCharacterDirectory | null; social: SocialSnapshot; urls: Record<string, string>; selected: string | null; onSelect: (root: string) => void; onChat: (id: string) => void; openingChat: boolean; onEdit: () => void;
}) {
  const prefix = useId().replace(/:/g, ""), svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, size: 1000 }), drag = useRef<{ x: number; y: number; view: typeof view; moved: boolean } | null>(null), moved = useRef(false);
  const layout = useMemo(() => {
    const build = (place: ActivityLocation, ancestors: Set<string>): MapNode => {
      const children: MapNode[] = [{ id: `label:${place.location_id}`, kind: "label", name: place.name, hidden: place.hidden }];
      for (const child of locations.filter(value => value.parent_id === place.location_id && !ancestors.has(value.location_id))) children.push(build(child, new Set([...ancestors, child.location_id])));
      for (const activity of directory?.items.filter(value => value.current_location_id === place.location_id) ?? []) { const person = social.characters.find(value => value.root_import_id === activity.root_import_id); if (person) children.push({ id: person.root_import_id, kind: "person", name: person.name, person }); }
      return { id: place.location_id, kind: "place", name: place.name, hidden: place.hidden, children };
    };
    const tree: MapNode = { id: "world", kind: "root", name: "", children: locations.filter(place => !place.parent_id || !locations.some(value => value.location_id === place.parent_id)).map(place => build(place, new Set([place.location_id]))) };
    return pack<MapNode>().size([1000, 1000]).padding(22)(hierarchy(tree).sum(node => node.kind === "label" ? 3 : node.kind === "person" ? 1 : 0).sort((a, b) => (b.value ?? 0) - (a.value ?? 0) || a.data.id.localeCompare(b.data.id))).descendants();
  }, [locations, directory, social]);
  const person = social.characters.find(value => value.root_import_id === selected), activity = directory?.items.find(value => value.root_import_id === selected);
  const placeName = (id: string | null | undefined) => locations.find(place => place.location_id === id)?.name ?? "尚未设置";
  const zoom = useCallback((factor: number) => { setView(current => { const size = Math.min(2000, Math.max(160, current.size * factor)); return { x: current.x + (current.size - size) / 2, y: current.y + (current.size - size) / 2, size }; }); }, []);
  useEffect(() => { const svg = svgRef.current; if (!svg) return; const wheel = (event: WheelEvent) => { event.preventDefault(); zoom(event.deltaY > 0 ? 1.12 : .89); }; svg.addEventListener("wheel", wheel, { passive: false }); return () => svg.removeEventListener("wheel", wheel); }, [zoom]);
  const focus = (id: string) => { if (moved.current) return; onSelect(id); const node = layout.find(value => value.data.id === id); if (node?.parent) { const size = Math.max(220, node.parent.r * 2.5); setView({ x: node.parent.x - size / 2, y: node.parent.y - size / 2, size }); } };
  const placed = new Set(directory?.items.filter(value => value.initialized).map(value => value.root_import_id));
  return <div className="location-map-stage"><div className="location-map-caption"><strong>地点</strong><span>大圆包含小圆 · 虚线为隐藏地点</span><span>拖动平移 · 滚轮缩放 · 点击头像查看</span></div><svg ref={svgRef} className="location-map" viewBox={`${view.x} ${view.y} ${view.size} ${view.size}`} aria-label="地点包含关系与角色位置" onPointerDown={event => { if (event.button !== 0) return; drag.current = { x: event.clientX, y: event.clientY, view, moved: false }; moved.current = false; }} onPointerMove={event => { const start = drag.current; if (!start) return; const rect = event.currentTarget.getBoundingClientRect(); const dx = event.clientX - start.x, dy = event.clientY - start.y; if (Math.hypot(dx, dy) > 5) { start.moved = true; moved.current = true; if (!event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.setPointerCapture(event.pointerId); const scale = start.view.size / Math.min(rect.width, rect.height); setView({ x: start.view.x - dx * scale, y: start.view.y - dy * scale, size: start.view.size }); } }} onPointerUp={event => { drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }} onPointerCancel={() => { drag.current = null; }}>
    <defs>{layout.filter(node => node.data.kind === "person").map(node => <clipPath key={node.data.id} id={`${prefix}-${node.data.id}`}><circle cx={node.x} cy={node.y} r={node.r} /></clipPath>)}</defs>
    {layout.filter(node => node.data.kind === "place").map(node => <circle key={node.data.id} cx={node.x} cy={node.y} r={node.r} className={`location-region depth-${Math.min(node.depth, 3)} ${node.data.hidden ? "hidden-place" : ""}`}><title>{locationPaths(locations).get(node.data.id)}</title></circle>)}
    {layout.filter(node => node.data.kind === "label").map(node => <text key={node.data.id} x={node.x} y={node.y} className="location-map-label" textAnchor="middle" dominantBaseline="middle" fontSize={Math.min(22, node.r * 1.5 / Math.max(2, Math.min(11, Array.from(node.data.name).length) + (node.data.hidden ? 2 : 0)))}><title>{node.data.name}</title>{node.data.hidden ? "◇ " : ""}{Array.from(node.data.name).length > 10 ? Array.from(node.data.name).slice(0, 10).join("") + "…" : node.data.name}</text>)}
    {layout.filter(node => node.data.kind === "person").map(node => <g key={node.data.id} role="button" tabIndex={0} aria-label={`${node.data.name}，${node.parent?.data.name ?? ""}`} className={`location-map-person ${selected === node.data.id ? "selected" : ""}`} onClick={() => focus(node.data.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); moved.current = false; focus(node.data.id); } }}><circle cx={node.x} cy={node.y} r={node.r} />{urls[node.data.person?.avatar_digest ?? ""] ? <image href={urls[node.data.person?.avatar_digest ?? ""]} x={node.x - node.r} y={node.y - node.r} width={node.r * 2} height={node.r * 2} preserveAspectRatio="xMidYMid slice" clipPath={`url(#${prefix}-${node.data.id})`} /> : <text x={node.x} y={node.y} textAnchor="middle" dominantBaseline="central" fontSize={node.r}>{Array.from(node.data.name)[0]}</text>}<title>{node.data.name}</title></g>)}
  </svg>{!locations.length && <div className="location-map-empty"><p>先为这个世界添加地点。</p><button type="button" className="secondary-button" onClick={onEdit}>添加地点</button></div>}
  {person && <aside className="social-focus-panel location-focus-panel" aria-label="选中角色地点"><button className="text-action social-close" onClick={() => onSelect("")}>收起详情</button><ContactAvatar className="social-focus-avatar" name={person.name} url={urls[person.avatar_digest ?? ""]} /><h3>{person.name}</h3><p>初始地点－当前位置</p><strong className="location-route">{placeName(activity?.initial_location_id)}－{placeName(activity?.current_location_id)}</strong><p>{activity?.locked ? "已锁定在初始地点" : activity?.initialized ? "以初始地点为常驻中心活动" : "尚未设置初始地点"}</p><button className="primary-button" disabled={!directory?.player_id || openingChat} onClick={() => onChat(person.current_import_id)}>打开会话</button></aside>}
  <div className="location-map-controls"><button onClick={() => zoom(.8)} aria-label="放大地点图">＋</button><button onClick={() => zoom(1.25)} aria-label="缩小地点图">－</button><button onClick={() => { setView({ x: 0, y: 0, size: 1000 }); onSelect(""); }}>总览</button><button onClick={onEdit}>编辑地点</button></div>{social.characters.some(value => !placed.has(value.root_import_id)) && <div className="location-unplaced"><span>未设置位置</span>{social.characters.filter(value => !placed.has(value.root_import_id)).map(value => <button key={value.root_import_id} onClick={() => onSelect(value.root_import_id)}>{value.name}</button>)}</div>}</div>;
}
