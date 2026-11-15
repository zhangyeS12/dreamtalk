import { useEffect, useId, useMemo, useRef, useState, type PointerEvent } from "react";
import type { Connection } from "./diagramLayout";
import { atlasGroupView, atlasHit, atlasNodes, clampAtlasView, homeAtlasView, visibleAtlasNodes, zoomAtlas,
  type AtlasLayout, type AtlasView, type AtlasNode } from "./atlasLayout";
import { paintAtlas } from "./atlasPaint";

type Gesture = { view: AtlasView; x: number; y: number; span: number };
export function RelationshipAtlas({ layout, connections, center, pair, urls, onSelect, onAvatarDigests, onFailure }: {
  layout: AtlasLayout; connections: Connection[]; center: string | null; pair: string | null;
  urls: Record<string, string>; onSelect: (id: string) => void; onAvatarDigests: (digests: string) => void; onFailure: (reason: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null), surface = useRef<HTMLDivElement>(null), help = useId();
  const [view, setView] = useState(homeAtlasView), [width, setWidth] = useState(480);
  const [notice, setNotice] = useState(""), [keyboard, setKeyboard] = useState<string | null>(null), [imagesRevision, setImagesRevision] = useState(0);
  const viewRef = useRef(view), pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<Gesture | null>(null), moved = useRef(false);
  const images = useRef(new Map<string, { url: string; image: HTMLImageElement }>()), mounted = useRef(false);
  const nodes = useMemo(() => atlasNodes(layout, center), [layout, center]);
  const visible = useMemo(() => visibleAtlasNodes(nodes, view), [nodes, view]);
  const digests = [...new Set(visible.filter(node => node.r * width / view.size >= 5.5 || node.id === center || node.id === pair)
    .flatMap(node => node.person.avatar_digest ? [node.person.avatar_digest] : []))].sort().join(",");
  useEffect(() => {
    const timer = window.setTimeout(() => onAvatarDigests(digests), 140);
    return () => window.clearTimeout(timer);
  }, [digests, onAvatarDigests]);
  useEffect(() => {
    mounted.current = true;
    const cache = images.current;
    return () => { mounted.current = false; for (const entry of cache.values()) { entry.image.onload = null; entry.image.src = ""; } cache.clear(); };
  }, []);
  useEffect(() => {
    const wanted = new Set(digests ? digests.split(",") : []);
    for (const [digest, entry] of images.current) if (!wanted.has(digest) || urls[digest] !== entry.url) {
      entry.image.onload = null; entry.image.src = ""; images.current.delete(digest);
    }
    for (const digest of wanted) if (urls[digest] && !images.current.has(digest)) {
      const image = new Image(), entry = { url: urls[digest], image };
      image.decoding = "async";
      image.onload = () => { if (mounted.current && images.current.get(digest) === entry) setImagesRevision(value => value + 1); };
      images.current.set(digest, entry); image.src = entry.url;
    }
  }, [digests, urls]);
  useEffect(() => {
    const element = surface.current; if (!element) return;
    // Measure the host, never the Canvas bitmap whose intrinsic size we change.
    const measure = () => { const value = element.getBoundingClientRect().width; if (Number.isFinite(value) && value > 0) setWidth(Math.min(720, value)); };
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    observer?.observe(element); window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  useEffect(() => {
    const element = canvas.current; if (!element) return;
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    const pixels = Math.round(width * ratio);
    if (element.width !== pixels || element.height !== pixels) { element.width = pixels; element.height = pixels; }
    try {
      const ctx = element.getContext("2d");
      if (!ctx) { onFailure("relation_graph_context_unavailable"); return; }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const portraits = new Map([...images.current].filter(([, entry]) => entry.image.complete && entry.image.naturalWidth > 0)
        .map(([id, entry]) => [id, entry.image]));
      paintAtlas(ctx, layout, connections, view, width, center, pair ?? keyboard, portraits);
    } catch {
      onFailure("relation_graph_draw_failed");
    }
  }, [layout, connections, view, width, center, pair, keyboard, urls, imagesRevision, onFailure]);
  function apply(next: AtlasView) { viewRef.current = clampAtlasView(next); setView(viewRef.current); }
  function rebase() {
    const values = [...pointers.current.values()];
    if (!values.length) { gesture.current = null; return; }
    const x = values.length < 2 ? values[0].x : (values[0].x + values[1].x) / 2;
    const y = values.length < 2 ? values[0].y : (values[0].y + values[1].y) / 2;
    const span = values.length < 2 ? 0 : Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y);
    gesture.current = { x, y, span, view: viewRef.current };
  }
  function down(event: PointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0 || pointers.current.size >= 2) return;
    if (!pointers.current.size) moved.current = false;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size > 1) moved.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId); rebase();
  }
  function move(event: PointerEvent<HTMLCanvasElement>) {
    if (!pointers.current.has(event.pointerId) || !gesture.current) return;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const values = [...pointers.current.values()], start = gesture.current;
    const x = values.length < 2 ? values[0].x : (values[0].x + values[1].x) / 2;
    const y = values.length < 2 ? values[0].y : (values[0].y + values[1].y) / 2;
    if (Math.hypot(x - start.x, y - start.y) > 5) moved.current = true;
    if (!moved.current) return;
    const box = event.currentTarget.getBoundingClientRect(); if (!box.width) return;
    const span = values.length < 2 ? 0 : Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y);
    const size = clampAtlasView({ ...start.view, size: start.view.size / (span && start.span ? span / start.span : 1) }).size;
    apply({ size, x: start.view.x + (start.x - box.left) / box.width * start.view.size - (x - box.left) / box.width * size,
      y: start.view.y + (start.y - box.top) / box.width * start.view.size - (y - box.top) / box.width * size });
  }
  function activate(node: AtlasNode, pixelWidth: number) {
    if (node.id !== center && node.r * 2 * pixelWidth / viewRef.current.size < 27 && viewRef.current.size > 1000 / 6 + 1) {
      const group = atlasGroupView(layout, node.group);
      const size = Math.min(viewRef.current.size / 1.8, node.r * 2 * pixelWidth / 36);
      apply(group.size < viewRef.current.size * .8 ? group : clampAtlasView({ size, x: node.x - size / 2, y: node.y - size / 2 }));
      setNotice((layout.groups.find(group => group.id === node.group)?.name ?? "这一组") + "区域已放大，再点头像选择人物。");
    } else { setKeyboard(null); onSelect(node.id); }
  }
  function up(event: PointerEvent<HTMLCanvasElement>) {
    const tracked = pointers.current.has(event.pointerId);
    pointers.current.delete(event.pointerId);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    const cancelled = event.type === "pointercancel";
    if (cancelled) moved.current = true;
    if (tracked && !pointers.current.size && !moved.current && !cancelled) {
      const box = event.currentTarget.getBoundingClientRect();
      if (box.width) {
        const node = atlasHit(nodes, viewRef.current, event.clientX - box.left, event.clientY - box.top, box.width);
        if (node) { event.currentTarget.focus({ preventScroll: true }); activate(node, box.width); }
      }
    }
    rebase();
  }
  useEffect(() => {
    const element = canvas.current;
    const wheel = (event: WheelEvent) => {
      if (!event.ctrlKey || !element) return;
      event.preventDefault();
      const box = element.getBoundingClientRect(); if (!box.width) return;
      const next = zoomAtlas(viewRef.current, event.deltaY < 0 ? 1.15 : 1 / 1.15,
        { x: (event.clientX - box.left) / box.width, y: (event.clientY - box.top) / box.width });
      viewRef.current = next; setView(next);
    };
    element?.addEventListener("wheel", wheel, { passive: false });
    return () => element?.removeEventListener("wheel", wheel);
  }, []);
  return <div className="relation-atlas">
    <div ref={surface} className="atlas-surface" style={{ position: "relative", width: "100%", aspectRatio: "1", overflow: "hidden" }}>
      <canvas ref={canvas} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} role="img" aria-label="阵营环形人物关系图" aria-describedby={help} tabIndex={0}
        data-zoom={Math.round(1000 / view.size * 100)}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
        onLostPointerCapture={event => { if (pointers.current.has(event.pointerId)) { pointers.current.delete(event.pointerId); moved.current = true; rebase(); } }}
        onKeyDown={event => {
          if ((event.key === "ArrowRight" || event.key === "ArrowLeft") && nodes.length) {
            event.preventDefault(); const index = nodes.findIndex(node => node.id === keyboard);
            const next = nodes[(index + (event.key === "ArrowRight" ? 1 : -1) + nodes.length) % nodes.length];
            setKeyboard(next.id); setNotice(next.person.name + "，按 Enter 选择。");
          } else if ((event.key === "Enter" || event.key === " ") && nodes.length) {
            event.preventDefault(); onSelect(keyboard ?? nodes[0].id);
          }
        }} />
      {!center && layout.nodes.length > 1 && <div className="atlas-center-note" aria-hidden="true"><span>人物关系</span><strong>{layout.nodes.length}</strong><small>位角色</small></div>}
      <span className="atlas-corner-label" aria-hidden="true">相识 · 阵营 · 联系</span>
    </div>
    <div className="diagram-controls atlas-controls" role="group" aria-label="环形关系图操作">
      <button aria-label="放大环形关系图" disabled={view.size <= 1000 / 6 + .01} onClick={() => apply(zoomAtlas(viewRef.current, 1.4))}>＋</button>
      <output aria-label="关系图缩放比例">{Math.round(1000 / view.size * 100)}%</output>
      <button aria-label="缩小环形关系图" disabled={view.size >= 1000} onClick={() => apply(zoomAtlas(viewRef.current, 1 / 1.4))}>－</button>
      <button onClick={() => { apply(homeAtlasView()); setNotice(""); }}>复位视图</button>
    </div>
    <div className="atlas-groups" aria-label="放大阵营分区">{layout.groups.map(group => <button key={group.id}
      style={{ borderLeftColor: group.color }} onClick={() => { apply(atlasGroupView(layout, group.id)); setNotice(group.name + "分区已放大。"); }}>
      <span>{group.name}</span><small>{group.count}</small></button>)}</div>
    <p id={help} className="diagram-help">{center ? "再选另一位角色查看两人资料。" : "点头像聚焦人物；头像较小时先放大分区。"}拖动平移，双指缩放；键盘左右选择、Enter 确认。</p>
    <p className="atlas-announcement" role="status" aria-live="polite">{notice}</p>
  </div>;
}
