import { afterEach, beforeEach, expect, test, vi, type MockInstance } from "vitest";
import { cleanup, fireEvent, render, screen, within, waitFor, act } from "@testing-library/react";
import { useState } from "react";
import type { ActivityCharacter, ActivityCharacterDirectory, ActivityLocation, SocialSnapshot } from "@dreamtalk/api-client";
import { ContactRelations, ContactPlaces } from "./ContactLists";
import { DiagramCanvas } from "./DiagramCanvas";
import * as atlasPainter from "./atlasPaint";
import { atlasNodes } from "./atlasLayout";
import { confirmedConnections, DIAGRAM_PAGE, occupancyCounts, packBubbles, placedCharacters, radialPositions, zoomView } from "./diagramLayout";

function person(index: number) {
  return { root_import_id: "root-" + index, current_import_id: "import-" + index, character_id: "character-" + index,
    name: ["角色甲", "角色乙", "角色丙"][index] ?? "角色" + index, avatar_digest: "avatar-" + index };
}
function socialFixture(): SocialSnapshot {
  return { characters: [person(0), person(1), person(2)], factions: [{ faction_id: "f", parent_id: null, name: "同班" }],
    memberships: [{ faction_id: "f", root_import_id: "root-0" }, { faction_id: "f", root_import_id: "root-2" }],
    connections: [{ first_root_import_id: "root-0", second_root_import_id: "root-1", faction_ids: [] }] };
}
function place(id: string, name: string, parent_id: string | null = null, hidden = false): ActivityLocation {
  return { location_id: id, name, parent_id, hidden, is_home: id === "home", is_region: false, allowed_character_ids: [], revision: 1 };
}
function placesFixture() {
  const social = socialFixture(), locations = [place("campus", "校园"), place("room", "教室", "campus"),
    place("secret", "隐藏仓库", "campus", true), place("home", "家")];
  const item = (index: number, current: string, initialized = true): ActivityCharacter => ({
    character_id: "character-" + index, root_import_id: "root-" + index, name: person(index).name, initialized,
    initial_location_id: "home", current_location_id: current, locked: false, residency: "strong", revision: 1, policy_revision: 0,
  });
  const directory: ActivityCharacterDirectory = { player_id: "player", items: [item(0, "room"), item(1, "home"), item(2, "room", false)] };
  return { social, locations, directory };
}
function RelationHarness({ social = socialFixture(), digests = vi.fn() }: { social?: SocialSnapshot; digests?: (digests: string) => void }) {
  const [root, setRoot] = useState("root-0");
  return <ContactRelations social={social} selected={root} onChoose={setRoot} onProfile={vi.fn()} onAvatarDigests={digests} />;
}
class TestPointerEvent extends MouseEvent {
  pointerId: number;
  constructor(type: string, init: MouseEventInit & { pointerId?: number } = {}) {
    super(type, init); this.pointerId = init.pointerId ?? 1;
  }
}
let paints: MockInstance<typeof atlasPainter.paintAtlas>;
beforeEach(() => {
  vi.stubGlobal("PointerEvent", TestPointerEvent);
  const context = { setTransform: vi.fn(), clearRect: vi.fn(), save: vi.fn(), restore: vi.fn(), scale: vi.fn(), translate: vi.fn(),
    rotate: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), stroke: vi.fn(), moveTo: vi.fn(), bezierCurveTo: vi.fn(),
    clip: vi.fn(), drawImage: vi.fn(), fillText: vi.fn(), createRadialGradient: () => ({ addColorStop: vi.fn() }) };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  paints = vi.spyOn(atlasPainter, "paintAtlas");
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function lastAtlas() { return paints.mock.calls.at(-1)!; }
function focusPerson(name: string) {
  fireEvent.change(screen.getByLabelText("搜索关系图角色"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "聚焦" + name }));
  fireEvent.change(screen.getByLabelText("搜索关系图角色"), { target: { value: "" } });
}
function tapPerson(root: string, drag = false) {
  const args = lastAtlas(), node = atlasNodes(args[1], args[5]).find(item => item.id === root)!;
  const chart = screen.getByRole("img", { name: "阵营环形人物关系图" });
  vi.spyOn(chart, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 600, height: 600, x: 0, y: 0,
    right: 600, bottom: 600, toJSON: () => ({}) });
  const x = (node.x - args[3].x) / args[3].size * 600, y = (node.y - args[3].y) / args[3].size * 600;
  fireEvent.pointerDown(chart, { pointerId: 1, button: 0, clientX: x, clientY: y });
  if (drag) fireEvent.pointerMove(chart, { pointerId: 1, button: 0, clientX: x + 50, clientY: y });
  fireEvent.pointerUp(chart, { pointerId: 1, button: 0, clientX: x + (drag ? 50 : 0), clientY: y });
}
test("ring overview includes unconnected people and only confirmed edges", () => {
  render(<RelationHarness />);
  expect(screen.getByRole("img", { name: "阵营环形人物关系图" })).toBeTruthy();
  expect(lastAtlas()[1].nodes).toHaveLength(3);
  expect(lastAtlas()[2]).toEqual([{ first_root_import_id: "root-0", second_root_import_id: "root-1", faction_ids: [] }]);
  expect(lastAtlas()[5]).toBeNull();
  expect(screen.getByRole("button", { name: "全局总览" }).getAttribute("aria-pressed")).toBe("true");
});
test("search chooses a center and a second person opens existing relationship details", () => {
  render(<RelationHarness />);
  focusPerson("角色甲");
  expect(lastAtlas()[5]).toBe("root-0");
  tapPerson("root-1");
  const dialog = screen.getByRole("dialog", { name: "角色甲与角色乙" });
  expect(within(dialog).getByText("已确认相识")).toBeTruthy();
  expect(within(dialog).getByText("相识依据：已有相识记录")).toBeTruthy();
  fireEvent.click(within(dialog).getByRole("button", { name: "聚焦角色乙" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(lastAtlas()[5]).toBe("root-1");
});
test("same faction does not fabricate acquaintance in a pair sheet", () => {
  render(<RelationHarness />); focusPerson("角色甲"); tapPerson("root-2");
  const dialog = screen.getByRole("dialog", { name: "角色甲与角色丙" });
  expect(within(dialog).getByText("尚无已确认相识记录")).toBeTruthy();
  expect(lastAtlas()[2]).toHaveLength(1);
  fireEvent.click(within(dialog).getByRole("button", { name: "返回关系网" }));
  expect(lastAtlas()[5]).toBe("root-0");
  expect(lastAtlas()[6]).toBeNull();
});
test("overview is not split into twelve-person pages; list avatars remain paged", async () => {
  const social = socialFixture(), digests = vi.fn();
  social.characters = Array.from({ length: 55 }, (_, index) => person(index)); social.connections = [];
  render(<RelationHarness social={social} digests={digests} />);
  expect(lastAtlas()[1].nodes).toHaveLength(55);
  expect(screen.queryByLabelText("关系分页")).toBeNull();
  await waitFor(() => expect(digests.mock.calls.at(-1)?.[0].split(",")).toHaveLength(55));
  fireEvent.click(screen.getByRole("button", { name: "列表" }));
  expect(digests.mock.calls.at(-1)?.[0].split(",")).toHaveLength(30);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(digests.mock.calls.at(-1)?.[0].split(",")).toHaveLength(25);
});
test("search and direct-faction filters remove absent people and edges", () => {
  render(<RelationHarness />);
  fireEvent.change(screen.getByLabelText("筛选阵营"), { target: { value: "f" } });
  expect(lastAtlas()[1].nodes).toHaveLength(2); expect(lastAtlas()[2]).toHaveLength(0);
  fireEvent.change(screen.getByLabelText("搜索关系图角色"), { target: { value: "角色乙" } });
  expect(screen.getByText("没有匹配的角色。")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("筛选阵营"), { target: { value: "" } });
  expect(lastAtlas()[1].nodes.map(node => node.id)).toEqual(["root-1"]);
  expect(lastAtlas()[2]).toHaveLength(0);
});
test("deleting a selected root removes its focus, pair and stale edges", () => {
  const social = socialFixture(), props = { selected: "root-0", onChoose: vi.fn(), onProfile: vi.fn() };
  const { rerender } = render(<ContactRelations social={social} {...props} />);
  focusPerson("角色甲"); tapPerson("root-1");
  rerender(<ContactRelations social={{ ...social, characters: social.characters.slice(1) }} {...props} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(lastAtlas()[1].nodes.map(node => node.id)).not.toContain("root-0");
  expect(lastAtlas()[2]).toHaveLength(0); expect(lastAtlas()[5]).toBeNull();
});
test("unsaved selection guard still prevents moving the center", () => {
  const choose = vi.fn(() => false);
  render(<ContactRelations social={socialFixture()} selected="root-0" onChoose={choose} onProfile={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "个人关系" }));
  expect(choose).toHaveBeenCalledWith("root-0"); expect(lastAtlas()[5]).toBeNull();
});
test("atlas has keyboard selection and no idle animation loop", () => {
  const frame = vi.spyOn(window, "requestAnimationFrame"), choose = vi.fn();
  render(<ContactRelations social={socialFixture()} selected="root-0" onChoose={choose} onProfile={vi.fn()} />);
  const first = lastAtlas()[1].nodes[0].id;
  fireEvent.keyDown(screen.getByRole("img", { name: "阵营环形人物关系图" }), { key: "Enter" });
  expect(choose).toHaveBeenCalledWith(first); expect(lastAtlas()[5]).toBe(first);
  expect(frame).not.toHaveBeenCalled();
});
test("atlas dragging cannot accidentally choose a person", () => {
  const choose = vi.fn();
  render(<ContactRelations social={socialFixture()} selected="root-0" onChoose={choose} onProfile={vi.fn()} />);
  tapPerson("root-1", true); expect(choose).not.toHaveBeenCalled(); expect(lastAtlas()[5]).toBeNull();
});
test("closing pair details preserves the viewport", () => {
  render(<RelationHarness />); focusPerson("角色甲");
  fireEvent.click(screen.getByRole("button", { name: "放大环形关系图" }));
  const view = { ...lastAtlas()[3] }; tapPerson("root-1");
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "关闭两人详情" }));
  expect(lastAtlas()[3]).toEqual(view); expect(lastAtlas()[5]).toBe("root-0");
});
test("native close synchronizes pair state and the same pair can reopen", () => {
  render(<RelationHarness />); focusPerson("角色甲"); tapPerson("root-1");
  const dialog = screen.getByRole("dialog");
  dialog.removeAttribute("open"); fireEvent(dialog, new Event("close")); expect(screen.queryByRole("dialog")).toBeNull();
  tapPerson("root-1"); expect(screen.getByRole("dialog", { name: "角色甲与角色乙" })).toBeTruthy();
});
test("dense sectors zoom further instead of trapping every tap at the same scale", () => {
  const social = socialFixture(); social.characters = Array.from({ length: 120 }, (_, i) => person(i)); social.memberships = [];
  render(<RelationHarness social={social} />);
  const before = lastAtlas()[3].size; tapPerson("root-10");
  expect(lastAtlas()[3].size).toBeLessThan(before);
  tapPerson("root-10"); expect(lastAtlas()[5]).toBe("root-10");
});
test("invalid, duplicate, reversed and self connections are excluded", () => {
  const social = socialFixture();
  social.connections.push({ first_root_import_id: "root-1", second_root_import_id: "root-0", faction_ids: [] },
    { first_root_import_id: "root-0", second_root_import_id: "missing", faction_ids: [] },
    { first_root_import_id: "root-1", second_root_import_id: "root-1", faction_ids: [] });
  expect(confirmedConnections(social)).toHaveLength(1);
});
test("place circles drill down and show an occupant only at the current physical location", () => {
  const props = placesFixture(), digests = vi.fn(), open = vi.fn();
  render(<ContactPlaces {...props} onSelect={open} onEdit={vi.fn()} onAvatarDigests={digests} />);
  let chart = screen.getByRole("group", { name: "地点包含图" });
  expect(within(chart).queryByRole("button", { name: /角色甲/ })).toBeNull();
  fireEvent.click(within(chart).getByRole("button", { name: "校园，进入地点" }));
  chart = screen.getByRole("group", { name: "地点包含图" });
  expect(within(chart).queryByRole("button", { name: /角色甲/ })).toBeNull();
  fireEvent.click(within(chart).getByRole("button", { name: "教室，进入地点" }));
  chart = screen.getByRole("group", { name: "地点包含图" });
  expect(within(chart).getByRole("button", { name: "角色甲，当前位置：教室，查看资料" })).toBeTruthy();
  expect(within(chart).queryByRole("button", { name: /角色乙|角色丙/ })).toBeNull();
  expect(digests).toHaveBeenLastCalledWith("avatar-0");
  fireEvent.click(within(chart).getByRole("button", { name: /角色甲/ }));
  expect(open).toHaveBeenCalledWith("root-0");
});
test("place breadcrumbs return to a parent and hidden branches stay marked", () => {
  render(<ContactPlaces {...placesFixture()} onSelect={vi.fn()} onEdit={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("跳转地点"), { target: { value: "secret" } });
  expect(screen.getByText(/当前处于隐藏分支/)).toBeTruthy();
  expect(screen.getByRole("group", { name: "地点包含图" }).querySelector(".diagram-enclosure.is-hidden")).toBeTruthy();
  fireEvent.click(within(screen.getByRole("navigation", { name: "地点路径" })).getByRole("button", { name: "校园" }));
  expect(screen.getByLabelText("跳转地点")).toHaveProperty("value", "campus");
  fireEvent.click(screen.getByRole("button", { name: "世界总览" }));
  expect(screen.getByLabelText("跳转地点")).toHaveProperty("value", "");
});
test("missing positions stay unknown and do not become zero-occupancy claims", () => {
  render(<ContactPlaces {...placesFixture()} directory={null} onSelect={vi.fn()} onEdit={vi.fn()} />);
  expect(screen.getByText(/世界地点.*位置尚未读取/)).toBeTruthy();
  expect(screen.queryAllByText("0 人")).toHaveLength(0);
  fireEvent.change(screen.getByLabelText("跳转地点"), { target: { value: "room" } });
  expect(screen.queryByRole("button", { name: /角色甲.*当前位置/ })).toBeNull();
});
test("current occupants are deduplicated and counted in their ancestor locations", () => {
  const props = placesFixture();
  props.directory.items.push({ ...props.directory.items[0] });
  const placed = placedCharacters(props.locations, props.directory, props.social);
  expect(placed).toHaveLength(2);
  const counts = occupancyCounts(props.locations, props.directory, props.social);
  expect(counts.get("room")).toBe(1); expect(counts.get("campus")).toBe(1); expect(counts.get("home")).toBe(1);
});
test("removing a focused place safely returns the diagram to world scope", () => {
  const props = placesFixture();
  const rendered = render(<ContactPlaces {...props} onSelect={vi.fn()} onEdit={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("跳转地点"), { target: { value: "room" } });
  rendered.rerender(<ContactPlaces {...props} locations={props.locations.filter(place => place.location_id !== "room")} onSelect={vi.fn()} onEdit={vi.fn()} />);
  expect(screen.getByLabelText("跳转地点")).toHaveProperty("value", "");
});
test("a dense place directory is paged before layout and remains within its enclosure", () => {
  const props = placesFixture(); props.locations = Array.from({ length: 35 }, (_, i) => place("p" + i, "地点" + i));
  render(<ContactPlaces {...props} onSelect={vi.fn()} onEdit={vi.fn()} />);
  expect(within(screen.getByRole("group", { name: "地点包含图" })).getAllByRole("button")).toHaveLength(DIAGRAM_PAGE);
  const nodes = packBubbles(props.locations.slice(0, DIAGRAM_PAGE).map(place => ({ id: place.location_id, name: place.name, kind: "place" as const })));
  for (const node of nodes) expect(Math.hypot(node.x - 300, node.y - 300) + node.r).toBeLessThanOrEqual(294.001);
});
test("radial layout is deterministic, bounded and has room between touch targets", () => {
  const ids = Array.from({ length: 13 }, (_, i) => "r" + i), positions = radialPositions(ids, "r0");
  expect(positions).toEqual(radialPositions(ids, "r0"));
  const values = [...positions.values()];
  for (let i = 0; i < values.length; i++) for (let j = i + 1; j < values.length; j++) {
    expect(Math.hypot(values[i].x - values[j].x, values[i].y - values[j].y)).toBeGreaterThan(96);
  }
});
test("canvas zoom buttons clamp the scale and reset the viewport", () => {
  render(<DiagramCanvas label="测试图">{() => null}</DiagramCanvas>);
  for (let i = 0; i < 12; i++) fireEvent.click(screen.getByRole("button", { name: "放大测试图" }));
  expect(screen.getByLabelText("缩放比例").textContent).toBe("400%");
  expect(screen.getByRole("button", { name: "放大测试图" })).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByRole("button", { name: "复位视图" }));
  expect(screen.getByRole("group", { name: "测试图" }).getAttribute("viewBox")).toBe("0 0 600 600");
  expect(zoomView({ x: 0, y: 0, size: 600 }, .01).size).toBe(600);
});
test("pointer drag pans without accidentally selecting a person", () => {
  const selected = vi.fn();
  render(<DiagramCanvas label="测试图">{canActivate => <g role="button" aria-label="图节点" onClick={() => { if (canActivate()) selected(); }}><circle cx="300" cy="300" r="40" /></g>}</DiagramCanvas>);
  const chart = screen.getByRole("group", { name: "测试图" });
  vi.spyOn(chart, "getBoundingClientRect").mockReturnValue({ x: 0, y: 0, left: 0, top: 0, width: 600, height: 600, bottom: 600, right: 600, toJSON: () => ({}) });
  fireEvent.pointerDown(chart, { pointerId: 1, button: 0, clientX: 100, clientY: 100 });
  fireEvent.pointerMove(chart, { pointerId: 1, button: 0, clientX: 125, clientY: 130 });
  fireEvent.pointerUp(chart, { pointerId: 1, button: 0, clientX: 125, clientY: 130 });
  expect(chart.getAttribute("viewBox")).toBe("-25 -30 600 600");
  fireEvent.click(screen.getByRole("button", { name: "图节点" }));
  expect(selected).not.toHaveBeenCalled();
  fireEvent.pointerDown(chart, { pointerId: 2, button: 0, clientX: 100, clientY: 100 });
  fireEvent.pointerUp(chart, { pointerId: 2, button: 0, clientX: 100, clientY: 100 });
  fireEvent.click(screen.getByRole("button", { name: "图节点" }));
  expect(selected).toHaveBeenCalledTimes(1);
});
test("two-pointer pinch zooms and continues smoothly when one finger leaves", () => {
  render(<DiagramCanvas label="测试图">{() => null}</DiagramCanvas>);
  const chart = screen.getByRole("group", { name: "测试图" });
  vi.spyOn(chart, "getBoundingClientRect").mockReturnValue({ x: 0, y: 0, left: 0, top: 0, width: 600, height: 600, bottom: 600, right: 600, toJSON: () => ({}) });
  fireEvent.pointerDown(chart, { pointerId: 1, button: 0, clientX: 100, clientY: 100 });
  fireEvent.pointerDown(chart, { pointerId: 2, button: 0, clientX: 200, clientY: 100 });
  fireEvent.pointerMove(chart, { pointerId: 2, button: 0, clientX: 300, clientY: 100 });
  expect(chart.getAttribute("viewBox")).toBe("50 50 300 300");
  fireEvent.pointerUp(chart, { pointerId: 1, button: 0, clientX: 100, clientY: 100 });
  fireEvent.pointerMove(chart, { pointerId: 2, button: 0, clientX: 320, clientY: 100 });
  expect(chart.getAttribute("viewBox")).toBe("40 50 300 300");
});


test("atlas pinch keeps its anchor and continues panning after one finger leaves without selecting", () => {
  const choose = vi.fn();
  render(<ContactRelations social={socialFixture()} selected="root-0" onChoose={choose} onProfile={vi.fn()} />);
  const chart = screen.getByRole("img", { name: "阵营环形人物关系图" });
  vi.spyOn(chart, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 600, height: 600, x: 0, y: 0,
    right: 600, bottom: 600, toJSON: () => ({}) });
  fireEvent.pointerDown(chart, { pointerId: 1, button: 0, clientX: 100, clientY: 100 });
  fireEvent.pointerDown(chart, { pointerId: 2, button: 0, clientX: 200, clientY: 100 });
  fireEvent.pointerMove(chart, { pointerId: 2, button: 0, clientX: 300, clientY: 100 });
  expect(lastAtlas()[3].size).toBe(500);
  expect(lastAtlas()[3].x).toBeCloseTo(250 / 3);
  fireEvent.pointerUp(chart, { pointerId: 1, button: 0, clientX: 100, clientY: 100 });
  const before = lastAtlas()[3].x;
  fireEvent.pointerMove(chart, { pointerId: 2, button: 0, clientX: 330, clientY: 100 });
  expect(lastAtlas()[3].size).toBe(500); expect(lastAtlas()[3].x).toBeCloseTo(before - 25);
  fireEvent.pointerUp(chart, { pointerId: 2, button: 0, clientX: 330, clientY: 100 });
  expect(choose).not.toHaveBeenCalled();
});


test("high-DPI raster dimensions stay independent of canvas intrinsic size", () => {
  vi.stubGlobal("devicePixelRatio", 2);
  const callbacks: Array<() => void> = [], observed: Element[] = [];
  class Observer {
    constructor(callback: ResizeObserverCallback) { callbacks.push(() => callback([], this as unknown as ResizeObserver)); }
    observe(element: Element) { observed.push(element); }
    disconnect() {}
    unobserve() {}
  }
  vi.stubGlobal("ResizeObserver", Observer);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const width = this instanceof HTMLCanvasElement ? this.width : 320;
    return { x: 0, y: 0, left: 0, top: 0, width, height: width, right: width, bottom: width, toJSON: () => ({}) };
  });
  render(<RelationHarness />);
  const chart = screen.getByRole("img", { name: "阵营环形人物关系图" }) as HTMLCanvasElement;
  for (let i = 0; i < 5; i++) act(() => callbacks.forEach(callback => callback()));
  expect(observed.every(element => element.classList.contains("atlas-surface"))).toBe(true);
  expect(chart.width).toBe(640); expect(chart.height).toBe(640);
  expect(chart.style.position).toBe("absolute");
  expect((chart.parentElement as HTMLElement).style.aspectRatio).toBe("1 / 1");
});
test("unavailable drawing keeps readable real people and offers manual retry", () => {
  vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(null);
  const profile = vi.fn(), digests = vi.fn();
  render(<ContactRelations social={socialFixture()} selected={null} onChoose={vi.fn()} onProfile={profile} onAvatarDigests={digests} />);
  expect(screen.getByRole("alert").textContent).toContain("relation_graph_context_unavailable");
  expect(screen.getByRole("button", { name: "列表" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "查看角色甲资料" }));
  expect(profile).toHaveBeenCalledWith("root-0");
  expect(screen.getByRole("button", { name: "重新绘图" })).toBeTruthy();
  expect(digests).toHaveBeenLastCalledWith("");
});
test("a drawing exception becomes a scoped list fallback", () => {
  paints.mockImplementationOnce(() => { throw new DOMException("synthetic", "IndexSizeError"); });
  render(<RelationHarness />);
  expect(screen.getByRole("alert").textContent).toContain("relation_graph_draw_failed");
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
});

test("a stale native close event cannot dismiss an already reopened pair sheet", () => {
  render(<RelationHarness />); focusPerson("角色甲"); tapPerson("root-1");
  const dialog = screen.getByRole("dialog", { name: "角色甲与角色乙" });
  expect((dialog as HTMLDialogElement).open).toBe(true);
  fireEvent(dialog, new Event("close"));
  expect(screen.getByRole("dialog", { name: "角色甲与角色乙" })).toBe(dialog);
  fireEvent.click(within(dialog).getByRole("button", { name: "关闭两人详情" }));
  expect(screen.queryByRole("dialog")).toBeNull();
});
