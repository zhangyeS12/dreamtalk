import type { SocialSnapshot } from "@dreamtalk/api-client";
import type { Person, Connection, Point } from "./diagramLayout";

export const ATLAS_SIZE = 1000;
export type AtlasView = { x: number; y: number; size: number };
export type AtlasNode = Point & { id: string; r: number; person: Person; group: string; color: string };
export type AtlasGroup = { id: string; name: string; color: string; start: number; end: number; count: number };
export type AtlasLayout = { nodes: AtlasNode[]; groups: AtlasGroup[] };
const COLORS = ["#92c8df", "#d4b78c", "#b5a6dc", "#92cbb5", "#ddaab2", "#a7bce5", "#d5c98f", "#9dcbd1"];
export const homeAtlasView = (): AtlasView => ({ x: 0, y: 0, size: ATLAS_SIZE });

export function atlasFactionPaths(social: SocialSnapshot): Map<string, string> {
  const byId = new Map(social.factions.map(f => [f.faction_id, f]));
  return new Map(social.factions.map(f => {
    const names = [f.name], seen = new Set([f.faction_id]); let parent = f.parent_id;
    while (parent && !seen.has(parent)) {
      seen.add(parent); const item = byId.get(parent); if (!item) break;
      names.unshift(item.name); parent = item.parent_id;
    }
    return [f.faction_id, names.join(" / ")];
  }));
}
function colorFor(id: string) {
  let hash = 0; for (const char of id) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return COLORS[hash % COLORS.length];
}
/** Display grouping is not a primary faction or a new world fact. Each root occurs once. */
export function layoutAtlas(people: Person[], social: SocialSnapshot, faction = ""): AtlasLayout {
  const paths = atlasFactionPaths(social);
  const memberships = new Map<string, string[]>();
  for (const member of social.memberships) if (paths.has(member.faction_id)) {
    const values = memberships.get(member.root_import_id) ?? [];
    if (!values.includes(member.faction_id)) values.push(member.faction_id);
    memberships.set(member.root_import_id, values);
  }
  const unique = [...new Map(people.map(person => [person.root_import_id, person])).values()]
    .sort((a, b) => a.name.localeCompare(b.name) || a.root_import_id.localeCompare(b.root_import_id));
  const buckets = new Map<string, Person[]>();
  for (const person of unique) {
    const ids = (memberships.get(person.root_import_id) ?? [])
      .sort((a, b) => paths.get(a)!.localeCompare(paths.get(b)!) || a.localeCompare(b));
    const key = faction && ids.includes(faction) ? faction : ids[0] ?? "";
    const bucket = buckets.get(key) ?? []; bucket.push(person); buckets.set(key, bucket);
  }
  const ordered = [...buckets].sort(([a], [b]) => !a ? 1 : !b ? -1 :
    paths.get(a)!.localeCompare(paths.get(b)!) || a.localeCompare(b));
  const gap = Math.min(.075, 1 / Math.max(1, ordered.length));
  const sweep = Math.PI * 2 - gap * ordered.length;
  const nodes: AtlasNode[] = [], groups: AtlasGroup[] = [];
  let angle = -Math.PI / 2;
  const pitch = unique.length <= 12 ? 110 : unique.length <= 28 ? 60 : unique.length <= 72 ? 50 : unique.length <= 200 ? 42 : Math.max(8, 6200 / unique.length);
  for (const [id, members] of ordered) {
    const span = sweep * members.length / Math.max(1, unique.length);
    const start = angle + gap / 2, end = start + span, color = id ? colorFor(id) : "#b5bed1";
    groups.push({ id, name: id ? paths.get(id)! : "未加入阵营", color, start, end, count: members.length });
    let remaining = members.length, offset = 0;
    for (let lane = 0; remaining > 0; lane++) {
      const radius = Math.max(88, 366 - lane * 56);
      const capacity = Math.max(1, Math.floor(span * radius / pitch));
      const count = lane >= 5 ? remaining : Math.min(remaining, capacity);
      const step = span / count;
      const r = Math.min(unique.length <= 12 ? 42 : unique.length <= 28 ? 26 : unique.length <= 72 ? 22 : Math.min(18, pitch * .43),
        Math.max(.75, radius * Math.sin(step / 2) * .78));
      for (let index = 0; index < count; index++) {
        const theta = start + step * (index + .5), person = members[offset + index];
        nodes.push({ id: person.root_import_id, person, group: id, color, r,
          x: unique.length === 1 ? 500 : 500 + Math.cos(theta) * radius,
          y: unique.length === 1 ? 500 : 500 + Math.sin(theta) * radius });
      }
      offset += count; remaining -= count;
    }
    angle += span + gap;
  }
  return { nodes, groups };
}
export function atlasNodes(layout: AtlasLayout, center: string | null): AtlasNode[] {
  return layout.nodes.map(node => node.id === center ? { ...node, x: 500, y: 500, r: 58 } : node);
}
export function atlasNeighbors(connections: Connection[], root: string | null): Set<string> {
  return new Set(connections.flatMap(edge => edge.first_root_import_id === root ? [edge.second_root_import_id]
    : edge.second_root_import_id === root ? [edge.first_root_import_id] : []));
}
export function clampAtlasView(view: AtlasView): AtlasView {
  const size = Math.max(ATLAS_SIZE / 6, Math.min(ATLAS_SIZE, view.size));
  return { size, x: Math.max(-80, Math.min(ATLAS_SIZE + 80 - size, view.x)),
    y: Math.max(-80, Math.min(ATLAS_SIZE + 80 - size, view.y)) };
}
export function zoomAtlas(view: AtlasView, factor: number, anchor: Point = { x: .5, y: .5 }): AtlasView {
  const size = Math.max(ATLAS_SIZE / 6, Math.min(ATLAS_SIZE, view.size / factor));
  if (size === ATLAS_SIZE) return homeAtlasView();
  return clampAtlasView({ x: view.x + anchor.x * (view.size - size), y: view.y + anchor.y * (view.size - size), size });
}
export function atlasGroupView(layout: AtlasLayout, group: string): AtlasView {
  const points = layout.nodes.filter(node => node.group === group);
  if (!points.length) return homeAtlasView();
  const left = Math.min(...points.map(p => p.x - p.r)), right = Math.max(...points.map(p => p.x + p.r));
  const top = Math.min(...points.map(p => p.y - p.r)), bottom = Math.max(...points.map(p => p.y + p.r));
  const size = Math.max(220, Math.max(right - left, bottom - top) + 120);
  return clampAtlasView({ size, x: (left + right - size) / 2, y: (top + bottom - size) / 2 });
}
export function visibleAtlasNodes(nodes: AtlasNode[], view: AtlasView): AtlasNode[] {
  return nodes.filter(node => node.x + node.r >= view.x && node.x - node.r <= view.x + view.size &&
    node.y + node.r >= view.y && node.y - node.r <= view.y + view.size);
}
export function atlasHit(nodes: AtlasNode[], view: AtlasView, x: number, y: number, width: number): AtlasNode | undefined {
  const point = { x: view.x + x / width * view.size, y: view.y + y / width * view.size };
  const padding = 8 * view.size / Math.max(width, 1);
  return nodes.map(node => ({ node, distance: Math.hypot(point.x - node.x, point.y - node.y) }))
    .filter(({ node, distance }) => distance <= node.r + padding)
    .sort((a, b) => a.distance - b.distance)[0]?.node;
}
