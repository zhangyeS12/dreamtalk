import { useEffect, useId, useMemo, useState } from "react";
import type { ActivityCharacterDirectory, ActivityLocation, SocialSnapshot } from "@dreamtalk/api-client";
import { DiagramCanvas } from "./DiagramCanvas";
import { DIAGRAM_PAGE, locationPaths, occupancyCounts, packBubbles, placedCharacters, shortLabel, type PlaceBubble } from "./diagramLayout";

export function PlaceDiagram({ locations, directory, social, onSelect, urls, onAvatarDigests }: {
  locations: ActivityLocation[]; directory: ActivityCharacterDirectory | null; social: SocialSnapshot;
  onSelect: (root: string) => void; urls: Record<string, string>; onAvatarDigests?: (digests: string) => void;
}) {
  const [focus, setFocus] = useState<string | null>(null), [page, setPage] = useState(0);
  const prefix = useId().replace(/:/g, "");
  const byId = useMemo(() => new Map(locations.map(place => [place.location_id, place])), [locations]);
  const paths = useMemo(() => locationPaths(locations), [locations]);
  const scope = byId.get(focus ?? "") ?? null;
  const placed = useMemo(() => placedCharacters(locations, directory, social), [locations, directory, social]);
  const counts = useMemo(() => occupancyCounts(locations, directory, social), [locations, directory, social]);
  const children = locations.filter(place => scope ? place.parent_id === scope.location_id : !place.parent_id || !byId.has(place.parent_id))
    .sort((a, b) => a.name.localeCompare(b.name) || a.location_id.localeCompare(b.location_id));
  const residents = scope ? placed.filter(person => person.current_location_id === scope.location_id) : [];
  const people = new Map(social.characters.map(person => [person.root_import_id, person]));
  const items: PlaceBubble[] = [
    ...children.map(place => ({ id: place.location_id, kind: "place" as const, name: place.name, hidden: place.hidden })),
    ...residents.map(person => ({ id: person.root_import_id, kind: "person" as const, name: people.get(person.root_import_id)!.name })),
  ];
  const last = Math.max(0, Math.ceil(items.length / DIAGRAM_PAGE) - 1), shownPage = Math.min(page, last);
  const slice = items.slice(shownPage * DIAGRAM_PAGE, (shownPage + 1) * DIAGRAM_PAGE);
  const bubbles = packBubbles(slice);
  const chain: ActivityLocation[] = [], seen = new Set<string>();
  let ancestor = scope;
  while (ancestor && !seen.has(ancestor.location_id)) {
    seen.add(ancestor.location_id); chain.unshift(ancestor); ancestor = byId.get(ancestor.parent_id ?? "") ?? null;
  }
  const hidden = chain.some(place => place.hidden);
  const digests = [...new Set(slice.filter(item => item.kind === "person").flatMap(item => people.get(item.id)?.avatar_digest ?? []))].sort().join(",");
  useEffect(() => { onAvatarDigests?.(digests); return () => onAvatarDigests?.(""); }, [digests, onAvatarDigests]);
  function choose(id: string | null) { setFocus(id); setPage(0); }
  return <div className="place-diagram">
    <nav className="diagram-breadcrumbs" aria-label="地点路径">
      <button type="button" aria-current={!scope ? "location" : undefined} onClick={() => choose(null)}>世界总览</button>
      {chain.map(place => <button key={place.location_id} type="button" aria-current={place.location_id === scope?.location_id ? "location" : undefined} onClick={() => choose(place.location_id)}>{place.name}</button>)}
    </nav>
    <label className="field">跳转地点<select value={scope?.location_id ?? ""} onChange={event => choose(event.target.value || null)}>
      <option value="">世界总览</option>{locations.map(place => <option key={place.location_id} value={place.location_id}>{paths.get(place.location_id)}{place.hidden ? " · 隐藏" : ""}</option>)}</select>
    </label>
    <p className="diagram-summary">{scope?.name ?? "世界地点"} · {children.length} 个下级地点
      {directory ? " · " + (scope ? residents.length + " 人当前在此" : placed.length + " 人已定位") : " · 位置尚未读取"}</p>
    {hidden && <p className="diagram-help">当前处于隐藏分支，仅作为地点作者视图显示。</p>}
    <DiagramCanvas key={(scope?.location_id ?? "world") + ":" + shownPage} label="地点包含图">{canActivate => <>
      <circle cx={300} cy={300} r={294} className={"diagram-enclosure" + (hidden ? " is-hidden" : "")} vectorEffect="non-scaling-stroke" />
      {bubbles.map((node, index) => {
        const person = node.kind === "person" ? people.get(node.id) : null;
        const radius = Math.min(node.r * .48, 48), clip = prefix + "-place-avatar-" + index;
        const activate = () => { if (node.kind === "place") choose(node.id); else onSelect(node.id); };
        const label = node.kind === "place" ? node.name + "，进入地点" + (node.hidden ? "，隐藏分支" : "") : node.name + "，当前位置：" + scope?.name + "，查看资料";
        return <g key={node.kind + ":" + node.id} role="button" tabIndex={0} aria-label={label}
          className={node.kind === "place" ? "diagram-place" + (node.hidden ? " is-hidden" : "") : "diagram-person"}
          onClick={() => { if (canActivate()) activate(); }}
          onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); } }}>
          <title>{node.kind === "place" ? paths.get(node.id) : node.name}</title>
          <circle cx={node.x} cy={node.y} r={node.r} className={node.kind === "place" ? "diagram-place-circle" : "diagram-resident-circle"} vectorEffect="non-scaling-stroke" />
          {node.kind === "place" ? <>
            <text x={node.x} y={node.y - 7} className="diagram-place-name" textAnchor="middle">{shortLabel(node.name)}</text>
            <text x={node.x} y={node.y + 32} className="diagram-place-count" textAnchor="middle">{directory ? (counts.get(node.id) ?? 0) + " 人" : "位置未读取"}</text>
          </> : <>
            <defs><clipPath id={clip}><circle cx={node.x} cy={node.y - 16} r={radius} /></clipPath></defs>
            {urls[person?.avatar_digest ?? ""] ? <image href={urls[person?.avatar_digest ?? ""]} x={node.x - radius} y={node.y - 16 - radius}
              width={radius * 2} height={radius * 2} preserveAspectRatio="xMidYMid slice" clipPath={"url(#" + clip + ")"} />
              : <text x={node.x} y={node.y - 16} className="diagram-initial" textAnchor="middle" dominantBaseline="central">{Array.from(node.name)[0]}</text>}
            <text x={node.x} y={node.y + radius + 21} className="diagram-name" textAnchor="middle">{shortLabel(node.name)}</text>
          </>}
        </g>;
      })}
    </>}</DiagramCanvas>
    {!items.length && <p role="status">{!locations.length ? "还没有地点，可以先添加地点。" : directory ? "这里没有下级地点或已定位角色。" : "位置尚未读取，请刷新地点信息。"}</p>}
    {items.length > DIAGRAM_PAGE && <div className="diagram-pagination" aria-label="地点图分页"><button disabled={!shownPage} onClick={() => setPage(shownPage - 1)}>上一页</button><span>{shownPage + 1} / {last + 1}</span><button disabled={shownPage === last} onClick={() => setPage(shownPage + 1)}>下一页</button></div>}
    <p className="diagram-help">大圆包含小圆。点地点逐级展开，点头像打开资料；虚线表示隐藏分支。圈大小仅用于排版，不代表真实面积。</p>
  </div>;
}
