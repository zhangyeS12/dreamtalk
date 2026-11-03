import type { CardDesign, CardFaceDesign, CardLayer, LibraryCardItem } from "@dreamtalk/api-client";

export type CardSide = "front" | "back";
export const CARD_RATIO = 1.5858;
export const STICKERS = ["☾", "✦", "✧", "❖", "✿", "⌁"];
export const CARD_THEMES = [
  { name: "月夜蓝", color: "#253e57", accent: "#f0d5a0" },
  { name: "暮色紫", color: "#49354e", accent: "#f3d6ba" },
  { name: "松林绿", color: "#25463e", accent: "#e8dbb4" },
  { name: "赤陶红", color: "#673b3c", accent: "#f4d9b6" },
  { name: "银墨黑", color: "#252c3e", accent: "#d2dfed" },
];
export const layer = (kind: CardLayer["kind"], text: string, x: number, y: number, size: number, color = "#f0d5a0"): CardLayer => ({ id: crypto.randomUUID(), anchor: "center", kind, text, x, y, size, color, rotation: 0, opacity: 100 });
export function defaultDesign(card: Pick<LibraryCardItem, "name" | "design">): CardDesign {
  if (card.design) return structuredClone(card.design);
  const name = Array.from(card.name).slice(0, 60).join("");
  const base: CardFaceDesign = { layout: "portrait", color: CARD_THEMES[0].color, accent: CARD_THEMES[0].accent, material: "matte", frame: true, image_digest: null, source_digest: null, crop: null, image_opacity: 100, layers: [] };
  return { version: 1, display_name: name, subtitle: "角色档案", glyph: Array.from(name).at(-1) ?? "✦",
    front: { ...base, layers: [layer("name", name, 28, 66, 31), { ...layer("role", "角色档案", 28, 81, 12), opacity: 88 }] },
    back: { ...base, layout: "notes", layers: [layer("text", "每一次相遇\n都从一页空白开始。", 50, 53, 22)] } };
}
export function symmetricFace(face: CardFaceDesign): CardFaceDesign {
  return { ...structuredClone(face), layers: face.layers.map(item => ({ ...item, id: crypto.randomUUID() })) };
}
export function restPose(id: string) {
  let hash = 5381;
  for (const char of id) hash = ((hash * 33) ^ char.charCodeAt(0)) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 16), 0x45d9f3b);
  hash = Math.imul(hash ^ (hash >>> 16), 0x45d9f3b);
  hash = (hash ^ (hash >>> 16)) >>> 0;
  return { roll: hash % 111 - 55, yaw: (hash >>> 5) % 67 - 33, pitch: (hash >>> 11) % 41 - 20, y: (hash >>> 17) % 75 - 37, phase: (hash % 360) / 57.3 };
}
export const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
