import { memo, type CSSProperties, type ReactNode } from "react";
import type { WorldSettings } from "@dreamtalk/api-client";
import { mixOklab, skyAt, worldClock } from "../sky";
import styles from "./Archive.module.css";

const STARS = Array.from({ length: 110 }, (_, index) => {
  const a = Math.sin(index * 12.9898) * 43758.5453, b = Math.sin(index * 78.233) * 12345.678;
  const x = a - Math.floor(a), y = b - Math.floor(b);
  return { x: x * 100, y: y * 70, size: 0.4 + ((x + y) % 1) * 0.9, delay: -(index % 9) * 0.6 };
});

/** Sky variables for the archive: the last world's current hour, or a timeless night. */
export function archiveSky(world: WorldSettings | undefined): { style: CSSProperties; body: "sun" | "moon" } {
  const clock = world ? worldClock(world.world_time) : null;
  const sky = skyAt(clock ? clock.minuteOfDay : 0);
  return {
    body: sky.body.kind,
    style: {
      "--dt-sky-zenith": sky.zenith, "--dt-sky-horizon": sky.horizon, "--rim": mixOklab(sky.horizon, "#ffffff", 0.25),
      "--dt-sky-x": sky.body.x.toFixed(4), "--dt-sky-altitude": sky.body.altitude.toFixed(4), "--dt-stars": sky.stars.toFixed(3),
    } as CSSProperties,
  };
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
