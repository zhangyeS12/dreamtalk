import type { CoverCrop } from "@dreamtalk/api-client";
import { CoreRequestError } from "@dreamtalk/api-client";
import { CARD_THEMES, layer } from "../cardDesign";

export const PACK_RATIO = .7;
export type { CharacterPack, PackDesign, PackFaceDesign } from "@dreamtalk/api-client";
import type { CharacterPack, PackFaceDesign } from "@dreamtalk/api-client";
export type PackImages = { url: (ref: string) => string; upload: (file: File, owner?: string) => Promise<string>; crop: (ref: string, crop: CoverCrop, ratio: number, owner?: string) => Promise<string> };
export function defaultPack(name: string, index = 0): CharacterPack {
  const theme = CARD_THEMES[index % CARD_THEMES.length];
  const surface = (): PackFaceDesign => ({ color: theme.color, accent: theme.accent, material: index % 2 ? "metal" : "matte", frame: true, glyph: ["☾", "✦", "⌁", "❖", "✧"][index % 5], image: null, source: null, crop: null, imageOpacity: 82, layers: [] });
  return { id: crypto.randomUUID(), revision: 0, name, subtitle: "把下一次相遇，装进期待。", cardIds: [], design: { version: 1,
    front: { ...surface(), layers: [layer("name", name, 50, 65, 29, theme.accent), layer("role", "一封尚未拆开的故事", 50, 77, 10, theme.accent)] },
    back: { ...surface(), glyph: "✧", layers: [layer("text", "每一次相遇\n都值得被认真打开。", 50, 58, 17, theme.accent)] },
  } };
}
export const packThemes = CARD_THEMES;

export function packFailure(error: unknown): string {
  if (error instanceof CoreRequestError) {
    if (error.status === 409) return "卡包已被其他编辑更新。草稿保留，请关闭设计器并重新读取后核对。";
    if (error.status === 404) return "卡包、角色或图片暂不可用。请重新读取卡库；未保存的图片可重新上传。";
    if (error.status === 413 || error.status === 422) return "内容未能保存。请核对卡包信息，图片须为10 MiB以内的PNG、JPEG或WebP。";
    return "保存结果暂未确认。草稿保留，可再次保存核对同一次请求，或关闭后重新读取。";
  }
  return error instanceof Error ? error.message : "操作未完成，请重试。";
}
