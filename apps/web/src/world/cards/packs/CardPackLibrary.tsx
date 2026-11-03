import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";
import type { LibraryCardItem } from "@dreamtalk/api-client";
import { ArrowLeft, ChevronLeft, ChevronRight, Palette, Plus, RotateCcw, Scissors, X } from "lucide-react";
import { PackBody } from "./PackBody";
import { PackEditor } from "./PackEditor";
import { PackSpill } from "./PackSpill";
import { defaultPack, type CharacterPack, type PackImages } from "./packDesign";
import { useWindowStill } from "../../useWindowStill";
import { useDesktopUpdateBlock } from "../../../DesktopUpdates";
import styles from "./Packs.module.css";

type Phase = "browse" | "selected" | "opening" | "spilling" | "cards";
export function CardPackLibrary({ packs, cards, images, active, onSave, onDiscard, onEditingChange, renderCards }: {
  packs: CharacterPack[]; cards: LibraryCardItem[]; images: PackImages; active: boolean;
  onSave: (pack: CharacterPack) => Promise<void>; onEditingChange: (editing: boolean) => void;
  onDiscard?: (pack: CharacterPack) => void;
  renderCards: (pack: CharacterPack | null) => ReactNode;
}) {
  const [phase, setPhase] = useState<Phase>("browse"), [selected, setSelected] = useState<string | null>(null), [focus, setFocus] = useState(0);
  const [settled, setSettled] = useState(false);
  const [pose, setPose] = useState({ yaw: -14, pitch: -3 }), [rotating, setRotating] = useState(false);
  const turn = useRef<{ id: number; x: number; y: number; yaw: number; pitch: number } | null>(null);
  const backFacing = Math.cos(pose.yaw * Math.PI / 180) < 0;
  const canCut = settled && !rotating && Math.abs(Math.cos(pose.yaw * Math.PI / 180)) > .4 && Math.abs(pose.pitch) < 55;
  const [progress, setProgress] = useState(0), [direction, setDirection] = useState<"left" | "right">("left"), [editing, setEditing] = useState<CharacterPack | null>(null);
  const [origin, setOrigin] = useState({ x: 0, y: 0 }), [notice, setNotice] = useState("");
  const cut = useRef<{ id: number; start: number; side: "left" | "right"; rect: DOMRect } | null>(null);
  const browse = useRef<{ id: number; start: number; moved: boolean } | null>(null), suppressClick = useRef(false);
  const selectedNode = useRef<HTMLDivElement>(null), phaseRef = useRef(phase), previousActive = useRef(active);
  phaseRef.current = phase;
  const still = useWindowStill(), pack = packs.find(item => item.id === selected);
  const count = packs.length + 1;
  const contents = useMemo(() => pack ? pack.cardIds.flatMap(id => { const card = cards.find(item => item.card_id === id); return card ? [card] : []; }) : [], [cards, pack]);
  useDesktopUpdateBlock(editing ? "卡包正在编辑或保存。" : null);
  const reseal = useCallback(() => { turn.current = null; setRotating(false); setPose({ yaw: -14, pitch: -3 }); cut.current = null; setProgress(0); setSelected(null); setPhase("browse"); setNotice(""); }, []);
  // Opening is presentation state only. Every fresh visit starts with sealed packs.
  useLayoutEffect(() => { if (active && !previousActive.current) reseal(); previousActive.current = active; }, [active, reseal]);
  useEffect(() => { onEditingChange(Boolean(editing)); return () => onEditingChange(false); }, [editing, onEditingChange]);
  useEffect(() => { const cancel = () => { turn.current = null; setRotating(false); cut.current = null; if (phaseRef.current === "selected") setProgress(0); }; window.addEventListener("blur", cancel); return () => window.removeEventListener("blur", cancel); }, []);
  useEffect(() => {
    if (!active || editing) return;
    const key = (event: KeyboardEvent) => { if (document.querySelector("dialog[open]") || event.target instanceof Element && event.target.matches("input,textarea,select")) return; if (event.key === "Escape" && phaseRef.current !== "cards") { event.preventDefault(); reseal(); } };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, [active, editing, reseal]);
  useEffect(() => {
    setSettled(false);
    if (phase !== "selected") return;
    const timer = window.setTimeout(() => setSettled(true), 660);
    return () => clearTimeout(timer);
  }, [phase, selected]);
  const open = useCallback(() => {
    if (phaseRef.current !== "selected" || !canCut || !pack) return;
    if (!contents.length) { setNotice("这个卡包还没有角色卡。先点“设计与装卡”，挑选要装入的角色。"); return; }
    const rect = selectedNode.current?.getBoundingClientRect();
    setOrigin({ x: rect ? rect.x + rect.width / 2 : innerWidth / 2, y: rect ? rect.y + rect.height * .2 : innerHeight * .4 });
    cut.current = null; setProgress(1); setPhase("opening");
  }, [pack, contents.length, canCut]);
  useEffect(() => {
    if (phase !== "opening") return;
    const timer = window.setTimeout(() => setPhase(matchMedia("(prefers-reduced-motion: reduce)").matches ? "cards" : "spilling"), 450);
    return () => clearTimeout(timer);
  }, [phase]);
  const down = (event: PointerEvent<HTMLDivElement>) => {
    if (phase !== "selected" || !canCut || !event.isPrimary || event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect(), point = (event.clientX - rect.x) / rect.width;
    if (point > .24 && point < .76) { setNotice("从封口任意一端按住，横向划到另一端。"); return; }
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    const side = point < .5 ? "left" : "right"; cut.current = { id: event.pointerId, start: event.clientX, side, rect }; setDirection(side); setNotice("");
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const value = cut.current; if (!value || value.id !== event.pointerId || Math.abs(event.clientY - (value.rect.y + value.rect.height / 2)) > value.rect.height + 25) return;
    const distance = (event.clientX - value.start) * (value.side === "left" ? 1 : -1);
    const next = Math.max(0, Math.min(1, distance / (value.rect.width * .76))); setProgress(next);
    if (next >= .98) { open(); if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }
  };
  const turnDown = (event: PointerEvent<HTMLDivElement>) => {
    if (phase !== "selected" || !settled || !event.isPrimary || event.button !== 0 || (event.target as Element).closest("[data-seal-controls]")) return;
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    turn.current = { id: event.pointerId, x: event.clientX, y: event.clientY, ...pose }; setRotating(true);
  };
  const turnMove = (event: PointerEvent<HTMLDivElement>) => {
    const value = turn.current; if (!value || value.id !== event.pointerId) return;
    const yaw = value.yaw + (event.clientX - value.x) * .65;
    const pitch = Math.max(-72, Math.min(72, value.pitch - (event.clientY - value.y) * .45));
    setPose({ yaw, pitch });
  };
  const turnEnd = (event: PointerEvent<HTMLDivElement>) => {
    if (turn.current?.id !== event.pointerId) return;
    turn.current = null; setRotating(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const next = (amount: number) => setFocus(value => (value + amount + count) % count);
  const galleryVisible = phase !== "cards";
  return <>
    {(phase === "cards" || pack && (phase === "opening" || phase === "spilling")) && <div className={styles.actualCards} data-veiled={phase !== "cards" || undefined}>{renderCards(pack ?? null)}</div>}
    {galleryVisible && <section className={styles.gallery} aria-label="角色卡包" data-phase={phase} data-active={active || undefined} data-still={still || undefined} inert={!active || Boolean(editing)} aria-hidden={!active}
      onWheel={event => { if (phase !== "browse") return; if (Math.abs(event.deltaX || event.deltaY) > 4) next(event.deltaX + event.deltaY > 0 ? 1 : -1); }}>
      <div className={styles.gallerySky} aria-hidden="true" /><div className={styles.floor} aria-hidden="true" />
      <div className={styles.intro}><span>角色卡包 <i>{packs.length} 包</i></span><h2>{phase === "browse" ? "下一次相遇，正等待拆封。" : phase === "selected" ? "里面的故事，已经等不及了。" : "让故事，来到你身边。"}</h2><p>{phase === "browse" ? "挑选一个卡包，亲手打开这份期待。" : phase === "selected" ? "拖动包体自由旋转 · 在顶部封口横向划开" : ""}</p></div>
      <div className={styles.packStage} onPointerDown={event => { if (phase === "browse" && !(event.target as Element).closest("button")) { event.currentTarget.setPointerCapture(event.pointerId); browse.current = { id: event.pointerId, start: event.clientX, moved: false }; } }}
        onPointerMove={event => { const value = browse.current; if (!value || value.id !== event.pointerId) return; const delta = event.clientX - value.start; if (Math.abs(delta) > 80) { next(delta < 0 ? 1 : -1); value.start = event.clientX; value.moved = true; } }}
        onPointerUp={() => { suppressClick.current = browse.current?.moved ?? false; browse.current = null; window.setTimeout(() => { suppressClick.current = false; }, 0); }} onPointerCancel={() => { browse.current = null; }}>
        {[...packs, null].map((item, index) => {
          const delta = ((index - focus + count * 1.5) % count) - count / 2;
          const chosen = item?.id === selected, hidden = phase !== "browse" && !chosen;
          return <div key={item?.id ?? "new"} className={styles.packSlot} data-selected={chosen || undefined} data-dimmed={hidden || undefined} data-rotating={chosen && rotating || undefined} ref={chosen ? selectedNode : undefined}
            style={{ "--slot": delta, "--tilt": `${[ -7, 5, -3, 8, -5, 4 ][index % 6]}deg`, "--float-delay": `${-index * 1.13}s` } as CSSProperties}>
            {item ? <div className={styles.packObject}>
              <div className={styles.packSolid} data-pack-solid data-visible-face={chosen && backFacing ? "back" : "front"} data-turning={chosen && rotating || undefined}
                style={{ "--pack-depth": `${Math.min(25, 12 + item.cardIds.length * 1.7)}px`, "--turn-y": `${chosen ? pose.yaw : -12}deg`, "--turn-x": `${chosen ? pose.pitch : 0}deg`, "--shine-x": `${50 + Math.sin((chosen ? pose.yaw : -12) * Math.PI / 180) * 43}%`, "--shine-y": `${35 + (chosen ? pose.pitch : 0) * .5}%`, "--shine-angle": `${110 - (chosen ? pose.yaw % 360 : -12) * .18}deg` } as CSSProperties}
                onPointerDown={turnDown} onPointerMove={turnMove} onPointerUp={turnEnd} onPointerCancel={turnEnd} onLostPointerCapture={event => { if (turn.current?.id === event.pointerId) { turn.current = null; setRotating(false); } }}>

              <button type="button" className={styles.packButton} disabled={hidden || phase === "opening" || phase === "spilling"} aria-label={`选择卡包：${item.name}`} aria-pressed={chosen} onKeyDown={event => { if (!chosen || phase !== "selected") return; if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setPose(value => ({ ...value, yaw: value.yaw + (event.key === "ArrowRight" ? 15 : -15) })); } else if (event.key === "ArrowUp" || event.key === "ArrowDown") { event.preventDefault(); setPose(value => ({ ...value, pitch: Math.max(-72, Math.min(72, value.pitch + (event.key === "ArrowDown" ? 10 : -10))) })); } else if (event.key === "Home") { event.preventDefault(); setPose({ yaw: 0, pitch: 0 }); } }} onClick={() => { if (suppressClick.current || chosen) return; setPose({ yaw: -14, pitch: -3 }); setRotating(false); setSelected(item.id); setFocus(index); setProgress(0); setNotice(""); setPhase("selected"); }}>
                <PackBody pack={item} images={images} />
              </button>
              {chosen && <div className={styles.sealControls} data-seal-controls data-side={backFacing ? "back" : "front"}><div className={styles.mouth} /><div className={styles.tearCap} aria-hidden="true" style={{ backgroundColor: item.design[backFacing ? "back" : "front"].color }} />
                <div className={styles.cutBand} data-direction={direction} role="slider" tabIndex={phase === "selected" && canCut ? 0 : -1} aria-disabled={!canCut} aria-label="卡包封口：从一端按住横向划开，也可用方向键或Enter打开" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}
                  onPointerDown={down} onPointerMove={move} onPointerUp={event => { if (cut.current?.id === event.pointerId) { cut.current = null; setProgress(0); } }} onPointerCancel={() => { cut.current = null; setProgress(0); }} onLostPointerCapture={() => { if (cut.current) { cut.current = null; setProgress(0); } }}
                  onKeyDown={event => { if (phase !== "selected") return; if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); setProgress(value => Math.min(1, value + .2)); if (progress >= .79) open(); } }}>
                  <span className={styles.cutGuide} /><span className={styles.cutTrace} style={{ transform: `scaleX(${progress})` }} /><span className={styles.scissors} style={{ left: `${direction === "left" ? progress * 100 : 100 - progress * 100}%` }}><Scissors size={19} /></span><small>{!settled ? "稍等，卡包正在靠近" : !canCut ? "转动包体，露出封口" : progress > 0 ? "沿着封口，继续划开" : "按住这里 · 横向划开"}</small>
                </div></div>}
              </div>
            </div> : <button className={styles.newPack} type="button" aria-label="创建新卡包" onClick={() => setEditing(defaultPack("我的新卡包", packs.length))}><Plus size={31} strokeWidth={1} /><span>装一包新的故事</span><small>创建卡包</small></button>}
            {phase === "browse" && item && <div className={styles.packCaption}><span>{item.name}</span><small>{item.cardIds.length} 张角色卡</small></div>}
          </div>;
        })}
      </div>
      {phase === "browse" ? <><button className={`${styles.arrow} ${styles.previous}`} type="button" aria-label="上一个卡包" onClick={() => next(-1)}><ChevronLeft size={25} /></button><button className={`${styles.arrow} ${styles.next}`} type="button" aria-label="下一个卡包" onClick={() => next(1)}><ChevronRight size={25} /></button><footer className={styles.galleryFooter}><button type="button" onClick={() => { setSelected(null); setPhase("cards"); }}>全部角色卡</button><span>左右滑动浏览 · 每次归来，都是一份重新封好的期待</span><button type="button" onClick={() => setEditing(defaultPack("我的新卡包", packs.length))}><Plus size={15} />创建卡包</button></footer></> : <div className={styles.selectedActions}><h3>{pack?.name}</h3><p>{notice || pack?.subtitle}</p><div><button type="button" disabled={phase !== "selected"} onClick={() => setPose({ yaw: Math.round(pose.yaw / 360) * 360, pitch: 0 })}><RotateCcw size={14} />正面</button><button type="button" disabled={phase !== "selected"} onClick={() => setPose({ yaw: Math.round((pose.yaw - 180) / 360) * 360 + 180, pitch: 0 })}>背面</button><button type="button" disabled={phase !== "selected"} onClick={reseal}><X size={15} />放回</button><button type="button" disabled={phase !== "selected" || !pack} onClick={() => pack && setEditing(pack)}><Palette size={15} />设计与装卡</button></div></div>}
      <p className={styles.announcement} role="status">{phase === "opening" || phase === "spilling" ? "卡包已剪开，角色卡正在散出。" : notice}</p>
    </section>}
    {phase === "cards" && active && !editing && <button type="button" className={styles.backToPacks} onClick={reseal}><ArrowLeft size={15} />返回卡包<span>{pack?.name ?? "全部角色卡"}</span></button>}
    {phase === "spilling" && active && <PackSpill cards={contents} images={images} origin={origin} onComplete={() => setPhase("cards")} />}
    {editing && <PackEditor pack={editing} cards={cards} images={images} onSave={async value => { await onSave(value); setPose({ yaw: -14, pitch: -3 }); setSelected(value.id); const index = packs.findIndex(item => item.id === value.id); setFocus(index < 0 ? packs.length : index); setProgress(0); setPhase("selected"); }} onClose={() => { onDiscard?.(editing); setEditing(null); }} />}
  </>;
}
