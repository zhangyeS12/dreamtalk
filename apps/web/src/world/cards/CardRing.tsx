import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { CoreClient, CardDesign, LibraryCardItem } from "@dreamtalk/api-client";
import { useWindowStill } from "../useWindowStill";
import { CardFaces, useCardImages } from "./CardFaces";
import { clamp, defaultDesign, restPose } from "./cardDesign";
import { RemovalEffect } from "./RemovalEffect";
import styles from "./Cards.module.css";

export type Carry = { card: LibraryCardItem; x: number; y: number };
export function CardRing({ client, cards, active, selected, onSelect, onCreate, onCarry, onDrop, onCancel, locked, faceRequest, removingId, onRemovalComplete }: {
  client: CoreClient; cards: LibraryCardItem[]; active: boolean; selected: string | null; locked: boolean;
  onSelect: (id: string | null) => void; onCreate: () => void;
  onCarry: (carry: Carry) => void; onDrop: (carry: Carry) => void; onCancel: () => void;
  faceRequest?: { side: "front" | "back"; nonce: number };
  removingId?: string; onRemovalComplete?: () => void;
}) {
  const slots = useMemo(() => [...cards.map(card => ({ id: card.card_id, card })), ...Array.from({ length: Math.max(2, 8 - cards.length) }, (_, i) => ({ id: `blank:${i}`, card: null }))], [cards]);
  const stage = useRef<HTMLDivElement>(null), offset = useRef(0), rotation = useRef({ yaw: 0, pitch: 0 });
  const drag = useRef<{ pointer: number; x: number; y: number; offset: number; yaw: number; pitch: number; card: LibraryCardItem | null; moved: boolean; carry: Carry | null } | null>(null);
  const suppress = useRef(false), frame = useRef(0), draw = useRef(() => {});
  const still = useWindowStill();
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const settings = useRef({ active, selected, still, reduced }); settings.current = { active, selected, still, reduced };
  useEffect(() => { const media = window.matchMedia("(prefers-reduced-motion: reduce)"), change = () => setReduced(media.matches); media.addEventListener("change", change); return () => media.removeEventListener("change", change); }, []);
  const wake = useCallback(() => {
    if (frame.current) return;
    const tick = () => {
      frame.current = 0; draw.current();
      const p = settings.current;
      if (p.active && !p.selected && !p.still && !p.reduced && !drag.current?.carry) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  }, []);
  useLayoutEffect(() => { rotation.current = { yaw: 0, pitch: 0 }; }, [selected]);
  useLayoutEffect(() => {
    draw.current = () => {
      const root = stage.current; if (!root) return;
      const cardWidth = parseFloat(getComputedStyle(root).getPropertyValue("--card-w")) || 410;
      const step = cardWidth + (window.innerWidth < 680 ? 40 : 75), total = slots.length * step;
      const chosen = slots.findIndex(item => item.id === selected);
      const lap = chosen < 0 ? 0 : Math.round((offset.current - chosen * step) / total);
      const time = performance.now() / 1900;
      for (const node of root.querySelectorAll<HTMLElement>("[data-card-slot]")) {
        const index = Number(node.dataset.cardSlot), copy = Number(node.dataset.lap), slot = slots[index];
        const dx = index * step + copy * total - offset.current;
        const picked = Boolean(selected) && index === chosen && copy === lap;
        const rest = restPose(slot.id), pose = picked ? rotation.current : rest;
        const float = !selected && !still && !reduced ? Math.sin(time + rest.phase) * 7 : 0;
        const x = picked ? 0 : dx, y = picked ? -14 : rest.y + float, z = picked ? 100 : -dx * dx / 3000 - (selected ? 100 : 0);
        const roll = picked ? 0 : rest.roll, yaw = picked ? pose.yaw : clamp(-dx * .018 + rest.yaw, -45, 45), pitch = pose.pitch;
        node.style.transform = `translate3d(${x}px,${y}px,${z}px) rotateZ(${roll}deg) rotateX(${pitch}deg) rotateY(${yaw}deg)`;
        node.style.opacity = selected ? picked ? "1" : ".12" : Math.abs(dx) > root.clientWidth / 2 + 330 ? "0" : String(clamp(1 - Math.abs(dx) / (root.clientWidth * 1.3), .28, 1));
        node.style.zIndex = picked ? "20" : String(Math.max(1, 10 - Math.floor(Math.abs(dx) / step)));
        node.style.pointerEvents = selected && !picked || Math.abs(dx) > root.clientWidth / 2 + 330 ? "none" : "auto";
        node.dataset.selected = String(picked);
        const front = Math.cos(yaw * Math.PI / 180) * Math.cos(pitch * Math.PI / 180) >= 0;
        for (const face of node.querySelectorAll<HTMLElement>("[data-face]")) face.hidden = (face.dataset.face === "front") !== front;
      }
    };
    draw.current(); wake();
  }, [selected, slots, still, reduced, wake]);
  useEffect(() => { wake(); return () => { cancelAnimationFrame(frame.current); frame.current = 0; }; }, [wake, active, selected, still, reduced]);
  useEffect(() => { if (faceRequest && settings.current.selected) { rotation.current = { yaw: faceRequest.side === "front" ? 0 : 180, pitch: 0 }; draw.current(); } }, [faceRequest]);
  useEffect(() => { const observer = new ResizeObserver(() => { draw.current(); wake(); }); if (stage.current) observer.observe(stage.current); return () => observer.disconnect(); }, [wake]);
  const cancel = useCallback(() => {
    const current = drag.current; drag.current = null;
    if (current && stage.current?.hasPointerCapture(current.pointer)) stage.current.releasePointerCapture(current.pointer);
    if (current?.carry) onCancel();
    if (current?.moved) suppress.current = true;
    wake();
  }, [onCancel, wake]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (document.querySelector("dialog[open]") || (event.target instanceof Element && event.target.matches("input,select,textarea"))) return;
      if (event.key === "Escape") { if (drag.current) { event.preventDefault(); cancel(); } else if (active && selected && !locked) onSelect(null); }
      else if (active && !locked && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
        event.preventDefault(); const direction = event.key === "ArrowLeft" ? -1 : 1;
        if (selected) rotation.current.yaw += direction * 15;
        else if (stage.current) { const step = (parseFloat(getComputedStyle(stage.current).getPropertyValue("--card-w")) || 410) + (window.innerWidth < 680 ? 40 : 75), total = slots.length * step; offset.current = ((offset.current + direction * step) % total + total) % total; }
        draw.current();
      }
    };
    const release = () => { if (!drag.current) window.setTimeout(() => { suppress.current = false; }, 0); };
    window.addEventListener("keydown", escape); window.addEventListener("pointerup", release, true); window.addEventListener("blur", cancel);
    return () => { window.removeEventListener("keydown", escape); window.removeEventListener("pointerup", release, true); window.removeEventListener("blur", cancel); };
  }, [active, selected, locked, onSelect, cancel, slots.length]);
  const down = (event: ReactPointerEvent) => {
    if (locked || !active || event.button !== 0 || drag.current) return;
    suppress.current = false;
    const id = (event.target as Element).closest<HTMLElement>("[data-card-id]")?.dataset.cardId;
    drag.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, offset: offset.current, ...rotation.current, card: cards.find(item => item.card_id === id) ?? null, moved: false, carry: null };
  };
  const move = (event: ReactPointerEvent) => {
    const current = drag.current; if (!current || current.pointer !== event.pointerId) return;
    const dx = event.clientX - current.x, dy = event.clientY - current.y;
    if (!current.moved && Math.hypot(dx, dy) < 6) return;
    current.moved = true; suppress.current = true;
    if (!stage.current?.hasPointerCapture(event.pointerId)) stage.current?.setPointerCapture(event.pointerId);
    if (selected) { rotation.current = { yaw: current.yaw + dx * .65, pitch: clamp(current.pitch - dy * .4, -65, 65) }; draw.current(); }
    else if (current.card) { current.carry = { card: current.card, x: event.clientX, y: event.clientY }; onCarry(current.carry); }
    else { offset.current = current.offset - dx; const width = parseFloat(getComputedStyle(stage.current!).getPropertyValue("--card-w")) || 410; const total = slots.length * (width + (stage.current!.clientWidth < 680 ? 40 : 75)); offset.current = ((offset.current % total) + total) % total; draw.current(); }
  };
  const up = (event: ReactPointerEvent) => {
    const current = drag.current; if (!current || current.pointer !== event.pointerId) return;
    drag.current = null;
    if (stage.current?.hasPointerCapture(event.pointerId)) stage.current.releasePointerCapture(event.pointerId);
    if (current.carry) onDrop({ ...current.carry, x: event.clientX, y: event.clientY });
    window.setTimeout(() => { suppress.current = false; }, 0); wake();
  };
  const scroll = (direction: number) => { const root = stage.current; if (!root || selected || locked) return; const step = (parseFloat(getComputedStyle(root).getPropertyValue("--card-w")) || 410) + (root.clientWidth < 680 ? 40 : 75); offset.current = ((offset.current + direction * step) % (slots.length * step) + slots.length * step) % (slots.length * step); draw.current(); };
  return <div className={styles.ringWrap}>
    <div ref={stage} className={styles.ring} data-expanded={Boolean(selected)} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={cancel} onClick={event => { if (event.target === stage.current && selected && !locked && !suppress.current) onSelect(null); }}
      onWheel={event => { if (!selected && !locked) { offset.current += event.deltaX || event.deltaY; const root = stage.current!; const total = slots.length * ((parseFloat(getComputedStyle(root).getPropertyValue("--card-w")) || 410) + (root.clientWidth < 680 ? 40 : 75)); offset.current = (offset.current % total + total) % total; draw.current(); } }}>
      {[-1, 0, 1].flatMap(lap => slots.map((slot, index) => <button key={`${lap}:${slot.id}`} className={styles.card} data-card-slot={index} data-card-id={slot.card?.card_id} data-lap={lap}
        aria-label={slot.card ? `查看角色卡：${slot.card.name}` : "空白角色卡"} aria-hidden={lap !== 0 || undefined} tabIndex={lap === 0 && (!selected || slot.id === selected) ? 0 : -1}
        onFocus={event => { if (!selected && event.currentTarget.matches(":focus-visible")) { const root = stage.current!; offset.current = index * ((parseFloat(getComputedStyle(root).getPropertyValue("--card-w")) || 410) + (root.clientWidth < 680 ? 40 : 75)); draw.current(); } }}
        onClick={event => { if (suppress.current && event.detail > 0 || locked) return; if (slot.card) onSelect(slot.id === selected ? null : slot.id); else onCreate(); }}>
        {slot.card ? <RenderedCard client={client} card={slot.card} /> : <span className={styles.blankCard}><b>＋</b><span>从一张空白卡开始</span><small>新建 / 导入角色</small></span>}
      </button>))}
    </div>
    {!selected && <><button className={`${styles.arrow} ${styles.prev}`} aria-label="上一张角色卡" disabled={locked} onClick={() => scroll(-1)}>‹</button><button className={`${styles.arrow} ${styles.next}`} aria-label="下一张角色卡" disabled={locked} onClick={() => scroll(1)}>›</button></>}
    {removingId && onRemovalComplete && <RemovalEffect kind="particles" root={stage} selector={`[data-card-id="${removingId}"][data-selected="true"]`} onComplete={onRemovalComplete} />}
  </div>;
}
function RenderedCard({ client, card }: { client: CoreClient; card: LibraryCardItem }) {
  const design: CardDesign = useMemo(() => defaultDesign(card), [card]);
  const images = useCardImages(client, card.card_id, design);
  return <CardFaces design={design} images={images} />;
}
export function CardGhost({ client, carry }: { client: CoreClient; carry: Carry }) {
  return <div className={styles.ghost} style={{ left: carry.x - 120, top: carry.y - 75 }} aria-hidden="true"><RenderedCard client={client} card={carry.card} /></div>;
}
