import { hierarchy, pack } from "d3-hierarchy";
import type { ActivityCharacterDirectory, ActivityLocation, SocialSnapshot } from "@dreamtalk/api-client";

export const DIAGRAM_SIZE = 600;
export const DIAGRAM_PAGE = 12;
export type Person = SocialSnapshot["characters"][number];
export type Connection = SocialSnapshot["connections"][number];
export type Point = { x: number; y: number };
export type DiagramView = { x: number; y: number; size: number };

export function clampView(view: DiagramView): DiagramView {
  const size = Math.max(150, Math.min(DIAGRAM_SIZE, view.size));
  return {
    size, x: Math.max(-150, Math.min(750 - size, view.x)),
    y: Math.max(-150, Math.min(750 - size, view.y)),
  };
}
export function zoomView(view: DiagramView, factor: number): DiagramView {
  const size = Math.max(150, Math.min(DIAGRAM_SIZE, view.size / factor));
  return clampView({ size, x: view.x + (view.size - size) / 2, y: view.y + (view.size - size) / 2 });
}
export function radialPositions(ids: string[], center: string | null): Map<string, Point> {
  const rest = ids.filter(id => id !== center);
  const result = new Map<string, Point>();
  if (center && ids.includes(center)) result.set(center, { x: 300, y: 300 });
  rest.forEach((id, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, rest.length);
    const radius = !center && rest.length === 1 ? 0 : 210;
    result.set(id, { x: 300 + radius * Math.cos(angle), y: 300 + radius * Math.sin(angle) });
  });
  return result;
}
export function confirmedConnections(social: SocialSnapshot): Connection[] {
  const roots = new Set(social.characters.map(person => person.root_import_id));
  const seen = new Set<string>();
  return social.connections.filter(link => {
    const first = link.first_root_import_id, second = link.second_root_import_id;
    if (first === second || !roots.has(first) || !roots.has(second)) return false;
    const key = [first, second].sort().join("\0");
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
}
export function locationPaths(locations: ActivityLocation[]): Map<string, string> {
  const byId = new Map(locations.map(place => [place.location_id, place]));
  return new Map(locations.map(place => {
    const parts = [place.name], seen = new Set([place.location_id]);
    let parent = place.parent_id;
    while (parent && !seen.has(parent)) {
      seen.add(parent); const ancestor = byId.get(parent); if (!ancestor) break;
      parts.unshift(ancestor.name); parent = ancestor.parent_id;
    }
    return [place.location_id, parts.join(" / ")];
  }));
}
export function placedCharacters(locations: ActivityLocation[], directory: ActivityCharacterDirectory | null, social: SocialSnapshot) {
  const places = new Set(locations.map(place => place.location_id));
  const people = new Set(social.characters.map(person => person.root_import_id));
  const seen = new Set<string>();
  return (directory?.items ?? []).filter(item => {
    if (!item.initialized || !item.current_location_id || !places.has(item.current_location_id) ||
      !people.has(item.root_import_id) || seen.has(item.root_import_id)) return false;
    seen.add(item.root_import_id); return true;
  });
}
export function occupancyCounts(locations: ActivityLocation[], directory: ActivityCharacterDirectory | null, social: SocialSnapshot): Map<string, number> {
  const byId = new Map(locations.map(place => [place.location_id, place]));
  const counts = new Map(locations.map(place => [place.location_id, 0]));
  for (const person of placedCharacters(locations, directory, social)) {
    let id = person.current_location_id; const seen = new Set<string>();
    while (id && !seen.has(id)) {
      seen.add(id); counts.set(id, (counts.get(id) ?? 0) + 1); id = byId.get(id)?.parent_id ?? null;
    }
  }
  return counts;
}
export type PlaceBubble = { id: string; name: string; kind: "place" | "person"; hidden?: boolean };
type PackedData = { item?: PlaceBubble; children?: PackedData[] };
export function packBubbles(items: PlaceBubble[]) {
  if (!items.length) return [];
  const root = hierarchy<PackedData>({ children: items.map(item => ({ item })) }).sum(node => node.item ? 1 : 0);
  return pack<PackedData>().size([DIAGRAM_SIZE, DIAGRAM_SIZE]).padding(24)(root)
    .leaves().map(node => ({ ...node.data.item!, x: node.x, y: node.y, r: node.r }));
}
export function shortLabel(name: string): string {
  const letters = Array.from(name);
  return letters.length > 3 ? letters.slice(0, 2).join("") + "…" : name;
}
