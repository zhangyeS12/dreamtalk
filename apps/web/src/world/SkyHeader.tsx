import type { CSSProperties, ReactNode } from "react";
import type { WorldSettings } from "@dreamtalk/api-client";
import { formatClock, skyAt, worldClock } from "./sky";
import styles from "./SkyHeader.module.css";

/** Sky colours and sun/moon position as CSS custom properties for the workspace root. */
export function skyStyle(world: WorldSettings | undefined): CSSProperties {
  const clock = world ? worldClock(world.world_time) : null;
  if (!clock) return {};
  const sky = skyAt(clock.minuteOfDay);
  return {
    "--dt-sky-zenith": sky.zenith,
    "--dt-sky-horizon": sky.horizon,
    "--dt-sky-x": sky.body.x.toFixed(4),
    "--dt-sky-altitude": sky.body.altitude.toFixed(4),
    "--dt-stars": sky.stars.toFixed(3),
  } as CSSProperties;
}

// Fixed star field (percent coordinates); brightness follows the sky only.
const STARS: ReadonlyArray<readonly [number, number, number]> = [
  [3, 22, 1], [7, 64, .6], [11, 38, .8], [16, 14, .5], [19, 72, .7], [24, 30, 1], [28, 58, .5], [33, 18, .7],
  [37, 80, .6], [41, 42, .9], [46, 12, .6], [50, 66, .5], [54, 28, .8], [58, 52, .6], [62, 16, 1], [66, 74, .5],
  [70, 36, .7], [74, 60, .6], [78, 20, .9], [82, 46, .5], [86, 70, .8], [90, 26, .6], [94, 54, .9], [97, 14, .5],
];

export function SkyHeader({ world, modeSwitch, onArchive, status }: {
  world: WorldSettings | undefined;
  modeSwitch?: ReactNode;
  onArchive: () => void;
  status?: ReactNode;
}) {
  const clock = world ? worldClock(world.world_time) : null;
  const sky = clock ? skyAt(clock.minuteOfDay) : null;
  const paused = world?.clock_state === "paused";
  const degraded = world?.runtime_state === "degraded";
  return <header className={styles.sky} data-paused={paused || undefined}>
    <div className={styles.stars} aria-hidden="true">
      {STARS.map(([x, y, size]) => <i key={`${x}:${y}`} style={{ left: `${x}%`, top: `${y}%`, transform: `scale(${size})` }} />)}
    </div>
    {sky && <div className={styles.body} data-kind={sky.body.kind} aria-hidden="true" />}
    <div className={styles.world}>
      <img className={styles.mark} src="/brand/dreamtalk-logo.png" alt="dreamtalk" width="34" height="30" />
      <div className={styles.names}>
        <strong>{world?.name ?? "正在读取世界…"}</strong>
        {world && <span className={styles.clock}>
          {clock ? <>{formatClock(clock)}<span className={styles.phase}>{sky?.phase}</span></> : `逻辑时间 ${world.world_time} 微秒`}
          {paused && <span className={styles.state}>已暂停</span>}
          {degraded && <span className={styles.state} data-tone="danger">运行异常</span>}
        </span>}
      </div>
    </div>
    {status}
    <div className={styles.actions}>
      {modeSwitch}
      <button type="button" className={styles.archive} onClick={onArchive}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4.5h5.5A2.5 2.5 0 0 1 12 7v13a3.5 3.5 0 0 0-3.5-2H4Zm16 0h-5.5A2.5 2.5 0 0 0 12 7m0 13a3.5 3.5 0 0 1 3.5-2H20V4.5" /></svg>
        <span>世界书架</span>
      </button>
    </div>
  </header>;
}

export function SegmentedSwitch<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: ReadonlyArray<{ value: T; label: string }>; onChange: (value: T) => void;
}) {
  return <div className={styles.segmented} role="group" aria-label={label}>
    {options.map(option => <button key={option.value} type="button" aria-pressed={option.value === value}
      onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}
