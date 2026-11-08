import { useId, useLayoutEffect, useRef, type RefObject } from "react";
import { createPortal } from "react-dom";
import styles from "./Removal.module.css";

const columns = 24, rows = 15;
const noise = (seed: number) => { const value = Math.sin(seed * 127.1 + 311.7) * 43758.5453; return value - Math.floor(value); };
const cells = Array.from({ length: columns * rows }, (_, index) => ({ x: index % columns / columns, y: Math.floor(index / columns) / rows, birth: (.12 + (index % columns) / columns * .44 + noise(index) * .19) * 1200 }));

/** Native SVG masks preserve the actual DIY faces; one bounded Canvas draws the debris. */
export function RemovalEffect({ kind, root, selector, onComplete }: {
  kind: "burn" | "particles"; root: RefObject<HTMLElement | null>; selector: string; onComplete: () => void;
}) {
  const id = useId().replace(/:/g, ""), canvas = useRef<HTMLCanvasElement>(null), mask = useRef<SVGMaskElement>(null);
  const completion = useRef(onComplete); useLayoutEffect(() => { completion.current = onComplete; });
  useLayoutEffect(() => {
    const target = root.current?.querySelector<HTMLElement>(selector), node = canvas.current;
    let frame = 0, finished = false;
    const surfaces = target ? [...target.querySelectorAll<HTMLElement>("[data-face], [data-removal-surface]")] : [];
    const saved = surfaces.map(surface => ({ surface, mask: surface.style.maskImage, filter: surface.style.filter }));
    const oldOpacity = target?.style.opacity ?? "", oldTransition = target?.style.transition ?? "";
    const clean = () => { cancelAnimationFrame(frame); for (const item of saved) { item.surface.style.maskImage = item.mask; item.surface.style.filter = item.filter; } if (target) { delete target.dataset.removing; target.style.opacity = oldOpacity; target.style.transition = oldTransition; } };
    const finish = () => { if (finished) return; finished = true; clean(); completion.current(); };
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const reduced = media.matches || !CSS.supports("mask-image", `url("#${id}")`);
    const duration = reduced ? 140 : 1400;
    const fallback = window.setTimeout(finish, duration + 120);
    const hidden = () => { if (document.hidden) finish(); };
    const resize = () => finish();
    document.addEventListener("visibilitychange", hidden); window.addEventListener("resize", resize); media.addEventListener("change", resize);
    if (target) target.dataset.removing = kind;
    let context: CanvasRenderingContext2D | null = null;
    if (!reduced && node) { try { context = node.getContext("2d"); } catch { /* A static fade still completes the confirmed deletion. */ } }
    if (!target || !node || !context || reduced) {
      if (target) { target.style.transition = `opacity ${duration}ms ease-out`; target.style.opacity = "0"; }
    } else {
      const rect = target.getBoundingClientRect(), pad = 90, width = rect.width, height = rect.height;
      const ratio = Math.min(devicePixelRatio || 1, 2);
      node.width = Math.ceil((width + pad * 2) * ratio); node.height = Math.ceil((height + pad * 2) * ratio);
      Object.assign(node.style, { left: `${rect.left - pad}px`, top: `${rect.top - pad}px`, width: `${width + pad * 2}px`, height: `${height + pad * 2}px` });
      context.scale(ratio, ratio); context.translate(pad, pad);
      for (const { surface } of saved) surface.style.maskImage = `url("#${id}")`;
      const tiles = [...(mask.current?.querySelectorAll("rect") ?? [])], edge = mask.current?.querySelector("path");
      const ctx = context, start = performance.now();
      const debris = Array.from({ length: kind === "burn" ? 150 : cells.length * 2 }, (_, i) => {
        const cell = cells[Math.floor(i / 2) % cells.length], seed = noise(i + 8);
        return { x: kind === "burn" ? seed : cell.x + noise(i + 10) / columns, y: kind === "burn" ? noise(i + 12) : cell.y + noise(i + 17) / rows, birth: kind === "burn" ? noise(i + 11) * 850 : cell.birth, vx: (noise(i + 14) - .3) * 125, vy: -35 - noise(i + 15) * 130, life: 300 + noise(i + 16) * 300, size: .7 + noise(i + 20) * 2.5, color: kind === "burn" ? `hsl(${20 + seed * 33} 100% ${55 + seed * 30}%)` : ["#f0cb85", "#c3dcff", "#fbf3df", "#829cbe"][i % 4] };
      });
      const draw = (now: number) => {
        if (finished) return;
        const elapsed = now - start, progress = Math.min(1, elapsed / 960);
        ctx.clearRect(-pad, -pad, width + pad * 2, height + pad * 2);
        if (kind === "particles") tiles.forEach((tile, index) => tile.setAttribute("opacity", String(Math.max(0, 1 - (elapsed - cells[index].birth) / 75))));
        else {
          const boundary = (x: number) => Math.max(0, Math.min(1, 1.07 - progress * 1.15 + Math.sin(x * 42 + progress * 7) * .026 + Math.sin(x * 91 - progress * 12) * .012));
          const points = Array.from({ length: 49 }, (_, i) => ({ x: i / 48, y: boundary(i / 48) }));
          edge?.setAttribute("d", `M0 0H1V${points[48].y} ${points.slice().reverse().map(p => `L${p.x} ${p.y}`).join(" ")}Z`);
          for (const { surface } of saved) surface.style.filter = `saturate(${1 - progress * .8}) brightness(${1 - progress * .65})`;
          if (progress > .04 && progress < .99) {
            ctx.save(); ctx.globalCompositeOperation = "lighter";
            ctx.shadowColor = "#ff6a15"; ctx.shadowBlur = 17; ctx.lineWidth = 3;
            ctx.beginPath(); points.forEach((p, i) => { if (i) ctx.lineTo(p.x * width, p.y * height); else ctx.moveTo(0, p.y * height); }); ctx.strokeStyle = "#ffd58a"; ctx.stroke();
            for (let i = 0; i < 26; i++) {
              const x = (i + .5) / 26, y = boundary(x) * height, flame = 12 + noise(i) * 22 + Math.sin(elapsed / 48 + i) * 8;
              const gradient = ctx.createLinearGradient(0, y, 0, y - flame); gradient.addColorStop(0, "#ffd37bcf"); gradient.addColorStop(.35, "#ff6c2499"); gradient.addColorStop(1, "#ff3a0000"); ctx.fillStyle = gradient;
              ctx.beginPath(); ctx.moveTo(x * width - 8, y + 3); ctx.quadraticCurveTo(x * width - 10, y - flame * .4, x * width + Math.sin(i + elapsed / 72) * 8, y - flame); ctx.quadraticCurveTo(x * width + 10, y - flame * .4, x * width + 8, y + 3); ctx.fill();
            }
            ctx.restore();
          }
        }
        for (const particle of debris) {
          const age = elapsed - particle.birth; if (age < 0 || age > particle.life) continue;
          const life = age / particle.life, seconds = age / 1000;
          const y = kind === "burn" ? (1.04 - particle.birth / 960 * 1.15) * height : particle.y * height;
          ctx.globalAlpha = (1 - life) * Math.min(1, age / 40); ctx.fillStyle = particle.color;
          ctx.fillRect(particle.x * width + particle.vx * seconds + Math.sin(life * 5 + particle.x * 10) * life * 18, y + particle.vy * seconds, particle.size * (1 - life * .55), particle.size * (1 - life * .55));
        }
        ctx.globalAlpha = 1;
        if (elapsed >= duration) finish(); else frame = requestAnimationFrame(draw);
      };
      frame = requestAnimationFrame(draw);
    }
    return () => { finished = true; clearTimeout(fallback); clean(); document.removeEventListener("visibilitychange", hidden); window.removeEventListener("resize", resize); media.removeEventListener("change", resize); };
  }, [id, kind, root, selector]);
  return createPortal(<div className={styles.effect} data-removal-effect={kind} aria-hidden="true"><svg width="0" height="0"><defs><mask ref={mask} id={id} maskUnits="objectBoundingBox" maskContentUnits="objectBoundingBox" style={{ maskType: "alpha" }}>{kind === "burn" ? <path d="M0 0H1V1H0Z" fill="white" /> : cells.map((cell, i) => <rect key={i} x={cell.x} y={cell.y} width={1 / columns + .001} height={1 / rows + .001} fill="white" />)}</mask></defs></svg><canvas ref={canvas} /></div>, document.body);
}
