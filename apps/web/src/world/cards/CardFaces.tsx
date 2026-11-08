import { useEffect, useState, type CSSProperties } from "react";
import type { CoreClient, CardDesign, CardFaceDesign, CardLayer } from "@dreamtalk/api-client";
import styles from "./Cards.module.css";

export function useCardImages(client: CoreClient, cardId: string, design: CardDesign) {
  const [images, setImages] = useState<Record<string, string>>({});
  const digests = [...new Set([design.front.image_digest, design.back.image_digest].filter((x): x is string => Boolean(x)))].sort().join(",");
  useEffect(() => {
    const controller = new AbortController(), urls: string[] = [];
    setImages({});
    for (const digest of digests.split(",").filter(Boolean)) void client.libraryImage(cardId, digest, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob); urls.push(url); setImages(current => ({ ...current, [digest]: url }));
    }).catch(() => { /* The card remains usable with its text and colors. */ });
    return () => { controller.abort(); urls.forEach(url => URL.revokeObjectURL(url)); };
  }, [client, cardId, digests]);
  return images;
}
export function CardFace({ design, face, image, side, editing, selectedLayer, onLayer }: {
  design: CardDesign; face: CardFaceDesign; image?: string; side: "front" | "back";
  editing?: boolean; selectedLayer?: string; onLayer?: (event: React.PointerEvent, layer: CardLayer) => void;
}) {
  return <span className={styles.face} data-face={side} data-material={face.material} data-layout={face.layout} data-frame={face.frame || undefined}
    style={{ "--card-color": face.color, "--card-accent": face.accent } as CSSProperties}>
    {image && <img className={styles.image} src={image} alt="" draggable={false} style={{ opacity: face.image_opacity / 100 }} />}
    {face.layout === "portrait" ? <><span className={styles.art} aria-hidden="true"><span className={styles.orbit} /><span className={styles.glyph}>{design.glyph}</span></span><span className={styles.brand}>dreamtalk</span><span className={styles.cornerStar}>✦</span></> : <><span className={styles.backTag}>{design.display_name} · 角色档案</span><span className={styles.backRule} /><span className={styles.backSign}>在不同的世界，留下不同的故事。</span></>}
    <span className={styles.foil} aria-hidden="true" />
    <span className={styles.number}>DT · CHARACTER</span>
    {face.layers.map(item => <span key={item.id} className={styles.layer} data-kind={item.kind} data-selected={editing && selectedLayer === item.id || undefined}
      onPointerDown={editing ? event => onLayer?.(event, item) : undefined}
      style={{ left: `${item.x}%`, top: `${item.y}%`, fontSize: `calc(var(--card-w)*${item.size / 410})`, color: item.color, opacity: item.opacity / 100, transform: `${item.anchor === "center" ? "translate(-50%,-50%) " : ""}rotate(${item.rotation}deg)` }}>
      {item.text}
    </span>)}
  </span>;
}
export function CardFaces({ design, images }: { design: CardDesign; images: Record<string, string> }) {
  return <><CardFace design={design} face={design.front} image={images[design.front.image_digest ?? ""]} side="front" />
    <CardFace design={design} face={design.back} image={images[design.back.image_digest ?? ""]} side="back" /></>;
}
