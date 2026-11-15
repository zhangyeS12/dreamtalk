import { expect, test } from "vitest";
import type { SocialSnapshot } from "@dreamtalk/api-client";
import { atlasFactionPaths, atlasGroupView, atlasHit, atlasNodes, homeAtlasView, layoutAtlas, visibleAtlasNodes, zoomAtlas } from "./atlasLayout";

function fixture(count: number): SocialSnapshot {
  return { characters: Array.from({ length: count }, (_, i) => ({
    root_import_id: "root" + i, current_import_id: "current" + i, character_id: "character" + i,
    name: "人物" + i, avatar_digest: null,
  })), factions: [{ faction_id: "a", parent_id: null, name: "北方" }, { faction_id: "b", parent_id: "a", name: "分部" }],
  memberships: Array.from({ length: count }, (_, i) => ({ root_import_id: "root" + i, faction_id: i % 2 ? "a" : "b" })), connections: [] };
}
test("each root is drawn once with overlapping memberships and shuffled input", () => {
  const social = fixture(120); social.memberships.push({ root_import_id: "root0", faction_id: "a" });
  const layout = layoutAtlas(social.characters, social);
  expect(new Set(layout.nodes.map(n => n.id)).size).toBe(120);
  expect(layout).toEqual(layoutAtlas([...social.characters].reverse(), { ...social, memberships: [...social.memberships].reverse() }));
  for (const node of layout.nodes) expect(Math.hypot(node.x - 500, node.y - 500) + node.r).toBeLessThan(415);
});
test("only explicit membership selects a display sector; cycles remain bounded", () => {
  const social = fixture(3); social.memberships = [{ root_import_id: "root0", faction_id: "b" }];
  social.factions[0].parent_id = "b";
  const layout = layoutAtlas(social.characters, social);
  expect(layout.nodes.find(n => n.id === "root1")?.group).toBe("");
  expect(layout.nodes.find(n => n.id === "root0")?.group).toBe("b");
  expect(atlasFactionPaths(social).get("b")?.length).toBeLessThan(40);
});
test("focus relocates only one portrait and restores the exact overview geometry", () => {
  const social = fixture(55), layout = layoutAtlas(social.characters, social);
  const nodes = atlasNodes(layout, "root1");
  expect(nodes.find(n => n.id === "root1")).toMatchObject({ x: 500, y: 500, r: 58 });
  expect(nodes.filter(n => n.id !== "root1")).toEqual(layout.nodes.filter(n => n.id !== "root1"));
  expect(atlasNodes(layout, null)).toEqual(layout.nodes);
});
test("zoom anchors, culling and hits share world coordinates", () => {
  const social = fixture(12), layout = layoutAtlas(social.characters, social), node = layout.nodes[0];
  const view = atlasGroupView(layout, node.group);
  const inside = visibleAtlasNodes(layout.nodes, view);
  expect(inside.some(p => p.id === node.id)).toBe(true);
  expect(atlasHit(layout.nodes, view, (node.x - view.x) / view.size * 400, (node.y - view.y) / view.size * 400, 400)?.id).toBe(node.id);
  const next = zoomAtlas(homeAtlasView(), 2, { x: .2, y: .3 });
  expect(next).toEqual({ x: 100, y: 150, size: 500 });
  expect(zoomAtlas(next, .0001)).toEqual(homeAtlasView());
});
test("empty, solo and dense metadata never creates synthetic people", () => {
  for (const count of [0, 1, 200, 500]) {
    const social = fixture(count), layout = layoutAtlas(social.characters, social);
    expect(layout.nodes).toHaveLength(count);
    expect(layout.nodes.every(n => Number.isFinite(n.x + n.y + n.r))).toBe(true);
  }
});


test("two hundred portraits do not overlap or collide with a focused center", () => {
  const social = fixture(200), layout = layoutAtlas(social.characters, social);
  for (let i = 0; i < layout.nodes.length; i++) {
    const a = layout.nodes[i];
    expect(Math.hypot(a.x - 500, a.y - 500) - a.r).toBeGreaterThan(62);
    for (let j = i + 1; j < layout.nodes.length; j++) {
      const b = layout.nodes[j];
      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(a.r + b.r);
    }
  }
});
