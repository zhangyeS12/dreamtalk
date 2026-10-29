import { memo, type CSSProperties, type ReactNode } from "react";
import type { WorldSettings } from "@dreamtalk/api-client";
import { mixOklab, skyAt, skyOf, skyVars, starField } from "../sky";
import styles from "./Archive.module.css";

const STARS = starField(110);

/** Sky variables for the archive: the last world's current hour, or a timeless night. */
export function archiveSky(world: WorldSettings | undefined): { style: CSSProperties; body: "sun" | "moon" } {
  const sky = skyOf(world) ?? skyAt(0);
  return { body: sky.body.kind, style: { ...skyVars(sky), "--rim": mixOklab(sky.horizon, "#ffffff", 0.25) } as CSSProperties };
}

/** A dark room whose only light is a window onto that sky. */
export const ArchiveRoom = memo(function ArchiveRoom({ body, children }: { body: "sun" | "moon"; children?: ReactNode }) {
  return <div className={styles.room} aria-hidden="true">
    <div className={styles.window}>
      <div className={styles.sky} />
      <div className={styles.stars}>{STARS.map(star => <i key={`${star.x}:${star.y}`} style={{ left: `${star.x}%`, top: `${star.y}%`, transform: `scale(${star.size})`, animationDelay: `${star.delay}s` }} />)}</div>
      <div className={styles.body} data-kind={body} />
      <svg viewBox="0 0 1440 400" preserveAspectRatio="none">
        <path className={styles.far} d="M0 230 C140 190 230 150 350 176 C460 200 540 140 650 150 C760 160 820 214 940 196 C1050 180 1120 126 1240 144 C1330 158 1390 196 1440 190 V400 H0Z" />
        <path className={styles.near} d="M0 320 C180 294 320 304 470 314 C640 326 760 292 930 300 C1100 308 1250 294 1440 304 V400 H0Z" />
      </svg>
    </div>
    <div className={styles.floor} />
    {children}
  </div>;
});
