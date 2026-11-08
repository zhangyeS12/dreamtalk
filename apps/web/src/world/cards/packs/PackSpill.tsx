import { useEffect, useRef } from "react";
import type { LibraryCardItem } from "@dreamtalk/api-client";
import { CardFace } from "../CardFaces";
import { defaultDesign, restPose } from "../cardDesign";
import type { PackImages } from "./packDesign";
import styles from "./Packs.module.css";

export function PackSpill({ cards, images, origin, onComplete }: { cards: LibraryCardItem[]; images: PackImages; origin: { x: number; y: number }; onComplete: () => void }) {
  const root = useRef<HTMLDivElement>(null), done = useRef(onComplete);
  done.current = onComplete;
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { done.current(); return; }
    let cancelled = false;
    const animations: Animation[] = [];
    // The original CardRing mounts beneath this transition; its actual positions
    // are the landing points, rather than a second implementation of the ring.
    const timer = window.setTimeout(() => {
      const width = Math.min(410, innerWidth - 52);
      const nodes = root.current?.querySelectorAll<HTMLElement>("[data-spill-card]") ?? [];
      nodes.forEach((node, index) => {
        const card = cards[index];
        const candidates = [...document.querySelectorAll<HTMLElement>(`[data-card-id="${card.card_id}"]`)];
        const rect = candidates.map(node => node.getBoundingClientRect()).filter(rect => rect.width > 0).sort((a, b) => Math.abs(a.x + a.width / 2 - innerWidth / 2) - Math.abs(b.x + b.width / 2 - innerWidth / 2))[0];
        const endX = rect ? rect.x + rect.width / 2 - origin.x : (index - (cards.length - 1) / 2) * 170;
        const endY = rect ? rect.y + rect.height / 2 - origin.y : 25;
        const scale = rect ? Math.min(1.4, rect.width / width) : 1;
        const spread = (index - (cards.length - 1) / 2);
        const limit = Math.max(75, innerWidth / 2 - width / 2 - 16);
        const scatter = Math.max(-limit, Math.min(limit, spread * Math.min(110, innerWidth / Math.max(4, cards.length))));
        const animation = node.animate([
          { transform: "translate(-50%,-50%) translate(0,70px) rotate(90deg) scale(.33)", opacity: 0, offset: 0 },
          { transform: `translate(-50%,-50%) translate(${scatter * .3}px,-85px) rotate(${75 - spread * 10}deg) scale(.66)`, opacity: 1, offset: .2 },
          { transform: `translate(-50%,-50%) translate(${scatter}px,${-140 + Math.abs(spread) * 26}px) rotate(${spread * 17}deg) scale(.94)`, opacity: 1, offset: .5 },
          { transform: `translate(-50%,-50%) translate(${endX}px,${endY}px) rotate(${restPose(card.card_id).roll}deg) scale(${scale})`, opacity: 1, offset: .94 },
          { transform: `translate(-50%,-50%) translate(${endX}px,${endY}px) rotate(${restPose(card.card_id).roll}deg) scale(${scale})`, opacity: 0, offset: 1 },
        ], { duration: 1650, delay: index * Math.min(95, 360 / Math.max(1, cards.length)), easing: "cubic-bezier(.22,.61,.36,1)", fill: "both" });
        animations.push(animation);
      });
      void Promise.all(animations.map(animation => animation.finished.catch(() => undefined))).then(() => { if (!cancelled) done.current(); });
      if (!nodes.length) done.current();
    }, 100);
    return () => { cancelled = true; clearTimeout(timer); animations.forEach(animation => animation.cancel()); };
  }, [cards, origin.x, origin.y]);
  return <div ref={root} className={styles.spill} aria-hidden="true">{cards.map(card => { const design = defaultDesign(card); return <div className={styles.spillCard} key={card.card_id} data-spill-card style={{ left: origin.x, top: origin.y }}><CardFace design={design} face={design.front} side="front" image={design.front.image_digest ? images.url(design.front.image_digest) : undefined} /></div>; })}</div>;
}
