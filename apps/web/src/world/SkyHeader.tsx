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

export function skyBody(world: WorldSettings | undefined): "sun" | "moon" | null {
  const clock = world ? worldClock(world.world_time) : null;
  return clock ? skyAt(clock.minuteOfDay).body.kind : null;
}

/** The world's name written into its own sky, with the real clock beneath it. */
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
  return <header className={styles.top}>
    <img className={styles.mark} src="/brand/dreamtalk-logo.png" alt="dreamtalk" width="52" height="46" />
    <div className={styles.title}>
      <strong className={styles.name}>{world?.name ?? "正在读取世界…"}</strong>
      {world && <p className={styles.clock}>
        {clock ? <><span>{formatClock(clock)}</span><span className={styles.phase}>{sky?.phase}</span></> : <span>逻辑时间 {world.world_time} 微秒</span>}
        {paused && <span className={styles.state}>已暂停</span>}
        {degraded && <span className={styles.state} data-tone="danger">运行异常</span>}
      </p>}
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
