import { memo } from "react";
import { PackFace } from "./PackFace";
import type { CharacterPack, PackImages } from "./packDesign";
import styles from "./Packs.module.css";

/** Both designed faces and the folded rims occupy the same CSS 3D space. */
export const PackBody = memo(function PackBody({ pack, images }: { pack: CharacterPack; images: PackImages }) {
  return <div className={styles.packGeometry}>
    <div className={`${styles.packPlane} ${styles.frontPlane}`} data-pack-face="front"><PackFace pack={pack} face={pack.design.front} images={images} /></div>
    <div className={`${styles.packPlane} ${styles.backPlane}`} data-pack-face="back"><PackFace pack={pack} face={pack.design.back} images={images} /><span className={styles.backFin} aria-hidden="true" /></div>
    <div className={`${styles.foldedRim} ${styles.leftRim}`} aria-hidden="true" />
    <div className={`${styles.foldedRim} ${styles.rightRim}`} aria-hidden="true" />
    <div className={`${styles.sealRim} ${styles.topRim}`} aria-hidden="true" />
    <div className={`${styles.sealRim} ${styles.bottomRim}`} aria-hidden="true" />
  </div>;
});
