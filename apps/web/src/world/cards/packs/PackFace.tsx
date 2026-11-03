import { memo, type CSSProperties, type PointerEvent } from "react";
import type { CardLayer } from "@dreamtalk/api-client";
import type { CharacterPack, PackFaceDesign, PackImages } from "./packDesign";
import styles from "./Packs.module.css";
import foilTexture from "./assets/sealed-foil-v1.png";

export const PackFace = memo(function PackFace({ pack, face, images, editing, selected, onLayer }: { pack: CharacterPack; face: PackFaceDesign; images: PackImages; editing?: boolean; selected?: string | null; onLayer?: (event: PointerEvent, layer: CardLayer) => void }) {
  return <div className={styles.surface} data-side={face === pack.design.back ? "back" : "front"} data-material={face.material} style={{ "--pack-color": face.color, "--pack-accent": face.accent } as CSSProperties}>
    {face.image && images.url(face.image) && <img className={styles.coverImage} src={images.url(face.image)} alt="" draggable={false} style={{ opacity: face.imageOpacity / 100 }} />}
    <img className={styles.materialFilm} src={foilTexture} alt="" draggable={false} aria-hidden="true" />
    <div className={styles.printedFrame} data-frame={face.frame || undefined} />
    <div className={styles.sealedEdge} aria-hidden="true" />
    <div className={styles.bottomSeal} aria-hidden="true" />
    <span className={styles.packBrand}>dreamtalk</span>
    <div className={styles.packEmblem} aria-hidden="true"><span /><span /><b>{face.glyph}</b></div>
    <div className={styles.foil} aria-hidden="true" />
    {face.layers.map(item => <span key={item.id} data-layer={item.id} data-selected={editing && selected === item.id || undefined} className={styles.printLayer}
      onPointerDown={editing ? event => onLayer?.(event, item) : undefined}
      style={{ left: `${item.x}%`, top: `${item.y}%`, fontSize: `calc(var(--pack-w) * ${item.size / 260})`, color: item.color, opacity: item.opacity / 100, transform: `translate(-50%,-50%) rotate(${item.rotation}deg)` }}>{item.text}</span>)}
    <span className={styles.packCount}>{String(pack.cardIds.length).padStart(2, "0")} 张角色卡<span>CHARACTER COLLECTION</span></span>
  </div>;
});
