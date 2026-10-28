import type { BookDesign, BookDesignSticker, WorldCover } from "@dreamtalk/api-client";
import { stableHash } from "../hash";

/** Book proportions follow the saved cover images (196:286 faces, 42:286 spine). */
export const BOOK_HEIGHT = 540;
export const BOOK_FACE = 372;
export const THICKNESS: Record<BookDesign["thickness"], number> = { thin: 54, normal: 74, thick: 96 };
export const BLANK_THICKNESS = 70;
export type DesignFace = "front" | "spine" | "back";
/** Every face a reader can turn toward; the fore-edge has nothing to design. */
export type ShelfFace = DesignFace | "edge";
export const FACE_LABELS: Record<DesignFace | "edge", string> = { front: "正面", spine: "书脊", back: "背面", edge: "书口" };

/** System fonts only (no bundled font files). */
export const FONTS: Record<BookDesign["title"]["font"], { label: string; stack: string }> = {
  yahei: { label: "微软雅黑", stack: "'Microsoft YaHei UI', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif" },
  hei: { label: "黑体", stack: "'SimHei', 'Noto Sans CJK SC', sans-serif" },
  song: { label: "宋体", stack: "'SimSun', 'Noto Serif CJK SC', serif" },
  kai: { label: "楷体", stack: "'KaiTi', 'STKaiti', 'Noto Serif CJK SC', serif" },
  fangsong: { label: "仿宋", stack: "'FangSong', 'STFangsong', 'Noto Serif CJK SC', serif" },
};
export const MATERIALS: Array<[BookDesign["material"], string]> = [["paper", "纸面"], ["cloth", "布面"], ["leather", "皮革"], ["gloss", "亮面"], ["holo", "镭射"]];
export const CASE_COLORS = ["#111218", "#2b2f45", "#3d4a5c", "#5b2333", "#1f4037", "#b8875a", "#e9e4d8", "#f4c7d0"];
export const INK_COLORS = ["#ffffff", "#f3d27d", "#1b1d2a", "#e24a4a", "#94d0ff"];

const svg = (body: string) => `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">${body}</svg>`)}`;
const sunRays = Array.from({ length: 12 }, (_, i) => {
  const a = i * Math.PI / 6;
  return `<line x1="${(50 + 30 * Math.cos(a)).toFixed(1)}" y1="${(50 + 30 * Math.sin(a)).toFixed(1)}" x2="${(50 + 44 * Math.cos(a)).toFixed(1)}" y2="${(50 + 44 * Math.sin(a)).toFixed(1)}"/>`;
}).join("");

/** Built-in stickers are bundled vector art; user stickers are this world's uploaded images. */
export const BUILTIN_STICKERS: Record<string, { label: string; src: string }> = {
  star: { label: "四芒星", src: svg('<path d="M50 4 58 42 96 50 58 58 50 96 42 58 4 50 42 42Z" fill="#f3d27d"/>') },
  moon: { label: "新月", src: svg('<path d="M64 10a42 42 0 1 0 26 74A36 36 0 1 1 64 10Z" fill="#eef1fb"/>') },
  sun: { label: "太阳", src: svg(`<circle cx="50" cy="50" r="22" fill="#ffcf6b"/><g stroke="#ffcf6b" stroke-width="6" stroke-linecap="round">${sunRays}</g>`) },
  seal: { label: "印章", src: svg('<circle cx="50" cy="50" r="42" fill="none" stroke="#e24a4a" stroke-width="6"/><circle cx="50" cy="50" r="33" fill="none" stroke="#e24a4a" stroke-width="2"/><text x="50" y="60" font-size="28" font-weight="900" text-anchor="middle" fill="#e24a4a" font-family="SimHei,sans-serif">限定</text>') },
  ribbon: { label: "丝带", src: svg('<path d="M4 34h92l-10 16 10 16H4l10-16Z" fill="#c8324a"/><path d="M14 40h72v20H14Z" fill="#e34c63"/>') },
  film: { label: "胶片", src: svg('<rect x="6" y="22" width="88" height="56" rx="4" fill="#15151c"/>' + [14, 32, 50, 68, 86].map(x => `<rect x="${x - 4}" y="26" width="8" height="6" fill="#ddd"/><rect x="${x - 4}" y="68" width="8" height="6" fill="#ddd"/>`).join("") + '<rect x="16" y="36" width="68" height="28" fill="#6b5b95"/>') },
  sakura: { label: "樱花", src: svg([0, 72, 144, 216, 288].map(a => `<ellipse cx="50" cy="28" rx="13" ry="22" fill="#ffc6d9" transform="rotate(${a} 50 50)"/>`).join("") + '<circle cx="50" cy="50" r="8" fill="#ff8fb1"/>') },
  tape: { label: "胶带", src: svg('<rect x="2" y="36" width="96" height="28" fill="#f2e48a" opacity=".92" transform="rotate(-6 50 50)"/><text x="50" y="56" font-size="13" font-weight="800" text-anchor="middle" fill="#3a3210" transform="rotate(-6 50 50)" font-family="sans-serif">TOP SECRET</text>') },
  heart: { label: "爱心", src: svg('<path d="M50 86 14 52a20 20 0 0 1 36-26 20 20 0 0 1 36 26Z" fill="#ff7a8a"/>') },
};

const sticker = (ref: string, x: number, y: number, w: number, r = 0): BookDesignSticker => ({ kind: "builtin", ref, x, y, w, r, opacity: 1 });
const empty = () => ({ front: [] as BookDesignSticker[], spine: [] as BookDesignSticker[], back: [] as BookDesignSticker[] });

export const TEMPLATES: Record<string, { label: string; build: (title: string) => BookDesign }> = {
  vhs: { label: "录像带盒", build: text => ({ version: 1, template: "vhs", material: "gloss", case_color: "#111218", edge: "paper", thickness: "normal", wrap: false, brand: true,
    title: { text, font: "yahei", color: "#ffffff", size: 36, vertical: false, x: 50, y: 86 }, sky_window: { on: false, x: 76, y: 16, w: 30, h: 16 }, stickers: empty() }) },
  comic: { label: "漫画单行本", build: text => ({ version: 1, template: "comic", material: "paper", case_color: "#e9e4d8", edge: "paper", thickness: "thin", wrap: true, brand: true,
    title: { text, font: "hei", color: "#ffffff", size: 46, vertical: false, x: 50, y: 20 }, sky_window: { on: false, x: 76, y: 32, w: 30, h: 16 }, stickers: { ...empty(), front: [sticker("star", 82, 34, 14)] } }) },
  classic: { label: "线装古籍", build: text => ({ version: 1, template: "classic", material: "cloth", case_color: "#3d4a5c", edge: "paper", thickness: "thick", wrap: false, brand: false,
    title: { text, font: "song", color: "#f1e6c8", size: 38, vertical: true, x: 76, y: 34 }, sky_window: { on: true, x: 34, y: 30, w: 34, h: 22 }, stickers: { ...empty(), front: [sticker("seal", 30, 82, 22, -8)] } }) },
  dossier: { label: "档案夹", build: text => ({ version: 1, template: "dossier", material: "paper", case_color: "#b8875a", edge: "gilt", thickness: "normal", wrap: false, brand: true,
    title: { text, font: "hei", color: "#2b1d10", size: 40, vertical: false, x: 50, y: 46 }, sky_window: { on: false, x: 50, y: 70, w: 40, h: 16 }, stickers: { ...empty(), front: [sticker("tape", 50, 18, 60), sticker("seal", 74, 72, 26, 12)] } }) },
};

/**
 * Old covers (title + optional images) open as a design that looks like what
 * the user saved: their image stays the front, their title stays the title.
 */
export function designFor(cover: Pick<WorldCover, "mode" | "title" | "show_title" | "design"> | undefined, worldName: string): BookDesign {
  if (cover?.design) return cover.design;
  const imaged = cover?.mode === "image";
  const text = cover ? (imaged ? (cover.show_title ? cover.title : "") : cover.title || worldName) : worldName;
  const base = TEMPLATES.vhs.build(text);
  return imaged ? { ...base, template: "image", material: "paper" } : { ...base, template: "text", case_color: "#2b2f45", material: "paper", title: { ...base.title, y: 42, size: 34 } };
}

export function stickerSource(item: BookDesignSticker, uploads: Record<string, string>): string | undefined {
  return item.kind === "builtin" ? BUILTIN_STICKERS[item.ref]?.src : uploads[item.ref];
}

/** A stable spine treatment chosen from the world's name, never random. */
export function spineStyle(name: string): 0 | 1 | 2 {
  return (stableHash(name) % 3) as 0 | 1 | 2;
}

export const cloneDesign = (design: BookDesign): BookDesign => JSON.parse(JSON.stringify(design)) as BookDesign;

/** Per-face sticker limits; the Core rejects more (adapters/http/world_covers.py). */
export const STICKER_LIMIT: Record<DesignFace, number> = { front: 24, spine: 12, back: 24 };
const DESIGN_FACES: DesignFace[] = ["front", "spine", "back"];
const stickerId = (face: DesignFace, item: BookDesignSticker) => [face, item.kind, item.ref, item.x, item.y, item.w, item.r, item.opacity].join("|");
const TEMPLATE_STICKERS = new Set(Object.values(TEMPLATES).flatMap(template => {
  const built = template.build("");
  return DESIGN_FACES.flatMap(face => built.stickers[face].map(item => stickerId(face, item)));
}));

/**
 * Restyle a book with a template but keep what the user placed: the title text
 * and every sticker the template did not put there itself. Template stickers
 * from an earlier template are swapped out, so switching templates never piles them up.
 */
export function withTemplate(current: BookDesign, key: string): BookDesign {
  const next = TEMPLATES[key].build(current.title.text);
  for (const face of DESIGN_FACES) {
    const own = current.stickers[face].filter(item => !TEMPLATE_STICKERS.has(stickerId(face, item)));
    const room = Math.max(0, STICKER_LIMIT[face] - own.length);
    next.stickers[face] = [...next.stickers[face].slice(0, room), ...own];
  }
  return next;
}

/** Deep equality that ignores object key order (a saved design may come back reordered). */
export function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((item, index) => sameValue(item, b[index]));
  const left = a as Record<string, unknown>, right = b as Record<string, unknown>;
  const keys = Object.keys(left).filter(key => left[key] !== undefined), other = Object.keys(right).filter(key => right[key] !== undefined);
  return keys.length === other.length && keys.every(key => sameValue(left[key], right[key]));
}
