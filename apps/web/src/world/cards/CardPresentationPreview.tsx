import { useEffect, useState, type CSSProperties } from "react";
import type { CardDesign, CoreClient } from "@dreamtalk/api-client";
import { CardFace } from "./CardFaces";
import styles from "./Cards.module.css";

export function CardPresentationPreview({ client, design, cardId, previewId }: { client: CoreClient; design: CardDesign; cardId: string; previewId?: string }) {
  const [side, setSide] = useState<"front" | "back">("front");
  const [images, setImages] = useState<Record<string, string>>({}), [failed, setFailed] = useState(false);
  const digests = [...new Set([design.front.image_digest, design.back.image_digest].filter((item): item is string => Boolean(item)))].sort().join(",");
  useEffect(() => {
    const controller = new AbortController(), urls: string[] = [];
    setImages({}); setFailed(false);
    for (const digest of digests.split(",").filter(Boolean)) void (previewId ? client.libraryPreviewImage(previewId, digest, controller.signal) : client.libraryImage(cardId, digest, controller.signal)).then(blob => {
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob); urls.push(url); setImages(current => ({ ...current, [digest]: url }));
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { controller.abort(); urls.forEach(url => URL.revokeObjectURL(url)); };
  }, [client, cardId, previewId, digests]);
  return <section className={styles.presentationPreview} aria-label="分享卡面预览">
    <div className={styles.row}>{(["front", "back"] as const).map(value => <button type="button" key={value} aria-pressed={side === value} onClick={() => setSide(value)}>{value === "front" ? "正面" : "背面"}</button>)}</div>
    <div className={styles.previewCard} style={{ "--card-w": "min(410px, calc(100vw - 100px))" } as CSSProperties}>
      <CardFace design={design} face={design[side]} image={images[design[side].image_digest ?? ""]} side={side} />
    </div>
    {failed && <p role="alert">卡面图片未能读取，请关闭后重新预览再核对。</p>}
  </section>;
}
