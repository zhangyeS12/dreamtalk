import { afterEach, beforeAll, afterAll, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { ArchiveRing, ringIndex, ringSlots, coastFrame } from "./ArchiveRing";
const NativePointerEvent = window.PointerEvent;
beforeAll(() => {
  Object.defineProperty(window, "PointerEvent", { configurable: true, value: class extends MouseEvent {
    pointerId: number; isPrimary: boolean;
    constructor(name: string, init: PointerEventInit) { super(name, init); this.pointerId = init.pointerId ?? 1; this.isPrimary = init.isPrimary ?? true; }
  } });
});
afterAll(() => Object.defineProperty(window, "PointerEvent", { configurable: true, value: NativePointerEvent }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const items = Array.from({ length: 9 }, (_, index) => ({ id: "synthetic:" + index, name: "合成" + index }));
function ring(label: string, open = vi.fn()) {
  return <ArchiveRing label={label} kind="cards" items={items} onOpen={open} renderItem={item => <span>{item.name}</span>}/>;
}
test("negative and long drags wrap without increasing the rendered collection", () => {
  expect(ringIndex(-1, 9)).toBe(8); expect(ringIndex(90001, 9)).toBe(1);
  expect(ringSlots(-99999.6, 9).every(slot => slot.index >= 0 && slot.index < 9)).toBe(true);
  expect(ringSlots(100000, 1000000)).toHaveLength(5); expect(ringSlots(2, 0)).toEqual([]);
});
test("arrows and keyboard move only their own half and wrap across the end", () => {
  render(<>{ring("上半")}{ring("下半")}</>);
  const upper = screen.getByRole("group", { name: "上半" }), lower = screen.getByRole("group", { name: "下半" });
  fireEvent.click(screen.getByRole("button", { name: "上半上一项" }));
  expect(within(upper).getByRole("button", { name: "合成8" })).toBeTruthy();
  expect(within(lower).getByRole("button", { name: "合成0" })).toBeTruthy();
  fireEvent.keyDown(lower, { key: "ArrowRight" });
  expect(within(lower).getByRole("button", { name: "合成1" })).toBeTruthy();
  expect(within(upper).getByRole("button", { name: "合成8" })).toBeTruthy();
});
test("dragging from a card moves the ring and never opens that card on release", () => {
  const open = vi.fn(); render(ring("卡库", open));
  const group = screen.getByRole("group"), card = within(group).getByRole("button", { name: "合成0" });
  group.setPointerCapture = vi.fn();
  fireEvent.pointerDown(card, { pointerId: 7, clientX: 220, clientY: 50, button: 0, isPrimary: true });
  fireEvent.pointerMove(group, { pointerId: 7, clientX: 75, clientY: 52, isPrimary: true });
  fireEvent.pointerUp(group, { pointerId: 7 });
  fireEvent.click(card, { detail: 1 });
  expect(open).not.toHaveBeenCalled();
  expect(group.querySelectorAll(".mobile-archive-item")).toHaveLength(5);
});
test("cancelled drag restores the starting selection; a tap still opens the real id", () => {
  const open = vi.fn(); render(ring("卡库", open));
  const group = screen.getByRole("group"); group.setPointerCapture = vi.fn();
  fireEvent.pointerDown(group, { pointerId: 2, clientX: 200, clientY: 50, isPrimary: true });
  fireEvent.pointerMove(group, { pointerId: 2, clientX: 30, clientY: 51, isPrimary: true });
  fireEvent.pointerCancel(group, { pointerId: 2 });
  expect(within(group).getByRole("button", { name: "合成0" })).toBeTruthy();
  const card = within(group).getByRole("button", { name: "合成0" });
  fireEvent.pointerDown(card, { pointerId: 3, clientX: 100, clientY: 50, isPrimary: true });
  fireEvent.pointerUp(card, { pointerId: 3 }); fireEvent.click(card);
  expect(open).toHaveBeenCalledWith(items[0],expect.objectContaining({width:expect.any(Number),height:expect.any(Number)}));
});
test("a one-card collection stays cyclic, and deletion safely selects a remaining card", () => {
  const open = vi.fn(); const view = render(<ArchiveRing label="卡库" kind="cards" items={items.slice(0, 1)} renderItem={item => item.name} onOpen={open}/>);
  fireEvent.click(screen.getByRole("button", { name: "卡库上一项" }));
  expect(within(screen.getByRole("group")).getByRole("button", { name: "合成0" })).toBeTruthy();
  view.rerender(<ArchiveRing label="卡库" kind="cards" items={items.slice(1, 3)} renderItem={item => item.name} onOpen={open}/>);
  expect(within(screen.getByRole("group")).getByRole("button", { name: "合成1" })).toBeTruthy();
});

test("touch capture starts on the surface and child capture loss cannot terminate a drag", () => {
  const open=vi.fn();render(ring("卡库",open));
  const group=screen.getByRole("group"),card=within(group).getByRole("button",{name:"合成0"});
  group.setPointerCapture=vi.fn();
  fireEvent.pointerDown(card,{pointerId:42,clientX:240,clientY:80,isPrimary:true,button:0});
  expect(group.setPointerCapture).toHaveBeenCalledWith(42);
  fireEvent.pointerMove(group,{pointerId:42,clientX:210,clientY:80});
  const first=Number(group.dataset.position);
  fireEvent(card,new PointerEvent("lostpointercapture",{bubbles:true,pointerId:42}));
  fireEvent.pointerMove(group,{pointerId:42,clientX:100,clientY:80});
  expect(Number(group.dataset.position)).toBeGreaterThan(first);
  expect(group.dataset.motion).toBe("drag");
  fireEvent.pointerUp(group,{pointerId:42});
  fireEvent.click(card,{detail:1});expect(open).not.toHaveBeenCalled();
});
test("the drag follows pixels before release instead of jumping one item", () => {
  render(ring("卡库"));const group=screen.getByRole("group");
  group.setPointerCapture=vi.fn();
  fireEvent.pointerDown(group,{pointerId:9,clientX:200,clientY:80,isPrimary:true});
  fireEvent.pointerMove(group,{pointerId:9,clientX:173,clientY:80});
  const position=Number(group.dataset.position);
  expect(position).toBeGreaterThan(0);expect(position).toBeLessThan(1);
  expect(position).not.toBe(Math.round(position));
  fireEvent.pointerCancel(group,{pointerId:9});
  expect(Number(group.dataset.position)).toBe(0);
});
test("losing the surface capture cancels safely while loss from another pointer is ignored", () => {
  render(ring("卡库"));const group=screen.getByRole("group");group.setPointerCapture=vi.fn();
  fireEvent.pointerDown(group,{pointerId:9,clientX:200,clientY:80,isPrimary:true});
  fireEvent.pointerMove(group,{pointerId:9,clientX:70,clientY:80});
  fireEvent(group,new PointerEvent("lostpointercapture",{bubbles:true,pointerId:8}));
  expect(group.dataset.motion).toBe("drag");
  fireEvent(group,new PointerEvent("lostpointercapture",{bubbles:true,pointerId:9}));
  expect(Number(group.dataset.position)).toBe(0);expect(group.dataset.motion).toBe("idle");
});
test("the Windows decay keeps motion in the release direction and reduces speed", () => {
  const next=coastFrame(2,.01,16.67);
  expect(next.position).toBeGreaterThan(2);expect(next.velocity).toBeLessThan(.01);
  const reverse=coastFrame(2,-.01,16.67);
  expect(reverse.position).toBeLessThan(2);expect(reverse.velocity).toBeGreaterThan(-.01);
  expect(coastFrame(2,.01,500)).toEqual(coastFrame(2,.01,32));
});
test("books recycle enough neighbors to fill the shelf without mounting a whole collection", () => {
  render(<ArchiveRing label="书架" kind="books" items={Array.from({length:1000},(_,i)=>({id:String(i),name:String(i)}))} renderItem={item=>item.name} onOpen={vi.fn()}/>);
  const count=screen.getByRole("group").querySelectorAll(".mobile-archive-item").length;
  expect(count).toBeGreaterThan(5);expect(count).toBeLessThanOrEqual(25);
});
