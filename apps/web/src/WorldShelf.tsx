import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { WorldSettings } from "@dreamtalk/api-client";

const SLOT = 68;
const BLANK_BOOKS = 8;
const EASE = "cubic-bezier(.22,1,.36,1)";
const REST = "translate3d(0px,0px,0px) rotateY(-90deg) rotateX(0deg) rotateZ(0deg)";
type Book = { key: string; name: string; number: string; worldId?: string; blankIndex?: number };

export function WorldShelf({ worlds, selectedKey, initialWorldId, disabled, loading, onSelect, onCreate, onClose, onSettled }: {
  worlds: WorldSettings[]; selectedKey: string | null; initialWorldId: string | null;
  disabled: boolean; loading: boolean; onSelect: (id: string) => void; onCreate: (index: number) => void;
  onClose: () => void; onSettled: (key: string | null) => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const volumes = useRef(new Map<string, HTMLSpanElement>());
  const poses = useRef(new Map<string, { target: string; animation?: Animation }>());
  const previousSelection = useRef<string | null>(null);
  const previousGeometry = useRef({ width: 0, scrollLeft: 0 });
  const selectionRef = useRef(selectedKey);
  selectionRef.current = selectedKey;
  const settledCallback = useRef(onSettled);
  settledCallback.current = onSettled;
  const epoch = useRef(0);
  const fallback = useRef<number | undefined>(undefined);
  const restoredPosition = useRef(false);
  const [geometry, setGeometry] = useState({ width: 0, scrollLeft: 0 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const books = useMemo<Book[]>(() => [
    ...worlds.map((world, index) => ({ key: `world:${world.world_id}`, name: world.name,
      number: String(index + 1).padStart(2, "0"), worldId: world.world_id })),
    ...Array.from({ length: BLANK_BOOKS }, (_, index) => ({ key: `blank:${index}`, name: "未命名世界", number: "＋", blankIndex: index })),
  ], [worlds]);
  const sceneWidth = Math.max(geometry.width, books.length * SLOT + 176);
  const rowStart = (sceneWidth - books.length * SLOT) / 2;
  const measure = () => {
    const element = viewport.current;
    if (element) setGeometry(current => current.width === element.clientWidth && current.scrollLeft === element.scrollLeft
      ? current : { width: element.clientWidth, scrollLeft: element.scrollLeft });
  };
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      setGeometry(current => current.width === element.clientWidth && current.scrollLeft === element.scrollLeft
        ? current : { width: element.clientWidth, scrollLeft: element.scrollLeft });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (restoredPosition.current || loading || !geometry.width) return;
    restoredPosition.current = true;
    const index = books.findIndex(book => book.worldId === initialWorldId);
    if (index >= 0) viewport.current?.scrollTo({ left: rowStart + index * SLOT + SLOT / 2 - geometry.width / 2, behavior: "instant" });
  }, [books, geometry.width, initialWorldId, loading, rowStart]);
  useLayoutEffect(() => {
    if (!geometry.width) return;
    const oldSelection = previousSelection.current;
    const selectionChanged = oldSelection !== selectedKey;
    const geometryChanged = previousGeometry.current.width !== geometry.width || previousGeometry.current.scrollLeft !== geometry.scrollLeft;
    const immediate = reduced || document.hidden || (geometryChanged && !selectionChanged);
    if (selectionChanged || geometryChanged || reduced) {
      epoch.current += 1;
      window.clearTimeout(fallback.current);
    }
    const currentEpoch = epoch.current;
    const finish = () => {
      if (epoch.current !== currentEpoch || selectionRef.current !== selectedKey) return;
      window.clearTimeout(fallback.current);
      settledCallback.current(selectedKey);
    };
    for (const [key, pose] of poses.current) {
      if (!volumes.current.has(key)) { pose.animation?.cancel(); poses.current.delete(key); }
    }
    const stageFraction = Number.parseFloat(getComputedStyle(viewport.current!).getPropertyValue("--selection-position")) || .34;
    books.forEach((book, index) => {
      const node = volumes.current.get(book.key);
      if (!node) return;
      const chosen = book.key === selectedKey;
      const shift = geometry.scrollLeft + geometry.width * stageFraction - (rowStart + index * SLOT + SLOT / 2);
      node.parentElement?.style.setProperty("--display-shift", `${shift}px`);
      const target = chosen ? `translate3d(${shift}px,-14px,210px) rotateY(-24deg) rotateX(7deg) rotateZ(-5deg)`
        : hovered === book.key ? "translate3d(0px,-2px,44px) rotateY(-86deg) rotateX(0deg) rotateZ(0deg)" : REST;
      const previous = poses.current.get(book.key);
      if (previous?.target === target && !immediate) return;
      const from = getComputedStyle(node).transform;
      previous?.animation?.cancel();
      node.style.transform = target;
      if (immediate || (!previous && !chosen) || typeof node.animate !== "function") { poses.current.set(book.key, { target }); return; }
      const extracting = chosen && selectionChanged;
      const returning = book.key === oldSelection && selectionChanged;
      const middle = extracting ? `translate3d(${shift * .55}px,-6px,180px) rotateY(-90deg) rotateX(0deg) rotateZ(0deg)`
        : "translate3d(0px,0px,150px) rotateY(-90deg) rotateX(0deg) rotateZ(0deg)";
      const animation = node.animate(extracting || returning ? [
        { transform: from, offset: 0 }, { transform: middle, offset: extracting ? .38 : .62 }, { transform: target, offset: 1 },
      ] : [{ transform: from }, { transform: target }], {
        duration: extracting ? 480 : returning ? 340 : 180, delay: extracting && oldSelection ? 90 : 0, easing: EASE, fill: "backwards",
      });
      poses.current.set(book.key, { target, animation });
    });
    if (selectionChanged || geometryChanged || reduced) {
      const animation = selectedKey ? poses.current.get(selectedKey)?.animation : undefined;
      if (immediate || !animation || animation.playState === "finished") finish();
      else {
        void animation.finished.then(finish).catch(() => undefined);
        // Hidden tabs can pause animation completion. Content must remain usable.
        fallback.current = window.setTimeout(finish, 750);
      }
    }
    previousSelection.current = selectedKey;
    previousGeometry.current = geometry;
  }, [books, geometry, hovered, reduced, rowStart, selectedKey]);
  useEffect(() => {
    const running = poses.current;
    return () => { epoch.current += 1; window.clearTimeout(fallback.current); running.forEach(pose => pose.animation?.cancel()); };
  }, []);
  const scroll = (direction: number) => viewport.current?.scrollBy({ left: direction * (viewport.current.clientWidth * .65), behavior: reduced ? "instant" : "smooth" });
  const navigate = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && selectedKey) { event.preventDefault(); event.stopPropagation(); onClose(); return; }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || !(event.target instanceof HTMLButtonElement) || disabled) return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button[data-book-key]:not(:disabled)")];
    const index = buttons.indexOf(event.target);
    if (index < 0) return;
    event.preventDefault();
    buttons[event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === "ArrowRight" ? 1 : -1)))]?.focus();
  };
  return <section className={`archive-shelf-section ${selectedKey ? "has-selection" : ""}`} aria-label="世界书架">
    <div className="archive-shelf-heading"><span>{loading ? "正在读取世界档案…" : `${worlds.length} 个世界档案`}</span>
      <div className="archive-scroll-actions"><button type="button" disabled={disabled} aria-label="向左浏览书架" onClick={() => scroll(-1)}>←</button><button type="button" disabled={disabled} aria-label="向右浏览书架" onClick={() => scroll(1)}>→</button></div>
    </div>
    <div className="shelf-viewport" ref={viewport} onScroll={measure} onKeyDown={navigate}>
      <div className="shelf-scene" style={{ width: sceneWidth, perspectiveOrigin: `${geometry.scrollLeft + geometry.width / 2}px 42%` }}>
        <div className="shelf-backboard" aria-hidden="true" onClick={onClose} /><div className="shelf-top" aria-hidden="true" onClick={onClose} />
        <div className="shelf-floor" aria-hidden="true" onClick={onClose} /><div className="shelf-edge" aria-hidden="true" onClick={onClose} />
        {books.map((book, index) => <button type="button" data-book-key={book.key} key={book.key}
          className={`archive-book ${book.blankIndex !== undefined ? "blank-book" : ""} ${selectedKey === book.key ? "is-selected" : ""}`}
          style={{ left: rowStart + index * SLOT }}
          disabled={disabled || loading} aria-pressed={selectedKey === book.key} aria-controls="archive-preview"
          aria-label={book.worldId ? `预览世界：${book.name}` : `创建或导入一个新世界，空白书 ${book.blankIndex! + 1}`}
          onPointerEnter={event => { if (event.pointerType === "mouse") setHovered(book.key); }} onPointerLeave={() => setHovered(current => current === book.key ? null : current)}
          onFocus={event => { if (event.currentTarget.matches(":focus-visible")) setHovered(book.key); }} onBlur={() => setHovered(current => current === book.key ? null : current)}
          onClick={() => book.worldId ? onSelect(book.worldId) : onCreate(book.blankIndex!)}>
          <span className="book-shadow" aria-hidden="true" />
          <span className="book-volume" ref={node => { if (node) volumes.current.set(book.key, node); else volumes.current.delete(book.key); }} aria-hidden="true">
            <span className="book-front book-face"><small>dreamtalk</small><strong>{book.worldId ? book.name : "下一个世界"}</strong><span>{book.worldId ? "世界档案" : "创建 · 导入"}</span><i>{book.number}</i></span>
            <span className="book-back book-face"><small>dreamtalk</small><span>{book.worldId ? book.name : "等待一段新的故事"}</span></span>
            <span className="book-spine book-face"><small>{book.number}</small><strong>{book.name}</strong><span>dreamtalk</span></span>
            <span className="book-pages book-face" /><span className="book-top book-face" /><span className="book-bottom book-face" />
          </span>
        </button>)}
      </div>
    </div>
    <p className="archive-shelf-hint">悬停轻抽，点击展开。空白书可创建或导入世界；再次点击所选书或按 Esc 归位。</p>
  </section>;
}
