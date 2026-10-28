import { describe, expect, it } from "vitest";
import { STICKER_LIMIT, TEMPLATES, designFor, sameValue, spineStyle, withTemplate } from "./bookDesign";
import { faceFromYaw, lapsFor, restPose, ringLayout, ringPosition, yawToward } from "./ring";
import { characterTint, companyTints } from "../tint";

describe("ring", () => {
  const books = [{ key: "a" }, { key: "b" }, { key: "c" }];
  const widths: Record<string, number> = { a: 60, b: 80, c: 100 };
  const layout = ringLayout(books, key => widths[key]);

  it("lays one lap out by slot centres", () => {
    expect(layout.lap).toBe(240);
    expect([...layout.centres]).toEqual([["a", 30], ["b", 100], ["c", 190]]);
  });

  it("wraps every copy to within half a ring of the centre", () => {
    const laps = 3, length = layout.lap * laps;
    for (const offset of [-1000, -240, 0, 95, 240, 719, 5000]) for (const key of ["a", "b", "c"]) for (let lap = 0; lap < laps; lap++) {
      const dx = ringPosition(layout, key, lap, laps, offset);
      expect(dx).toBeGreaterThanOrEqual(-length / 2);
      expect(dx).toBeLessThan(length / 2);
    }
    // Scrolling by exactly one ring length lands every copy where it started.
    expect(ringPosition(layout, "b", 1, laps, 50 + length)).toBeCloseTo(ringPosition(layout, "b", 1, laps, 50));
    // The offset that centres a book puts it at 0.
    expect(ringPosition(layout, "b", 0, laps, 100)).toBe(0);
  });

  it("keeps enough laps to cover the viewport", () => {
    expect(lapsFor(0, 240)).toBeGreaterThanOrEqual(2);
    const laps = lapsFor(1920, 240);
    expect(laps * 240).toBeGreaterThan(1920 + 600);
    expect(lapsFor(1920, 0)).toBeGreaterThan(2);
  });

  it("curves books back and turns them toward the centre", () => {
    const centre = restPose(0), right = restPose(400), far = restPose(5000);
    expect(right.pz).toBeLessThan(centre.pz);
    expect(right.yaw).toBeLessThan(0);
    expect(restPose(-400).yaw).toBeGreaterThan(0);
    expect(Math.abs(far.yaw)).toBe(38);
  });

  it("names the face toward the viewer for any number of turns", () => {
    expect(faceFromYaw(-90)).toBe("front");
    expect(faceFromYaw(-68)).toBe("front");
    expect(faceFromYaw(0)).toBe("spine");
    expect(faceFromYaw(90)).toBe("back");
    expect(faceFromYaw(180)).toBe("edge");
    expect(faceFromYaw(359)).toBe("spine");
    expect(faceFromYaw(-90 + 720)).toBe("front");
    expect(faceFromYaw(90 - 1080)).toBe("back");
  });

  it("turns the short way to a face", () => {
    expect(yawToward(700, 90)).toBe(810);
    expect(yawToward(-10, 90)).toBe(90);
    expect(yawToward(-200, 90)).toBe(-270);
  });
});

describe("book design", () => {
  it("keeps old covers recognisable", () => {
    const text = designFor({ mode: "text", title: "旧标题", show_title: true }, "世界");
    expect(text.title.text).toBe("旧标题");
    expect(text.template).toBe("text");
    const image = designFor({ mode: "image", title: "隐藏", show_title: false }, "世界");
    expect(image.title.text).toBe("");
    expect(image.template).toBe("image");
    expect(designFor(undefined, "新世界").title.text).toBe("新世界");
  });

  it("keeps the user's stickers when switching templates", () => {
    const start = withTemplate(designFor(undefined, "书"), "comic");
    start.stickers.back.push({ kind: "image", ref: "d".repeat(64), x: 10, y: 10, w: 20, r: 0, opacity: 1 });
    start.stickers.front.push({ kind: "builtin", ref: "heart", x: 12, y: 80, w: 10, r: 5, opacity: 0.8 });
    const next = withTemplate(start, "dossier");
    expect(next.template).toBe("dossier");
    expect(next.title.text).toBe("书");
    expect(next.stickers.back).toEqual(start.stickers.back);
    // The comic star is swapped for the dossier's own stickers; the user's heart stays.
    expect(next.stickers.front.map(item => item.ref)).toEqual(["tape", "seal", "heart"]);
    // Switching back and forth never piles up template stickers.
    expect(withTemplate(withTemplate(next, "comic"), "dossier")).toEqual(next);
  });

  it("never exceeds the per-face sticker limit", () => {
    const full = designFor(undefined, "书");
    full.stickers.front = Array.from({ length: STICKER_LIMIT.front }, (_, index) => ({ kind: "builtin" as const, ref: "moon", x: index, y: 1, w: 5, r: 0, opacity: 1 }));
    const next = withTemplate(full, "dossier");
    expect(next.stickers.front).toHaveLength(STICKER_LIMIT.front);
    expect(next.stickers.front.every(item => item.ref === "moon")).toBe(true);
  });

  it("compares saved designs regardless of key order", () => {
    const design = TEMPLATES.classic.build("书");
    const reverse = (value: object) => Object.fromEntries(Object.entries(value).reverse());
    const reordered = { ...reverse(design), title: reverse(design.title), sky_window: reverse(design.sky_window) };
    expect(Object.keys(reordered)[0]).not.toBe(Object.keys(design)[0]);
    expect(sameValue(design, reordered)).toBe(true);
    expect(sameValue(design, { ...design, title: { ...design.title, size: 39 } })).toBe(false);
    expect(sameValue([1, 2], [2, 1])).toBe(false);
    expect(sameValue({ a: 1, b: undefined }, { a: 1 })).toBe(true);
  });

  it("chooses a stable spine treatment", () => {
    expect(spineStyle("晴川高中")).toBe(spineStyle("晴川高中"));
    expect(new Set(["a", "b", "c", "d", "e", "f", "g"].map(spineStyle)).size).toBeGreaterThan(1);
  });
});

describe("tints", () => {
  it("is stable per character and distinct within one group", () => {
    expect(characterTint("x")).toBe(characterTint("x"));
    const people = Array.from({ length: 12 }, (_, index) => `character-${index}`);
    const tints = companyTints(people);
    expect(new Set(tints.values()).size).toBe(12);
    expect(companyTints(["solo"]).get("solo")).toBe(characterTint("solo"));
  });
});
