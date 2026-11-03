/* Isolated, synthetic data adapter. It never constructs a Core connection,
   discovers credentials, calls a provider, or reads the product's storage keys. */
import type { ContentEditorDraft, CoreClient, CoverCrop, CoverImage, LibraryCardItem, LibraryCardPreview, WorldContentItem, WorldCover, WorldSettings } from "@dreamtalk/api-client";
import { defaultDesign, CARD_THEMES } from "../../world/cards/cardDesign";
import { defaultPack, type CharacterPack, type PackImages } from "../../world/cards/packs/packDesign";
import { TEMPLATES } from "../../world/archive/bookDesign";

const blankDraft = (name: string): ContentEditorDraft => ({ kind: "character", name, description: "一位等待与你相遇的旅人。", personality: "安静、敏锐，有自己的故事。", background: "", scenario: "", speech_guidance: "", first_message: "很高兴在这里遇见你。", creator_notes: "卡包交互预览中的演示角色。", tags: [], example_dialogue: [], entries: [] });
const listeners = new Set<() => void>();
const drafts = new Map<string, ContentEditorDraft>(), assets = new Map<string, string>(), assetInfo = new Map<string, CoverImage>();
const pending = new Map<string, { item: LibraryCardItem; draft: ContentEditorDraft }>();
const names = [["林见月", "档案修复师"], ["陆听澜", "星轨调查员"], ["白榆", "森林里的风信使"], ["沈砚", "夜航记录员"], ["温以宁", "旧城书店店主"], ["季遥", "远行的摄影师"], ["许星河", "列车上的观星者"], ["余青", "雨巷花匠"]];
const cards: LibraryCardItem[] = names.map(([name, role], index) => {
  const card: LibraryCardItem = { card_id: crypto.randomUUID(), name, revision: 1, design: null, world_ids: [] };
  const design = defaultDesign(card), theme = CARD_THEMES[index % CARD_THEMES.length];
  design.subtitle = role; design.front.color = theme.color; design.front.accent = theme.accent;
  design.front.layers = design.front.layers.map(item => ({ ...item, text: item.kind === "role" ? role : item.text, color: theme.accent }));
  design.back.color = theme.color; design.back.accent = theme.accent;
  card.design = design; drafts.set(card.card_id, blankDraft(name)); return card;
});
const packs = ["月下拾光", "雾港来信", "森林回廊", "远日档案", "雨夜茶馆", "无声群岛"].map((name, index) => {
  const pack = defaultPack(name, index); pack.revision = 1; pack.subtitle = ["一些故事，适合在月光下慢慢展开。", "潮汐送来信件，也送来新的相遇。", "穿过树影，有人正为你留着灯。", "把遥远的星，装进触手可及的日常。", "雨声很轻，故事很长。", "未曾说出口的话，也会找到岸。 "][index];
  pack.design.front.layers = pack.design.front.layers.map(item => item.kind === "role" ? { ...item, text: ["月光 · 书信 · 未完成的相遇", "雾气散去时，来信恰好抵达", "留一盏灯，等一个人", "每颗星都有自己的名字", "推门进来，茶还温着", "听见风，也听见你"][index] } : item);
  pack.cardIds = [cards[index % 8].card_id, cards[(index + 1) % 8].card_id, cards[(index + 3) % 8].card_id, cards[(index + 5) % 8].card_id]; return pack;
});
export const worlds: WorldSettings[] = ["月下列车", "雾港来信", "森林回廊", "远日档案", "雨夜茶馆", "无声群岛"].map(name => ({ world_id: crypto.randomUUID(), name, world_time: "2026-11-03T19:30:00Z", clock_state: "paused", time_scale: "1", runtime_state: "ready" }));
let snapshot = { cards, packs };
function emit() { snapshot = { cards: [...snapshot.cards], packs: [...snapshot.packs] }; listeners.forEach(listener => listener()); }
export const subscribe = (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); };
export const getSnapshot = () => snapshot;
export async function savePack(pack: CharacterPack) {
  if (!pack.name.trim()) throw new Error("请给卡包起一个名字。");
  if (new Set(pack.cardIds).size !== pack.cardIds.length || pack.cardIds.some(id => !snapshot.cards.some(card => card.card_id === id))) throw new Error("请重新核对装入的角色卡。");
  const saved = structuredClone(pack), index = snapshot.packs.findIndex(item => item.id === pack.id);
  saved.revision = Number(index < 0 ? 0 : snapshot.packs[index].revision) + 1;
  if (index < 0) snapshot.packs.push(saved); else snapshot.packs[index] = saved;
  emit();
}
async function loadImage(url: string) { const image = new Image(); image.src = url; await image.decode(); return image; }
async function keep(data: string): Promise<string> {
  const blob = await (await fetch(data)).blob(), bytes = await blob.arrayBuffer();
  const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(value => value.toString(16).padStart(2, "0")).join("");
  const image = await loadImage(data);
  assets.set(digest, data); assetInfo.set(digest, { digest, size: bytes.byteLength, width: image.naturalWidth, height: image.naturalHeight, media_type: blob.type }); return digest;
}
export const images: PackImages = {
  url: ref => assets.get(ref) ?? "",
  upload: async file => {
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error("请选择10 MiB以内的PNG、JPG或WebP图片。");
    const data = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error("图片未能读取，请重新选择。")); reader.readAsDataURL(file); });
    const image = await loadImage(data); if (image.naturalWidth * image.naturalHeight > 20_000_000 || Math.max(image.naturalWidth, image.naturalHeight) > 10000) throw new Error("图片尺寸过大，请选择较小的图片。");
    return keep(data);
  },
  crop: async (ref, crop, ratio) => {
    const source = await loadImage(images.url(ref)), rotated = document.createElement("canvas"), quarter = crop.rotation % 180 !== 0;
    rotated.width = quarter ? source.naturalHeight : source.naturalWidth; rotated.height = quarter ? source.naturalWidth : source.naturalHeight;
    const context = rotated.getContext("2d")!; context.translate(rotated.width / 2, rotated.height / 2); context.rotate(crop.rotation * Math.PI / 180); context.drawImage(source, -source.naturalWidth / 2, -source.naturalHeight / 2);
    const target = document.createElement("canvas"); target.width = ratio < 1 ? 900 : 1200; target.height = Math.round(target.width / ratio);
    target.getContext("2d")!.drawImage(rotated, crop.x / 100 * rotated.width, crop.y / 100 * rotated.height, crop.width / 100 * rotated.width, crop.height / 100 * rotated.height, 0, 0, target.width, target.height);
    return keep(target.toDataURL("image/webp", .9));
  },
};
function view(item: LibraryCardItem, draft = drafts.get(item.card_id)!): WorldContentItem {
  return { import_id: item.card_id, replaces_import_id: null, kind: "character", reviewed_hash: `preview-${item.revision}`, characters: [{ id: item.card_id, name: draft.name, description: draft.description, personality: draft.personality, background: draft.background, scenario: draft.scenario, speech_guidance: draft.speech_guidance, creator_notes: draft.creator_notes, tags: draft.tags, example_dialogue: draft.example_dialogue, authored_instructions: { character_card: { first_mes: draft.first_message } } }], lorebooks: [], entries: [], warnings: [] };
}
const scopes = new Map<string, CoreClient>();
export function previewClient(packId?: string): CoreClient {
  const key = packId ?? "all"; if (scopes.has(key)) return scopes.get(key)!;
  const api = {
    listProductWorlds: async () => worlds,
    listWorldCovers: async (): Promise<WorldCover[]> => worlds.map((world, index) => ({ world_id: world.world_id, mode: "text", title: world.name, show_title: true, faces: {}, revision: 1, design: { ...TEMPLATES.classic.build(world.name), case_color: CARD_THEMES[index % 5].color, title: { ...TEMPLATES.classic.build(world.name).title, color: CARD_THEMES[index % 5].accent } } })),
    worldContent: async () => [],
    selectedPlayer: async () => ({ player_id: null, availability: null, presence_revision: null }),
    libraryCards: async () => structuredClone(packId ? snapshot.cards.filter(card => snapshot.packs.find(pack => pack.id === packId)?.cardIds.includes(card.card_id)) : snapshot.cards),
    libraryCard: async (id: string) => ({ card: structuredClone(snapshot.cards.find(card => card.card_id === id)!), draft: structuredClone(drafts.get(id)!) }),
    saveLibraryDesign: async (card: LibraryCardItem, design: LibraryCardItem["design"]) => { const item = snapshot.cards.find(value => value.card_id === card.card_id)!; item.design = structuredClone(design); item.revision = Number(item.revision) + 1; emit(); return structuredClone(item); },
    libraryImage: async (_card: string, digest: string) => (await fetch(images.url(digest))).blob(),
    uploadLibraryImage: async (_card: string, file: File) => { const ref = await images.upload(file); return assetInfo.get(ref)!; },
    cropLibraryImage: async (_card: string, ref: string, crop: CoverCrop) => { const result = await images.crop(ref, crop, 1200 / 757); return assetInfo.get(result)!; },
    previewLibraryEditor: async (draft: ContentEditorDraft, editing?: LibraryCardItem): Promise<LibraryCardPreview> => {
      const item = editing ? { ...structuredClone(editing), name: draft.name, revision: Number(editing.revision) + 1 } : { card_id: crypto.randomUUID(), name: draft.name, revision: 1, design: null, world_ids: [] };
      const previewId = crypto.randomUUID(); pending.set(previewId, { item, draft }); return { preview_id: previewId, card_id: item.card_id, expected_revision: Number(item.revision) - 1, reviewed_hash: `preview-${item.revision}`, content: view(item, draft) };
    },
    previewLibraryChanges: async (card: LibraryCardItem, _original: ContentEditorDraft, draft: ContentEditorDraft) => api.previewLibraryEditor(draft, card),
    discardLibraryPreview: async (id: string) => { pending.delete(id); return { discarded: true }; },
    confirmLibraryCard: async (preview: LibraryCardPreview) => { const value = pending.get(preview.preview_id); if (!value) throw new Error("预览已过期。"); drafts.set(value.item.card_id, value.draft); const index = snapshot.cards.findIndex(item => item.card_id === value.item.card_id); if (index < 0) { snapshot.cards.push(value.item); const pack = snapshot.packs.find(item => item.id === packId); if (pack) pack.cardIds.push(value.item.card_id); } else snapshot.cards[index] = value.item; pending.delete(preview.preview_id); emit(); return structuredClone(value.item); },
    previewLibraryJoin: async (card: LibraryCardItem) => ({ card_id: card.card_id, source_revision: card.revision, content: view(card) }),
    confirmLibraryJoin: async (cardId: string, world: string) => { const card = snapshot.cards.find(item => item.card_id === cardId)!; card.world_ids = [...new Set([...card.world_ids, world])]; emit(); return view(card); },
    discardWorldContent: async () => ({ discarded: true }),
  };
  const client = new Proxy(api, { get(target, property) { if (property in target) return target[property as keyof typeof target]; return async () => { throw new Error("这个网页预览只演示卡包和卡面操作，完整文件导入／分享请使用正式项目入口。"); }; } }) as unknown as CoreClient;
  scopes.set(key, client); return client;
}
