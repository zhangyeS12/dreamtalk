import { useEffect, useId, useRef, useState, type ReactNode, type PointerEvent } from "react";
import { clampView, DIAGRAM_SIZE, zoomView, type DiagramView, type Point } from "./diagramLayout";

type Gesture = { view: DiagramView; center: Point; span: number };
export function DiagramCanvas({ label, children }: {
  label: string; children: (canActivate: () => boolean) => ReactNode;
}) {
  const id = useId(), svg = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<DiagramView>({ x: 0, y: 0, size: DIAGRAM_SIZE });
  const current = useRef(view), pointers = useRef(new Map<number, Point>());
  const gesture = useRef<Gesture | null>(null), moved = useRef(false);
  const apply = (next: DiagramView) => { current.current = clampView(next); setView(current.current); };
  function rebase() {
    const points = [...pointers.current.values()];
    if (!points.length) { gesture.current = null; return; }
    const center = points.length < 2 ? points[0] : { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 };
    const span = points.length < 2 ? 0 : Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
    gesture.current = { view: current.current, center, span };
  }
  function down(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0 || pointers.current.size >= 2) return;
    if (!pointers.current.size) moved.current = false;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size > 1) moved.current = true;
    rebase();
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    if (!pointers.current.has(event.pointerId) || !gesture.current) return;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const points = [...pointers.current.values()], start = gesture.current;
    const center = points.length < 2 ? points[0] : { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 };
    if (Math.hypot(center.x - start.center.x, center.y - start.center.y) > 5) moved.current = true;
    if (!moved.current) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const box = event.currentTarget.getBoundingClientRect();
    if (!box.width || !box.height) return;
    const span = points.length < 2 ? 0 : Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
    const size = Math.max(150, Math.min(DIAGRAM_SIZE, start.view.size / (span && start.span ? span / start.span : 1)));
    apply({ size,
      x: start.view.x + (start.center.x - box.left) / box.width * start.view.size - (center.x - box.left) / box.width * size,
      y: start.view.y + (start.center.y - box.top) / box.height * start.view.size - (center.y - box.top) / box.height * size,
    });
  }
  function up(event: PointerEvent<SVGSVGElement>) {
    pointers.current.delete(event.pointerId);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (event.type === "pointercancel") moved.current = true;
    rebase();
  }
  useEffect(() => {
    const element = svg.current;
    const wheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault(); const next = zoomView(current.current, event.deltaY < 0 ? 1.15 : 1 / 1.15);
      current.current = next; setView(next);
    };
    element?.addEventListener("wheel", wheel, { passive: false });
    return () => element?.removeEventListener("wheel", wheel);
  }, []);
  return <div className="mobile-diagram">
    <svg ref={svg} className="mobile-diagram-svg" role="group" aria-label={label} aria-describedby={id}
      viewBox={[view.x, view.y, view.size, view.size].join(" ")}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      {children(() => !moved.current)}
    </svg>
    <div className="diagram-controls" role="group" aria-label={label + "操作"}>
      <button type="button" aria-label={"放大" + label} disabled={view.size <= 150} onClick={() => apply(zoomView(current.current, 1.3))}>＋</button>
      <output aria-label="缩放比例">{Math.round(DIAGRAM_SIZE / view.size * 100)}%</output>
      <button type="button" aria-label={"缩小" + label} disabled={view.size >= DIAGRAM_SIZE} onClick={() => apply(zoomView(current.current, 1 / 1.3))}>－</button>
      <button type="button" onClick={() => apply({ x: 0, y: 0, size: DIAGRAM_SIZE })}>复位视图</button>
    </div>
    <p id={id} className="diagram-help">拖动平移 · 双指缩放 · 点选查看；也可用缩放按钮。</p>
  </div>;
}
