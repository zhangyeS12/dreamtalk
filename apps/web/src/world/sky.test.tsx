import { expect, it } from "vitest";
import { contrast, formatClock, mixOklab, skyAt, SKY_INK, SKY_TEXT_BAND, worldClock } from "./sky";


it("reads the world clock without inventing time for logical worlds", () => {
  expect(worldClock("0")).toEqual({ day: 1n, minuteOfDay: 0 });
  expect(worldClock(String(60_000_000n * (1440n + 19n * 60n + 40n)))).toEqual({ day: 2n, minuteOfDay: 19 * 60 + 40 });
  expect(worldClock("-5")).toBeNull();
  expect(worldClock("not-a-number")).toBeNull();
  expect(formatClock({ day: 3n, minuteOfDay: 7 * 60 + 5 })).toBe("第 3 天 · 07:05");
});

it("keeps header text readable over the sky at every minute of the day", () => {
  for (let minute = 0; minute < 1440; minute += 5) {
    const sky = skyAt(minute);
    const behind = mixOklab(sky.zenith, sky.horizon, SKY_TEXT_BAND);
    expect(contrast(SKY_INK, behind), `minute ${minute}`).toBeGreaterThanOrEqual(4.5);
  }
});

it("moves the sun by day and the moon by night along a continuous arc", () => {
  expect(skyAt(12 * 60).body.kind).toBe("sun");
  expect(skyAt(12 * 60 + 22).body.altitude).toBeGreaterThan(0.99);
  expect(skyAt(0).body.kind).toBe("moon");
  expect(skyAt(6 * 60).body.kind).toBe("moon");
  expect(skyAt(6 * 60 + 30).body.altitude).toBeLessThan(0.1);
  expect(skyAt(0).stars).toBeGreaterThan(0.9);
  expect(skyAt(12 * 60).stars).toBe(0);
  const morning = skyAt(9 * 60).body.x, afternoon = skyAt(15 * 60).body.x;
  expect(afternoon).toBeGreaterThan(morning);
});

it("changes colour smoothly between neighbouring minutes", () => {
  const channels = (hex: string) => [1, 3, 5].map(at => Number.parseInt(hex.slice(at, at + 2), 16));
  for (let minute = 0; minute < 1440; minute++) {
    const a = channels(skyAt(minute).horizon), b = channels(skyAt(minute + 1).horizon);
    expect(Math.max(...a.map((value, index) => Math.abs(value - b[index]))), `minute ${minute}`).toBeLessThanOrEqual(6);
  }
});
