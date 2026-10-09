import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import useEmblaCarousel, { type UseEmblaCarouselType } from "embla-carousel-react";
import type { WorldSettings } from "@dreamtalk/api-client";
import { BookFaces, type BookAppearance } from "./BookFaces";

const SLOT = 84;
const MIN_BOOKS = 12;
export const worldShelfBlankCount = (worldCount: number) => Math.max(1, MIN_BOOKS - worldCount);
const EASE = "cubic-bezier(.22,1,.36,1)";
const REST = "translate3d(0px,0px,0px) rotateY(90deg) rotateX(0deg) rotateZ(0deg)";
type Book = { key: string; name: string; number: string; worldId?: string; blankIndex?: number };
type Carousel = NonNullable<UseEmblaCarouselType[1]>;
type Geometry = { width: number; positions: number[] };

export function WorldShelf({ worlds, appearances, selectedKey, initialWorldId, disabled, loading, onSelect, onCreate, onClose, onSettled, vacatedIndex }: {
  worlds: WorldSettings[]; appearances: Record<string, BookAppearance>; selectedKey: string | null; initialWorldId: string | null;
  disabled: boolean; loading: boolean; onSelect: (id: string) => void; onCreate: (index: number) => void;
  onClose: () => void; onSettled: (key: string | null) => void;
  vacatedIndex?: number | null;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const volumes = useRef(new Map<string, HTMLSpanElement>());
  const poses = useRef(new Map<string, { target: string; left: number; animation?: Animation }>());
  const origin = useRef<{ key: string; left: number; lap: number } | null>(null);
  const pendingOrigin = useRef<{ key: string; left: number; lap: number; from?: string } | null>(null);
  const previousSelection = useRef<string | null>(null);
  const previousWidth = useRef(0);
  const selectionRef = useRef(selectedKey);
  selectionRef.current = selectedKey;
  const settledCallback = useRef(onSettled);
  settledCallback.current = onSettled;
  const canDrag = useRef(false);
  canDrag.current = !disabled && !loading;
  const epoch = useRef(0);
  const fallback = useRef<number | undefined>(undefined);
  const restoredPosition = useRef(false);
  const [geometry, setGeometry] = useState<Geometry>({ width: 0, positions: [] });
  const [hovered, setHovered] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const previousReduced = useRef(reduced);
  const options = useMemo(() => ({ loop: true, dragFree: true, dragThreshold: 8,
    container: ".shelf-motion-track", slides: ".shelf-motion-slot", watchFocus: false,
    watchDrag: () => canDrag.current }), []);
  const [emblaRef, carousel] = useEmblaCarousel(options);
  const attach = useCallback((node: HTMLDivElement | null) => { viewport.current = node; emblaRef(node); }, [emblaRef]);
  const books = useMemo<Book[]>(() => {
    const result: Book[] = [
    ...worlds.map((world, index) => ({ key: `world:${world.world_id}`, name: world.name,
      number: String(index + 1).padStart(2, "0"), worldId: world.world_id })),
    ...Array.from({ length: worldShelfBlankCount(worlds.length) }, (_, index) =>
      ({ key: `blank:${index}`, name: "未命名世界", number: "＋", blankIndex: index })),
    ];
    if (vacatedIndex !== null && vacatedIndex !== undefined) {
      const index = result.findIndex(item => item.blankIndex === 0);
      const [blank] = result.splice(index, 1);
      result.splice(Math.min(vacatedIndex, result.length), 0, blank);
    }
    return result;
  }, [worlds, vacatedIndex]);
  // Repeated presentation laps keep Embla looping even on a window wider than one lap.
  // They never create worlds or duplicate keyboard/accessibility entries.
  const laps = Math.max(2, Math.ceil((geometry.width + SLOT * 2) / (books.length * SLOT)) + 1);
  const copies = useMemo(() => Array.from({ length: laps * books.length }, (_, index) =>
    ({ book: books[index % books.length], index, key: `${Math.floor(index / books.length)}:${books[index % books.length].key}` })), [books, laps]);
  const stageFraction = viewport.current ? Number.parseFloat(getComputedStyle(viewport.current).getPropertyValue("--selection-position")) || .34 : .34;
  const stage = geometry.width * stageFraction;
  const selectedOrigin = origin.current?.key === selectedKey ? origin.current
    : pendingOrigin.current?.key === selectedKey ? pendingOrigin.current : null;
  const representatives = books.map((book, bookIndex) => {
    let copy = bookIndex;
    let left = geometry.positions[copy] ?? copy * SLOT;
    for (let lap = 1; lap < laps; lap += 1) {
      const candidate = bookIndex + lap * books.length;
      const position = geometry.positions[candidate] ?? candidate * SLOT;
      if (Math.abs(position + SLOT / 2 - stage) < Math.abs(left + SLOT / 2 - stage)) { copy = candidate; left = position; }
    }
    const chosen = book.key === selectedKey && selectedOrigin !== null;
    return { book, copy: chosen ? bookIndex + Math.min(selectedOrigin!.lap, laps - 1) * books.length : copy,
      left: chosen ? selectedOrigin!.left : left };
  });
  const representativesRef = useRef(representatives);
  representativesRef.current = representatives;
  const measure = useCallback((api: Carousel) => {
    const element = viewport.current;
    if (!element) return;
    const viewportLeft = element.getBoundingClientRect().left;
    // Public slide nodes provide Embla's actual looped positions; no private engine API.
    const positions = api.slideNodes().map(node => node.getBoundingClientRect().left - viewportLeft);
    setGeometry(current => current.width === element.clientWidth && current.positions.length === positions.length &&
      positions.every((left, index) => Math.abs(left - current.positions[index]) < .05)
      ? current : { width: element.clientWidth, positions });
  }, []);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setGeometry(current => current.width === element.clientWidth
      ? current : { ...current, width: element.clientWidth }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!carousel) return;
    const down = () => { setDragging(true); setHovered(null); };
    const up = () => setDragging(false);
    carousel.on("scroll", measure).on("reInit", measure).on("settle", measure).on("pointerDown", down).on("pointerUp", up);
    measure(carousel);
    return () => { carousel.off("scroll", measure).off("reInit", measure).off("settle", measure).off("pointerDown", down).off("pointerUp", up); };
  }, [carousel, measure]);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!carousel || restoredPosition.current || loading || !geometry.width) return;
    restoredPosition.current = true;
    const index = books.findIndex(book => book.worldId === initialWorldId);
    carousel.scrollTo(index >= 0 ? index : 0, true);
    measure(carousel);
  }, [books, carousel, geometry.width, initialWorldId, loading, measure]);
  useLayoutEffect(() => {
    if (!geometry.width) return;
    const oldSelection = previousSelection.current;
    const selectionChanged = oldSelection !== selectedKey;
    const resized = previousWidth.current !== geometry.width;
    const motionChanged = previousReduced.current !== reduced;
    const openingFrom = pendingOrigin.current?.key === selectedKey ? pendingOrigin.current.from : undefined;
    const immediate = reduced || document.hidden || (resized && !selectionChanged);
    if (selectionChanged || resized || motionChanged) { epoch.current += 1; window.clearTimeout(fallback.current); }
    const currentEpoch = epoch.current;
    const finish = () => {
      if (epoch.current !== currentEpoch || selectionRef.current !== selectedKey) return;
      window.clearTimeout(fallback.current); settledCallback.current(selectedKey);
    };
    for (const [key, pose] of poses.current) {
      if (!volumes.current.has(key)) { pose.animation?.cancel(); poses.current.delete(key); }
    }
    representatives.forEach(({ book, left, copy }) => {
      const node = volumes.current.get(book.key);
      if (!node) return;
      const chosen = book.key === selectedKey;
      if (chosen && origin.current?.key !== book.key) {
        origin.current = { key: book.key, left, lap: Math.floor(copy / books.length) };
        pendingOrigin.current = null;
      }
      const shift = stage - (left + SLOT / 2);
      node.parentElement?.style.setProperty("--display-shift", `${shift}px`);
      const target = chosen ? `translate3d(${shift}px,-14px,210px) rotateY(24deg) rotateX(7deg) rotateZ(-5deg)`
        : !dragging && hovered === book.key ? "translate3d(0px,-2px,44px) rotateY(86deg) rotateX(0deg) rotateZ(0deg)" : REST;
      const previous = poses.current.get(book.key);
      if (previous?.target === target && !resized && !motionChanged) { previous.left = left; return; }
      const fromMatrix = new DOMMatrix(chosen && selectionChanged && openingFrom ? openingFrom : getComputedStyle(node).transform);
      // A returning book may now have a different slot after dragging. Keep its starting pose continuous.
      if (previous && book.key === oldSelection && selectionChanged) fromMatrix.m41 += previous.left - left;
      const from = fromMatrix.toString();
      previous?.animation?.cancel(); node.style.transform = target;
      if (immediate || (!previous && !chosen) || typeof node.animate !== "function") { poses.current.set(book.key, { target, left }); return; }
      const extracting = chosen && selectionChanged;
      const returning = book.key === oldSelection && selectionChanged;
      const middle = extracting ? `translate3d(${shift * .55}px,-6px,180px) rotateY(90deg) rotateX(0deg) rotateZ(0deg)`
        : `translate3d(${returning ? fromMatrix.m41 * .35 : 0}px,0px,150px) rotateY(90deg) rotateX(0deg) rotateZ(0deg)`;
      const animation = node.animate(extracting || returning ? [
        { transform: from, offset: 0 }, { transform: middle, offset: extracting ? .38 : .62 }, { transform: target, offset: 1 },
      ] : [{ transform: from }, { transform: target }], {
        duration: extracting ? 480 : returning ? 340 : 180, delay: extracting && oldSelection ? 90 : 0, easing: EASE, fill: "backwards",
      });
      poses.current.set(book.key, { target, left, animation });
    });
    if (selectionChanged || resized || motionChanged) {
      const animation = selectedKey ? poses.current.get(selectedKey)?.animation : undefined;
      if (immediate || !animation || animation.playState === "finished") finish();
      else { void animation.finished.then(finish).catch(() => undefined); fallback.current = window.setTimeout(finish, 750); }
    }
    previousSelection.current = selectedKey; previousWidth.current = geometry.width; previousReduced.current = reduced;
    if (!selectedKey) origin.current = null;
  });
  useEffect(() => {
    const running = poses.current;
    return () => { epoch.current += 1; window.clearTimeout(fallback.current); running.forEach(pose => pose.animation?.cancel()); };
  }, []);
  const choose = (book: Book, copy: number, left: number, source?: HTMLElement) => {
    if (disabled || loading) return;
    if (selectedKey !== book.key) pendingOrigin.current = { key: book.key, lap: Math.floor(copy / books.length), left,
      from: source?.querySelector(".book-volume") ? getComputedStyle(source.querySelector(".book-volume")!).transform : undefined };
    if (book.worldId) onSelect(book.worldId); else onCreate(book.blankIndex!);
  };
  const reveal = (key: string) => {
    const representative = representativesRef.current.find(item => item.book.key === key);
    if (representative && carousel) { carousel.scrollTo(representative.copy, reduced); measure(carousel); }
  };
  const navigate = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && selectedKey) { event.preventDefault(); event.stopPropagation(); onClose(); return; }
    if ((event.key === "Enter" || event.key === " ") && event.target instanceof HTMLButtonElement && event.target.dataset.bookKey) {
      event.preventDefault();
      const item = representativesRef.current.find(entry => entry.book.key === (event.target as HTMLButtonElement).dataset.bookKey);
      if (item && !event.repeat) choose(item.book, item.copy, item.left);
      return;
    }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || !(event.target instanceof HTMLButtonElement) || disabled || loading) return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button[data-book-key]:not(:disabled)")];
    const index = buttons.indexOf(event.target);
    if (index < 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next]?.focus({ preventScroll: true });
  };
  const primaryCopies = new Set(representatives.map(item => item.copy));
  return <section className={`archive-shelf-section ${selectedKey ? "has-selection" : ""}`} aria-label="世界书架">
    <div className="archive-shelf-heading"><span>{loading ? "正在读取世界档案…" : `${worlds.length} 个世界档案 · ${books.length} 本书`}</span>
      <div className="archive-scroll-actions"><button type="button" disabled={disabled || loading} aria-label="向左循环浏览书架" onClick={() => carousel?.scrollPrev(reduced)}>←</button><button type="button" disabled={disabled || loading} aria-label="向右循环浏览书架" onClick={() => carousel?.scrollNext(reduced)}>→</button></div>
    </div>
    <div className={`shelf-viewport ${dragging ? "is-dragging" : ""}`} ref={attach} onKeyDown={navigate}
      onClick={event => { if (!(event.target as Element).closest(".archive-book")) onClose(); }}>
      <div className="shelf-scene">
        <div className="shelf-backboard" aria-hidden="true" /><div className="shelf-top" aria-hidden="true" />
        <div className="shelf-floor" aria-hidden="true" /><div className="shelf-edge" aria-hidden="true" />
        <div className="shelf-motion-track" aria-hidden="true">{copies.map(copy => <div className="shelf-motion-slot" key={copy.key} />)}</div>
        {copies.filter(copy => !primaryCopies.has(copy.index)).map(({ book, index, key }) => <div key={key} aria-hidden="true"
          className={`archive-book book-repeat ${book.blankIndex !== undefined ? "blank-book" : ""}`}
          style={{ left: geometry.positions[index] ?? index * SLOT }} onClick={event => choose(book, index, geometry.positions[index] ?? index * SLOT, event.currentTarget)}>
          <span className="book-shadow" /><span className="book-volume"><BookFaces name={book.name} number={book.number} blank={!book.worldId} appearance={book.worldId ? appearances[book.worldId] : undefined} /></span>
        </div>)}
        {representatives.map(({ book, copy, left }) => <button type="button" data-book-key={book.key} key={book.key}
          className={`archive-book ${book.blankIndex !== undefined ? "blank-book" : ""} ${selectedKey === book.key ? "is-selected" : ""}`}
          style={{ left }} disabled={disabled || loading} aria-pressed={selectedKey === book.key} aria-controls="archive-preview"
          aria-label={book.worldId ? `预览世界：${book.name}` : `创建或导入一个新世界，空白书 ${book.blankIndex! + 1}`}
          onPointerEnter={event => { if (event.pointerType === "mouse" && !dragging) setHovered(book.key); }} onPointerLeave={() => setHovered(current => current === book.key ? null : current)}
          onFocus={event => { if (event.currentTarget.matches(":focus-visible")) { setHovered(book.key); reveal(book.key); } }} onBlur={() => setHovered(current => current === book.key ? null : current)}
          onClick={event => choose(book, copy, left, event.currentTarget)}>
          <span className="book-shadow" aria-hidden="true" />
          <span className="book-volume" ref={node => { if (node) volumes.current.set(book.key, node); else volumes.current.delete(book.key); }} aria-hidden="true"><BookFaces name={book.name} number={book.number} blank={!book.worldId} appearance={book.worldId ? appearances[book.worldId] : undefined} /></span>
        </button>)}
      </div>
    </div>
    <p className="archive-shelf-hint">按住书本或书架左右拖动，首尾循环。悬停轻抽，点击展开；空白书可创建或导入世界，再次点击所选书或按 Esc 归位。</p>
  </section>;
}
