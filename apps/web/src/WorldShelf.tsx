import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from "react";
import type { BookDesign, WorldSettings } from "@dreamtalk/api-client";
import { BlankFaces, Book3DFaces, type BookArt } from "./world/archive/Book3D";
import { BLANK_THICKNESS, BOOK_FACE, FACE_LABELS, THICKNESS, designFor } from "./world/archive/bookDesign";
import { skyAt, worldClock } from "./world/sky";
import styles from "./world/archive/Shelf.module.css";

const MIN_BOOKS = 12;
const GAP = 8;
export const worldShelfBlankCount = (worldCount: number) => Math.max(1, MIN_BOOKS - worldCount);
export type ShelfAppearance = { design: BookDesign; art: BookArt; uploads: Record<string, string> };
export type ShelfFace = "front" | "spine" | "back" | "edge";
type Book = { key: string; name: string; world?: WorldSettings; blankIndex?: number };
type Pose = { px: number; py: number; pz: number; yaw: number; pitch: number; tilt: number };
type Node = { el: HTMLElement; book: Book; lap: number; dx: number; hover: number };

const FACE_YAW: Record<ShelfFace, number> = { front: -90, spine: 0, back: 90, edge: 180 };
const ease = (t: number) => 1 - (1 - t) ** 3;
const restPose = (dx: number): Pose => ({ px: dx, py: 0, pz: -(dx * dx) / 2600 - BOOK_FACE / 2, yaw: Math.max(-38, Math.min(38, -dx * 0.02)), pitch: 0, tilt: 0 });
const poseCss = (p: Pose) => `translate3d(${p.px.toFixed(1)}px, ${p.py.toFixed(1)}px, ${p.pz.toFixed(1)}px) rotateZ(${p.tilt.toFixed(2)}deg) rotateX(${p.pitch.toFixed(2)}deg) rotateY(${p.yaw.toFixed(2)}deg)`;
const nightSky = skyAt(0);

/**
 * The world archive as an endless ring of books. Books are positioned every
 * frame from one scroll offset; the chosen book leaves the ring and can be
 * turned all the way round. Worlds and blanks keep the original data order:
 * worlds first, then max(1, 12 - worlds) blanks.
 */
export function WorldShelf({ worlds, appearances, selectedKey, initialWorldId, disabled, loading, onSelect, onCreate, onClose, onSettled, vacatedIndex, designing = false, faceRequest, onFace }: {
  worlds: WorldSettings[]; appearances: Record<string, ShelfAppearance>; selectedKey: string | null; initialWorldId: string | null;
  disabled: boolean; loading: boolean; onSelect: (id: string) => void; onCreate: (index: number) => void;
  onClose: () => void; onSettled: (key: string | null) => void; vacatedIndex?: number | null;
  designing?: boolean; faceRequest?: { face: ShelfFace; nonce: number }; onFace?: (face: ShelfFace) => void;
}) {
  const books = useMemo<Book[]>(() => {
    const result: Book[] = [
      ...worlds.map(world => ({ key: `world:${world.world_id}`, name: world.name, world })),
      ...Array.from({ length: worldShelfBlankCount(worlds.length) }, (_, index) => ({ key: `blank:${index}`, name: "未命名世界", blankIndex: index })),
    ];
    if (vacatedIndex !== null && vacatedIndex !== undefined) {
      const index = result.findIndex(item => item.blankIndex === 0);
      const [blank] = result.splice(index, 1);
      result.splice(Math.min(vacatedIndex, result.length), 0, blank);
    }
    return result;
  }, [worlds, vacatedIndex]);
  const designOf = useCallback((book: Book) => book.world ? appearances[book.world.world_id]?.design ?? designFor(undefined, book.name) : null, [appearances]);
  const widthOf = useCallback((book: Book) => (book.world ? THICKNESS[designOf(book)!.thickness] : BLANK_THICKNESS) + GAP, [designOf]);

  const viewport = useRef<HTMLDivElement>(null);
  const nodes = useRef<Node[]>([]);
  const [width, setWidth] = useState(0);
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [chosenKey, setChosenKey] = useState<string | null>(null);
  const [face, setFace] = useState<ShelfFace>("front");
  const laps = Math.max(2, Math.ceil((width + 600) / Math.max(1, books.reduce((sum, book) => sum + widthOf(book), 0))) + 1);

  // Motion state lives in refs; React renders the books, the frame loop moves them.
  const engine = useRef({
    offset: 0, velocity: 0, dragging: false, awake: false, frame: 0,
    tween: null as null | { from: number; by: number; start: number; ms: number; done?: () => void },
    hovered: null as Node | null, chosen: null as Node | null, pose: null as Pose | null, returning: false,
    spin: { yaw: -68, pitch: 0, vy: 0, vp: 0, dragging: false }, settledKey: null as string | null,
    grow: new Map<string, { from: number; start: number }>(), printing: new Map<string, number>(),
  });
  const props = useRef({ books, widthOf, selectedKey, designing, reduced, onSettled, onFace, laps });
  props.current = { books, widthOf, selectedKey, designing, reduced, onSettled, onFace, laps };
  const slotWidth = useCallback((book: Book, now: number) => {
    const grow = engine.current.grow.get(book.key);
    const k = grow ? Math.min(1, (now - grow.start) / 700) : 1;
    return props.current.widthOf(book) * (grow ? grow.from + (1 - grow.from) * ease(k) : 1);
  }, []);
  const positionOf = useCallback((node: Node, now: number) => {
    const { books: list, laps: count } = props.current;
    let cum = 0, total = 0;
    for (const book of list) { const w = slotWidth(book, now); if (book === node.book) cum = total; total += w; }
    const length = total * count;
    const p = node.lap * total + cum + slotWidth(node.book, now) / 2 - engine.current.offset;
    return ((p % length) + length * 1.5) % length - length / 2;
  }, [slotWidth]);

  const focusTarget = useCallback((): Omit<Pose, "yaw" | "pitch"> => props.current.designing
    ? { px: -(viewport.current?.clientWidth ?? 1200) * 0.29, py: -10, pz: -80, tilt: 0 }
    : { px: 0, py: -12, pz: 120, tilt: -4 }, []);

  const faceFromYaw = (yaw: number): ShelfFace => {
    const a = ((yaw % 360) + 360) % 360;
    return ([["spine", 0], ["back", 90], ["edge", 180], ["front", 270], ["spine", 360]] as Array<[ShelfFace, number]>)
      .reduce((best, item) => Math.abs(a - item[1]) < Math.abs(a - best[1]) ? item : best)[0];
  };

  const step = useCallback(function step(now: number) {
    const state = engine.current, { reduced: still, selectedKey: wanted } = props.current;
    let moving = false;
    if (state.tween) {
      const t = still ? 1 : Math.min(1, (now - state.tween.start) / state.tween.ms);
      state.offset = state.tween.from + state.tween.by * ease(t); moving = true;
      if (t === 1) { const done = state.tween.done; state.tween = null; done?.(); }
    } else if (!state.dragging && !state.chosen && Math.abs(state.velocity) > 0.08 && !still) {
      state.offset += state.velocity; state.velocity *= 0.94; moving = true;
      if (Math.abs(state.velocity) <= 0.08) snap();
    }
    if (state.chosen && !state.spin.dragging && !state.returning && (Math.abs(state.spin.vy) > 0.01 || Math.abs(state.spin.vp) > 0.01)) {
      state.spin.yaw += state.spin.vy; state.spin.pitch = Math.max(-25, Math.min(25, state.spin.pitch + state.spin.vp));
      state.spin.vy *= 0.93; state.spin.vp *= 0.9; moving = true; reportFace();
    }
    for (const [key, start] of state.grow) if (now - start.start < 720) moving = true; else state.grow.delete(key);
    const half = (viewport.current?.clientWidth ?? 1200) / 2;
    for (const node of nodes.current) {
      node.dx = positionOf(node, now);
      if (node === state.chosen) continue;
      const target = node === state.hovered && !state.chosen && !state.dragging ? 1 : 0;
      if (Math.abs(target - node.hover) > 0.01) { node.hover += (target - node.hover) * (still ? 1 : 0.22); moving = true; } else node.hover = target;
      const pose = restPose(node.dx); pose.pz += 46 * node.hover; pose.py -= 14 * node.hover;
      const far = Math.min(1, Math.abs(node.dx) / half);
      let shade = Math.min(0.85, far ** 1.7 * 0.8) * (1 - 0.6 * node.hover), blur = far > 0.82 ? 3.5 : far > 0.62 ? 1.6 : 0;
      if (state.chosen && !state.returning) { shade = Math.min(0.92, shade + (props.current.designing ? 0.7 : 0.5)); blur = Math.max(blur, 2.5); }
      node.el.style.transform = poseCss(pose);
      node.el.style.setProperty("--shade", shade.toFixed(3));
      node.el.style.filter = blur ? `blur(${blur}px)` : "";
      node.el.classList.toggle("is-hover", node.hover > 0.5);
      node.el.style.visibility = Math.abs(node.dx) > half + 260 ? "hidden" : "";
      const printing = state.printing.get(node.book.key);
      node.el.classList.toggle("is-printing", printing !== undefined && now < printing);
      if (printing !== undefined && now >= printing + 100) state.printing.delete(node.book.key); else if (printing !== undefined) moving = true;
    }
    const chosen = state.chosen;
    if (chosen && state.pose) {
      const target: Pose = state.returning ? restPose(chosen.dx) : { ...focusTarget(), yaw: state.spin.yaw, pitch: state.spin.pitch };
      const k = still ? 1 : state.returning ? 0.18 : 0.14;
      let error = 0;
      for (const key of ["px", "py", "pz", "yaw", "pitch", "tilt"] as const) { state.pose[key] += (target[key] - state.pose[key]) * k; error += Math.abs(target[key] - state.pose[key]); }
      chosen.el.style.transform = poseCss(state.pose); chosen.el.style.filter = ""; chosen.el.style.visibility = "";
      chosen.el.style.setProperty("--shade", "0"); chosen.el.style.setProperty("--yaw", state.pose.yaw.toFixed(1));
      if (error > 0.6) moving = true;
      else if (state.returning) { chosen.el.classList.remove("is-chosen"); state.chosen = null; state.pose = null; state.returning = false; }
      else if (state.settledKey !== wanted && wanted === chosen.book.key) { state.settledKey = wanted; props.current.onSettled(wanted); }
    }
    // Exactly one frame chain, even when a render positions books synchronously.
    cancelAnimationFrame(state.frame);
    state.awake = moving;
    state.frame = moving ? requestAnimationFrame(step) : 0;
  }, [focusTarget, positionOf]);
  const wake = useCallback(() => {
    const state = engine.current;
    if (!state.awake) { state.awake = true; state.frame = requestAnimationFrame(step); }
  }, [step]);
  const travel = useCallback((by: number, ms = 520) => new Promise<void>(done => {
    const state = engine.current; state.velocity = 0;
    state.tween = { from: state.offset, by, start: performance.now(), ms: props.current.reduced ? 0 : ms, done }; wake();
  }), [wake]);
  function snap() {
    const state = engine.current; state.velocity = 0;
    const near = nearest(() => true, 0);
    if (near) void travel(near.dx, 360);
  }
  function nearest(filter: (node: Node) => boolean, at: number) {
    return nodes.current.filter(filter).reduce<Node | null>((best, node) => !best || Math.abs(node.dx - at) < Math.abs(best.dx - at) ? node : best, null);
  }
  const lastFace = useRef<ShelfFace>("front");
  function reportFace(force?: ShelfFace) {
    const next = force ?? faceFromYaw(engine.current.spin.yaw);
    if (next === lastFace.current) return;
    lastFace.current = next; setFace(next); props.current.onFace?.(next);
  }
  const turnTo = useCallback((target: ShelfFace) => {
    const spin = engine.current.spin;
    const base = target === "front" && !props.current.designing ? -68 : FACE_YAW[target];
    spin.yaw = base + 360 * Math.round((spin.yaw - base) / 360); spin.pitch = 0; spin.vy = 0; spin.vp = 0;
    reportFace(target); wake();
  }, [wake]);

  // ---------- Sizing, motion preference, first position ----------
  useLayoutEffect(() => {
    const element = viewport.current; if (!element) return;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element); setWidth(element.clientWidth);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const restored = useRef(false);
  useLayoutEffect(() => {
    if (restored.current || loading || !width) return;
    restored.current = true;
    const start = performance.now();
    const index = Math.max(0, books.findIndex(book => book.world?.world_id === initialWorldId));
    let cum = 0; for (let i = 0; i < index; i++) cum += widthOf(books[i]);
    engine.current.offset = cum + widthOf(books[index]) / 2 + (initialWorldId ? 0 : width * 0.18);
    step(start);
  }, [books, initialWorldId, loading, step, width, widthOf]);
  useEffect(() => { wake(); }, [books, laps, appearances, width, designing, wake]);
  useEffect(() => () => cancelAnimationFrame(engine.current.frame), []);

  // ---------- New worlds print into their slot; a new blank slides in ----------
  const known = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (loading) return;
    const keys = new Set(books.map(book => book.key)), state = engine.current, now = performance.now();
    if (known.current) for (const book of books) if (!known.current.has(book.key)) {
      if (book.world) state.printing.set(book.key, now + 1600);
      else state.grow.set(book.key, { from: 0, start: now });
    }
    known.current = keys; wake();
  }, [books, loading, wake]);

  // ---------- Selection: centre, pull out, turn; or put back ----------
  const pendingNode = useRef<Node | null>(null);
  useEffect(() => {
    const state = engine.current;
    let cancelled = false;
    const previous = state.chosen;
    if (previous && previous.book.key !== selectedKey) { state.returning = true; state.settledKey = null; setChosenKey(null); wake(); }
    if (!selectedKey) { state.settledKey = null; return; }
    if (state.chosen?.book.key === selectedKey && !state.returning) return;
    const pick = () => pendingNode.current?.book.key === selectedKey ? pendingNode.current : nearest(node => node.book.key === selectedKey, 0);
    const begin = async () => {
      const node = pick(); if (!node) { onSettled(selectedKey); return; }
      if (previous) await new Promise(resolve => setTimeout(resolve, props.current.reduced ? 0 : 260));
      if (cancelled) return;
      await travel(node.dx, 460);
      if (cancelled || props.current.selectedKey !== selectedKey) return;
      if (state.chosen && state.chosen !== node) { state.chosen.el.classList.remove("is-chosen"); }
      state.chosen = node; state.returning = false; state.pose = restPose(node.dx); state.hovered = null;
      state.spin = { yaw: node.book.world ? -68 : -40, pitch: 0, vy: 0, vp: 0, dragging: false };
      node.el.classList.add("is-chosen"); lastFace.current = "front"; setFace("front"); setChosenKey(selectedKey); wake();
    };
    void begin();
    // Hidden windows get no animation frames: still report the selection.
    const fallback = window.setTimeout(() => { if (!cancelled && state.settledKey !== selectedKey && props.current.selectedKey === selectedKey) { state.settledKey = selectedKey; onSettled(selectedKey); } }, 1400);
    return () => { cancelled = true; window.clearTimeout(fallback); };
  }, [selectedKey]);
  useEffect(() => { if (faceRequest) turnTo(faceRequest.face); }, [faceRequest, turnTo]);
  useEffect(() => { if (engine.current.chosen) { if (designing) turnTo("front"); wake(); } }, [designing, turnTo, wake]);
  // ---------- Pointer: drag the ring, or turn the chosen book ----------
  const down = useRef<null | { x: number; y: number; lx: number; ly: number; moved: boolean; node: Node | null; spin: boolean; id: number }>(null);
  const nodeAt = (target: EventTarget | null) => {
    const element = (target as Element | null)?.closest?.("[data-copy]") as HTMLElement | null;
    return element ? nodes.current.find(node => node.el === element) ?? null : null;
  };
  const choose = (node: Node) => {
    if (disabled || loading) return;
    pendingNode.current = node;
    if (node.book.world) onSelect(node.book.world.world_id); else onCreate(node.book.blankIndex!);
  };
  const pointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || (event.target as Element).closest(`.${styles.controls}`)) return;
    const state = engine.current, node = nodeAt(event.target);
    const onChosen = !!state.chosen && !state.returning && (node === state.chosen || props.current.designing);
    down.current = { x: event.clientX, y: event.clientY, lx: event.clientX, ly: event.clientY, moved: false, node, spin: onChosen, id: event.pointerId };
    state.tween = null; state.velocity = 0;
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const state = engine.current, press = down.current;
    if (!press) {
      if (event.pointerType !== "mouse" || state.chosen) return;
      const node = nodeAt(document.elementFromPoint(event.clientX, event.clientY));
      if (node !== state.hovered) { state.hovered = node; wake(); }
      return;
    }
    const dx = event.clientX - press.lx, dy = event.clientY - press.ly;
    if (!press.moved && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 6) { press.moved = true; state.hovered = null; }
    if (press.moved && press.spin) {
      state.spin.dragging = true; state.spin.yaw += dx * 0.5; state.spin.pitch = Math.max(-25, Math.min(25, state.spin.pitch - dy * 0.3));
      state.spin.vy = dx * 0.5; state.spin.vp = -dy * 0.3; reportFace(); wake();
    } else if (press.moved && !state.chosen && !disabled && !loading) {
      state.dragging = true; state.offset -= dx; state.velocity = -dx; wake();
    }
    press.lx = event.clientX; press.ly = event.clientY;
  };
  const pointerUp = () => {
    const state = engine.current, press = down.current; down.current = null;
    state.spin.dragging = false; const wasDragging = state.dragging; state.dragging = false;
    if (!press) return;
    if (press.moved) { if (wasDragging && Math.abs(state.velocity) < 1) snap(); wake(); return; }
    if (press.spin) return;
    if (!press.node) { if (selectedKey) onClose(); return; }
    if (press.node.book.key === selectedKey) return;
    choose(press.node);
  };
  const wheel = (event: ReactWheelEvent<HTMLElement>) => {
    const state = engine.current;
    if (state.chosen || disabled || loading) return;
    state.tween = null; state.offset += (event.deltaX || event.deltaY) * 0.8; wake();
    window.clearTimeout(wheelEnd.current); wheelEnd.current = window.setTimeout(snap, 140);
  };
  const wheelEnd = useRef<number | undefined>(undefined);

  // ---------- Keyboard: one focusable button per book (the first lap) ----------
  const navigate = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && selectedKey) { event.preventDefault(); event.stopPropagation(); onClose(); return; }
    const target = event.target as HTMLElement;
    if (engine.current.chosen && !engine.current.returning && (event.key === "ArrowLeft" || event.key === "ArrowRight") && !target.dataset.bookKey) {
      event.preventDefault(); engine.current.spin.yaw += event.key === "ArrowRight" ? 90 : -90; reportFace(); wake(); return;
    }
    if (!target.dataset.bookKey) return;
    if ((event.key === "Enter" || event.key === " ") && !event.repeat) {
      event.preventDefault(); const node = nodes.current.find(item => item.el === target); if (node) choose(node); return;
    }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || disabled || loading) return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button[data-book-key]:not(:disabled)")];
    const index = buttons.indexOf(target as HTMLButtonElement); if (index < 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next]?.focus({ preventScroll: true });
  };
  const reveal = (element: HTMLElement) => {
    const node = nodes.current.find(item => item.el === element);
    if (!node || engine.current.chosen) return;
    engine.current.hovered = node;
    const copy = nearest(item => item.book.key === node.book.key, 0);
    if (copy && Math.abs(copy.dx) > (viewport.current?.clientWidth ?? 1200) * 0.3) void travel(copy.dx, 380); else wake();
  };
  const stepWorld = (direction: 1 | -1) => {
    if (disabled || loading) return;
    const list = books.filter(book => book.world);
    const chosen = engine.current.chosen;
    if (chosen?.book.world && list.length) {
      const next = list[(list.indexOf(list.find(book => book.key === chosen.book.key)!) + direction + list.length) % list.length];
      pendingNode.current = nearest(node => node.book.key === next.key, direction * 300);
      onSelect(next.world!.world_id); return;
    }
    void travel(direction * 3 * (BLANK_THICKNESS + GAP), 420);
  };
  // ---------- Render: every lap is drawn; only the first lap is focusable ----------
  // Stable ref callbacks keep each copy's node (and the chosen book) across renders.
  const registry = useRef(new Map<string, Node>());
  const copyInfo = useRef(new Map<string, { book: Book; lap: number }>());
  const refCache = useRef(new Map<string, (element: HTMLElement | null) => void>());
  const register = (key: string, book: Book, lap: number) => {
    copyInfo.current.set(key, { book, lap });
    let callback = refCache.current.get(key);
    if (!callback) {
      callback = (element: HTMLElement | null) => {
        const map = registry.current;
        if (!element) { map.delete(key); return; }
        const info = copyInfo.current.get(key)!, existing = map.get(key);
        if (existing) existing.el = element; else map.set(key, { el: element, book: info.book, lap: info.lap, dx: 0, hover: 0 });
      };
      refCache.current.set(key, callback);
    }
    return callback;
  };
  useLayoutEffect(() => {
    for (const [key, node] of registry.current) { const info = copyInfo.current.get(key); if (info) { node.book = info.book; node.lap = info.lap; } }
    nodes.current = [...registry.current.values()];
    const state = engine.current;
    if (state.chosen && !nodes.current.includes(state.chosen)) {
      // The same copy re-registered (strict-mode ref replay or a lap change): keep the chosen book.
      const was = state.chosen, again = nodes.current.find(node => node.book.key === was.book.key && node.lap === was.lap) ?? null;
      if (again) { again.el.classList.add("is-chosen"); } else { state.pose = null; }
      state.chosen = again;
    }
    if (state.hovered && !nodes.current.includes(state.hovered)) state.hovered = null;
    step(performance.now());
  });
  const looks = (book: Book) => {
    if (!book.world) return null;
    const appearance = appearances[book.world.world_id], clock = worldClock(book.world.world_time);
    return { name: book.name, design: designOf(book)!, art: appearance?.art ?? {}, uploads: appearance?.uploads ?? {},
      sky: clock ? skyAt(clock.minuteOfDay) : nightSky, paused: book.world.clock_state === "paused" };
  };
  const chosenWorld = chosenKey?.startsWith("world:") ?? false;
  const copies: Array<{ book: Book; lap: number; key: string }> = [];
  for (let lap = 0; lap < laps; lap++) for (const book of books) copies.push({ book, lap, key: `${lap}:${book.key}` });

  // Handlers sit on the flat section: inside the ring's 3D context the ring's own plane
  // would otherwise sit in front of the books for hit testing.
  return <section className={styles.shelf} data-designing={designing || undefined} data-chosen={chosenKey ? "" : undefined} aria-label="世界书架"
    onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp}
    onPointerLeave={() => { if (!down.current && engine.current.hovered) { engine.current.hovered = null; wake(); } }} onWheel={wheel}
    onDoubleClick={event => { const node = nodeAt(event.target); if (node && node === engine.current.chosen) turnTo("front"); }}>
    <div className={styles.boardTop} aria-hidden="true" />
    <div ref={viewport} className={styles.ring} onKeyDown={navigate}>
      {copies.map(({ book, lap, key }) => {
        const look = looks(book);
        const thickness = look ? THICKNESS[look.design.thickness] : BLANK_THICKNESS;
        const style = { "--T": `${thickness}px` } as CSSProperties;
        const content = look ? <Book3DFaces look={look} /> : <BlankFaces />;
        return lap === 0
          ? <button type="button" key={key} ref={register(key, book, lap)} data-copy="" data-book-key={book.key} className={styles.book} style={style}
            disabled={disabled || loading} aria-pressed={selectedKey === book.key} aria-controls="archive-preview"
            aria-label={book.world ? `预览世界：${book.name}` : `创建或导入一个新世界，空白书 ${book.blankIndex! + 1}`}
            onFocus={event => { if (event.currentTarget.matches(":focus-visible")) reveal(event.currentTarget); }}>{content}</button>
          : <div key={key} ref={register(key, book, lap)} data-copy="" className={styles.book} style={style} aria-hidden="true">{content}</div>;
      })}
    </div>
    <div className={styles.boardBottom} aria-hidden="true" />
    <div className={styles.controls}>
      <button type="button" className={styles.arrow} data-side="left" disabled={disabled || loading} aria-label={chosenWorld ? "上一本" : "向左循环浏览书架"} onClick={() => stepWorld(-1)}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg></button>
      <button type="button" className={styles.arrow} data-side="right" disabled={disabled || loading} aria-label={chosenWorld ? "下一本" : "向右循环浏览书架"} onClick={() => stepWorld(1)}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg></button>
      {chosenWorld && <div className={styles.faces} role="group" aria-label="查看书的哪一面">
        {(["front", "spine", "back", "edge"] as const).map(item => <button key={item} type="button" aria-pressed={face === item} onClick={() => turnTo(item)}>{FACE_LABELS[item]}</button>)}
      </div>}
    </div>
    <p className={styles.hint}>{chosenKey && !chosenWorld ? "" : chosenWorld ? "按住书本拖动，可以 360 度转着看 · 双击回到正面"
      : loading ? "正在读取世界档案…" : `${worlds.length} 个世界 · ${books.length} 个书位 · 拖动书架，书本首尾相接 · 点击空白书新建世界`}</p>
  </section>;
}
