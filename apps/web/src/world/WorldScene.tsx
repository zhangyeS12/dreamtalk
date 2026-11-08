import { memo } from "react";
import { starField } from "./sky";
import styles from "./WorldScene.module.css";

const STARS = starField(96);

/**
 * The world behind every panel: sky, sun or moon, drifting cloud, distant land.
 * Colours and positions come only from CSS custom properties written from the
 * world clock (see sky.ts); nothing here represents events or activity.
 */
export const WorldScene = memo(function WorldScene({ kind }: { kind: "sun" | "moon" | null }) {
  return <div className={styles.scene} aria-hidden="true">
    <div className={styles.sky} />
    <div className={styles.stars}>
      {STARS.map(star => <i key={`${star.x}:${star.y}`} style={{ left: `${star.x}%`, top: `${star.y}%`, transform: `scale(${star.size})`, animationDelay: `${star.delay}s` }} />)}
    </div>
    {kind && <div className={styles.body} data-kind={kind} />}
    <div className={styles.cloud} style={{ top: "16%", width: 360, animationDuration: "170s", animationDelay: "-40s" }} />
    <div className={styles.cloud} style={{ top: "29%", width: 230, animationDuration: "130s", animationDelay: "-95s", opacity: 0.32 }} />
    <div className={styles.cloud} style={{ top: "10%", width: 480, animationDuration: "230s", animationDelay: "-150s", opacity: 0.26 }} />
    <svg className={styles.land} viewBox="0 0 1440 400" preserveAspectRatio="none">
      <path className={styles.far} d="M0 210 C120 170 210 120 330 150 C430 175 500 110 610 120 C720 130 780 190 900 170 C1010 150 1080 90 1200 110 C1300 128 1370 170 1440 160 V400 H0Z" />
      <path className={styles.mid} d="M0 270 C140 240 230 200 360 232 C470 260 560 214 690 226 C820 238 880 286 1010 262 C1130 240 1220 206 1330 228 C1390 240 1420 250 1440 254 V400 H0Z" />
      <path className={styles.near} d="M0 330 C180 300 320 310 470 322 C640 336 760 298 930 308 C1100 318 1250 300 1440 312 V400 H0Z" />
    </svg>
    <div className={styles.mist} />
  </div>;
});
