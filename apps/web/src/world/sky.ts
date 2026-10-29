/**
 * The world sky: a pure mapping from the authoritative world clock to colours
 * and a sun or moon position. It reads only `world_time`; it never invents
 * weather, events or activity.
 */

export type WorldClock = { day: bigint; minuteOfDay: number };
export type SkyPhase = "深夜" | "黎明" | "清晨" | "白昼" | "黄昏" | "入夜";
export type Sky = {
  zenith: string;
  horizon: string;
  /** Sun or moon. `x` runs 0→1 across its arc, `altitude` 0 (horizon) → 1 (top). */
  body: { kind: "sun" | "moon"; x: number; altitude: number };
  /** 0 by day, 1 in deep night. */
  stars: number;
  phase: SkyPhase;
};

const MINUTES_PER_DAY = 1440;

/** World time is microseconds since the world began; negative values are logical, not a clock. */
export function worldClock(raw: string): WorldClock | null {
  let micros: bigint;
  try { micros = BigInt(raw); } catch { return null; }
  if (micros < 0n) return null;
  const minutes = micros / 60_000_000n;
  return { day: minutes / 1440n + 1n, minuteOfDay: Number(minutes % 1440n) };
}

export function formatClock(clock: WorldClock): string {
  const hour = Math.floor(clock.minuteOfDay / 60), minute = clock.minuteOfDay % 60;
  return `第 ${clock.day} 天 · ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

// Hour → [zenith, horizon]. Tuned from the logo: indigo night, rose dawn,
// silver-blue day, gold dusk. The cycle wraps at 24.
const KEYFRAMES: ReadonlyArray<readonly [number, string, string]> = [
  [0, "#0c102e", "#1f2652"],
  [4.5, "#11163f", "#30315f"],
  [5.75, "#1f2862", "#7d6290"],
  [6.75, "#283a7a", "#d99a8c"],
  [8.5, "#22418a", "#9db8e2"],
  [15.5, "#22428b", "#a3bce4"],
  [17.5, "#26306f", "#e3a873"],
  [18.6, "#22276a", "#d27f6a"],
  [19.75, "#171c4c", "#4b3b6c"],
  [21.5, "#0e1336", "#242b5a"],
  [24, "#0c102e", "#1f2652"],
];

const SUNRISE = 6.25, SUNSET = 18.5;

export function skyAt(minuteOfDay: number): Sky {
  const hour = (((minuteOfDay % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY) / 60;
  let index = KEYFRAMES.findIndex(([at]) => at > hour) - 1;
  if (index < 0) index = KEYFRAMES.length - 2;
  const [fromAt, fromZenith, fromHorizon] = KEYFRAMES[index];
  const [toAt, toZenith, toHorizon] = KEYFRAMES[index + 1];
  const t = smooth((hour - fromAt) / (toAt - fromAt));
  const zenith = mixOklab(fromZenith, toZenith, t);
  const horizon = mixOklab(fromHorizon, toHorizon, t);

  const day = hour >= SUNRISE && hour < SUNSET;
  const span = day ? SUNSET - SUNRISE : 24 - (SUNSET - SUNRISE);
  const since = day ? hour - SUNRISE : (hour - SUNSET + 24) % 24;
  const x = since / span;
  const altitude = Math.sin(Math.PI * x);
  // Stars fade with the sky's own brightness so dawn and dusk stay consistent.
  const light = luminance(mixOklab(zenith, horizon, 0.5));
  const stars = clamp((0.09 - light) / 0.07, 0, 1);
  return {
    zenith, horizon,
    body: { kind: day ? "sun" : "moon", x, altitude },
    stars,
    phase: phaseOf(hour),
  };
}

/** Header text is always moon-white; the keyframes keep the text band dark enough for it. */
export const SKY_INK = "#eceef7";
/** Where header text sits inside the zenith→horizon gradient (matches the CSS stop). */
export const SKY_TEXT_BAND = 0.3;

function phaseOf(hour: number): SkyPhase {
  if (hour < 4.5) return "深夜";
  if (hour < 6.75) return "黎明";
  if (hour < 8.5) return "清晨";
  if (hour < 17) return "白昼";
  if (hour < 19.25) return "黄昏";
  if (hour < 22.5) return "入夜";
  return "深夜";
}

const smooth = (t: number) => t * t * (3 - 2 * t);
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

type Rgb = [number, number, number];
const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toGamma = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function parseHex(hex: string): Rgb {
  const value = Number.parseInt(hex.slice(1), 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
}

function toHex([r, g, b]: Rgb): string {
  return "#" + [r, g, b].map(c => Math.round(clamp(c, 0, 1) * 255).toString(16).padStart(2, "0")).join("");
}

function toOklab(hex: string): Rgb {
  const [r, g, b] = parseHex(hex).map(toLinear) as Rgb;
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function fromOklab([L, a, b]: Rgb): string {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return toHex([
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map(toGamma) as Rgb);
}

export function mixOklab(from: string, to: string, t: number): string {
  const a = toOklab(from), b = toOklab(to);
  return fromOklab([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]);
}

/** WCAG relative luminance. */
export function luminance(hex: string): number {
  const [r, g, b] = parseHex(hex).map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

/** The sky over a world right now, or null when its clock is not a real time. */
export function skyOf(world: { world_time: string } | undefined): Sky | null {
  const clock = world ? worldClock(world.world_time) : null;
  return clock ? skyAt(clock.minuteOfDay) : null;
}

/** A sky as the registered `--dt-sky-*` custom properties (see tokens.css). */
export function skyVars(sky: Sky): Record<string, string> {
  return {
    "--dt-sky-zenith": sky.zenith,
    "--dt-sky-horizon": sky.horizon,
    "--dt-sky-x": sky.body.x.toFixed(4),
    "--dt-sky-altitude": sky.body.altitude.toFixed(4),
    "--dt-stars": sky.stars.toFixed(3),
  };
}

export type Star = { x: number; y: number; size: number; delay: number };
/** A deterministic star field (percent positions) so the night never reshuffles between renders. */
export function starField(count: number): Star[] {
  return Array.from({ length: count }, (_, index) => {
    const a = Math.sin(index * 12.9898) * 43758.5453, b = Math.sin(index * 78.233) * 12345.678;
    const x = a - Math.floor(a), y = b - Math.floor(b);
    return { x: x * 100, y: y * 70, size: 0.4 + ((x + y) % 1) * 0.9, delay: -(index % 9) * 0.6 };
  });
}
