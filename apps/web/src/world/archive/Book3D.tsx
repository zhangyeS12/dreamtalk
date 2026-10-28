import type { CSSProperties, ReactNode } from "react";
import type { BookDesign } from "@dreamtalk/api-client";
import type { Sky } from "../sky";
import { BOOK_FACE, BOOK_HEIGHT, FONTS, THICKNESS, spineStyle, stickerSource, type DesignFace } from "./bookDesign";
import styles from "./Book3D.module.css";

export type BookArt = { front?: string; spine?: string; back?: string; jacket?: string; jacketAspect?: number };
export type BookLook = { name: string; design: BookDesign; art: BookArt; uploads: Record<string, string>; sky: Sky; paused: boolean };

const percent = (value: number) => `${value}%`;

function faceBackground(look: BookLook, face: DesignFace): CSSProperties {
  const { design, art } = look, T = THICKNESS[design.thickness];
  if (design.wrap && art.jacket) {
    // One image wraps back → spine → front, scaled like `cover` across the whole jacket.
    const total = BOOK_FACE * 2 + T, aspect = art.jacketAspect || 0.7;
    const width = Math.max(total, BOOK_HEIGHT * aspect), height = width / aspect;
    const offset = { back: 0, spine: BOOK_FACE, front: BOOK_FACE + T }[face] + (width - total) / 2;
    return { backgroundImage: `url("${art.jacket}")`, backgroundSize: `${width}px ${height}px`, backgroundPosition: `${-offset}px ${(BOOK_HEIGHT - height) / 2}px`, backgroundColor: design.case_color };
  }
  const image = art[face];
  return image ? { backgroundImage: `url("${image}")`, backgroundSize: "cover", backgroundPosition: "center", backgroundColor: design.case_color } : { backgroundColor: design.case_color };
}

/** One flat face of a designed book. Shared by the 3D book, the designer canvas and the entering animation. */
export function FaceArt({ look, face, stickers = true, children }: { look: BookLook; face: DesignFace; stickers?: boolean; children?: ReactNode }) {
  const { design, sky } = look, title = design.title, font = FONTS[title.font].stack;
  const skyVars = { "--wz": sky.zenith, "--wh": sky.horizon, "--wx": sky.body.x.toFixed(3), "--wa": sky.body.altitude.toFixed(3) } as CSSProperties;
  return <span className={styles.art} data-face={face}>
    <span className={styles.base} style={faceBackground(look, face)} />
    <span className={styles.material} data-material={design.material} />
    {face === "front" && design.sky_window.on && <span className={styles.skyWindow} style={{ left: percent(design.sky_window.x), top: percent(design.sky_window.y), width: percent(design.sky_window.w), height: percent(design.sky_window.h), ...skyVars }}><i data-kind={sky.body.kind} /></span>}
    {face === "front" && title.text && <span className={styles.title} data-vertical={title.vertical || undefined}
      style={{ left: percent(title.x), top: percent(title.y), font: `800 ${title.size}px ${font}`, color: title.color }}>{title.text}</span>}
    {face === "front" && design.brand && <span className={styles.brand} style={{ color: title.color }}>DREAMTALK</span>}
    {face === "spine" && <>
      <span className={styles.band} data-style={spineStyle(look.name)} data-paused={look.paused || undefined} style={{ "--bz": sky.zenith, "--bh": sky.horizon, "--bx": sky.body.x.toFixed(3) } as CSSProperties}><i data-kind={sky.body.kind} /></span>
      {title.text && <span className={styles.spineTitle} data-style={spineStyle(look.name)} style={{ fontFamily: font, color: title.color }}>{title.text}</span>}
      {design.brand && <span className={styles.spineMark} style={{ color: title.color }}>dreamtalk</span>}
    </>}
    {face === "back" && design.brand && <span className={styles.backMark} style={{ color: title.color }}>DREAMTALK · 世界档案</span>}
    {stickers && design.stickers[face].map((item, index) => {
      const src = stickerSource(item, look.uploads);
      return src ? <img key={`${index}:${item.ref}`} className={styles.sticker} src={src} alt="" draggable={false}
        style={{ left: percent(item.x), top: percent(item.y), width: percent(item.w), opacity: item.opacity, transform: `translate(-50%, -50%) rotate(${item.r}deg)` }} /> : null;
    })}
    {children}
  </span>;
}

/** Six faces around the book's centre so it can be turned all the way round. */
export function Book3DFaces({ look }: { look: BookLook }) {
  return <>
    <span className={`${styles.face} ${styles.spine}`}><FaceArt look={look} face="spine" /><span className={styles.light} /><span className={styles.shade} /></span>
    <span className={`${styles.face} ${styles.front}`}><FaceArt look={look} face="front" /><span className={styles.light} /><span className={styles.shade} /></span>
    <span className={`${styles.face} ${styles.back}`}><FaceArt look={look} face="back" /><span className={styles.light} /><span className={styles.shade} /></span>
    {(["edge", "top", "bottom"] as const).map(face => <span key={face} className={`${styles.face} ${styles[face]}`} data-gilt={look.design.edge === "gilt" || undefined}
      style={{ "--case": look.design.case_color } as CSSProperties}><span className={styles.pages} /><span className={styles.light} /><span className={styles.shade} /></span>)}
  </>;
}

/** An unprinted case: it sits quietly in the ring until a world is written into it. */
export function BlankFaces() {
  return <>
    <span className={`${styles.face} ${styles.spine} ${styles.blank}`}><span className={styles.plus}>＋</span><span className={styles.emboss}>dreamtalk</span><span className={styles.light} /><span className={styles.shade} /></span>
    <span className={`${styles.face} ${styles.front} ${styles.blank}`}><span className={styles.blankPrompt}>新的世界</span><span className={styles.shade} /></span>
    <span className={`${styles.face} ${styles.back} ${styles.blank}`}><span className={styles.shade} /></span>
    <span className={`${styles.face} ${styles.edge}`}><span className={styles.pages} /><span className={styles.shade} /></span>
  </>;
}

export const bookStyles = styles;
