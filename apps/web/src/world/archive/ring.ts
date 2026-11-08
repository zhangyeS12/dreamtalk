import { BOOK_FACE, type ShelfFace } from "./bookDesign";

/** Where one book sits: translation in px, rotations in degrees. */
export type Pose = { px: number; py: number; pz: number; yaw: number; pitch: number; tilt: number };

export const ease = (t: number) => 1 - (1 - t) ** 3;

/** A book resting in the ring `dx` px from the centre: further books curve back and turn. */
export const restPose = (dx: number): Pose => ({
  px: dx, py: 0, pz: -(dx * dx) / 2600 - BOOK_FACE / 2,
  yaw: Math.max(-38, Math.min(38, -dx * 0.02)), pitch: 0, tilt: 0,
});

export const poseCss = (p: Pose) =>
  `translate3d(${p.px.toFixed(1)}px, ${p.py.toFixed(1)}px, ${p.pz.toFixed(1)}px) rotateZ(${p.tilt.toFixed(2)}deg) rotateX(${p.pitch.toFixed(2)}deg) rotateY(${p.yaw.toFixed(2)}deg)`;

/** Yaw that shows each face square-on. */
export const FACE_YAW: Record<ShelfFace, number> = { front: -90, spine: 0, back: 90, edge: 180 };

/** The face nearest the viewer for any yaw, including whole extra turns. */
export function faceFromYaw(yaw: number): ShelfFace {
  const angle = ((yaw % 360) + 360) % 360;
  const marks: Array<[ShelfFace, number]> = [["spine", 0], ["back", 90], ["edge", 180], ["front", 270], ["spine", 360]];
  return marks.reduce((best, item) => Math.abs(angle - item[1]) < Math.abs(angle - best[1]) ? item : best)[0];
}

/** The yaw for `face` closest to `current`, so turning never spins the long way round. */
export function yawToward(current: number, base: number): number {
  return base + 360 * Math.round((current - base) / 360);
}

/** One lap of slots: each book's centre from the lap start, and the lap length. */
export type RingLayout = { centres: Map<string, number>; lap: number };

export function ringLayout(books: ReadonlyArray<{ key: string }>, widthOf: (key: string) => number): RingLayout {
  const centres = new Map<string, number>();
  let lap = 0;
  for (const book of books) { const width = widthOf(book.key); centres.set(book.key, lap + width / 2); lap += width; }
  return { centres, lap };
}

/**
 * Signed distance from the viewport centre for one copy of a book, wrapped so
 * every copy stays within half a ring of the centre (the ring has `laps` laps).
 */
export function ringPosition(layout: RingLayout, key: string, lap: number, laps: number, offset: number): number {
  const length = layout.lap * laps;
  if (!length) return 0;
  const raw = lap * layout.lap + (layout.centres.get(key) ?? 0) - offset;
  return ((raw % length) + length * 1.5) % length - length / 2;
}

/** How many laps keep the ring wider than the viewport plus a margin on both sides. */
export function lapsFor(viewport: number, lapWidth: number): number {
  return Math.max(2, Math.ceil((viewport + 600) / Math.max(1, lapWidth)) + 1);
}
