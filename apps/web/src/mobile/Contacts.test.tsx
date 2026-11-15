import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { CoreClient, type SocialSnapshot, type WorldContentItem } from "@dreamtalk/api-client";
import { MobileContacts } from "./Contacts";
import { ContactRelations, ContactPlaces } from "./ContactLists";
import { WorldContacts } from "../WorldContent";
Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value() { this.setAttribute("open", ""); } });
Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value() { this.removeAttribute("open"); } });
beforeEach(() => {
  const context = { setTransform: vi.fn(), clearRect: vi.fn(), save: vi.fn(), restore: vi.fn(), scale: vi.fn(), translate: vi.fn(),
    rotate: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), stroke: vi.fn(), moveTo: vi.fn(), bezierCurveTo: vi.fn(),
    clip: vi.fn(), drawImage: vi.fn(), fillText: vi.fn(), createRadialGradient: () => ({ addColorStop: vi.fn() }) };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function card(id: string, name: string): WorldContentItem {
  return { import_id: id, replaces_import_id: null, kind: "character", reviewed_hash: "synthetic",
    characters: [{ id: id + "-definition", name, description: "合成资料", personality: "", background: "", scenario: "", speech_guidance: "", creator_notes: "", authored_instructions: {}, tags: [], example_dialogue: [] }],
    lorebooks: [], entries: [] };
}
function fixture() {
  const items = [card("new-a", "角色甲"), card("new-b", "角色乙"), card("new-c", "角色丙")];
  const social: SocialSnapshot = { factions: [{ faction_id: "faction", name: "合成阵营", parent_id: null }],
    characters: items.map((item, i) => ({ root_import_id: "root-" + i, current_import_id: item.import_id, character_id: "character-" + i, name: item.characters[0].name, avatar_digest: null })),
    memberships: [{ faction_id: "faction", root_import_id: "root-0" }, { faction_id: "faction", root_import_id: "root-1" }],
    connections: [{ first_root_import_id: "root-0", second_root_import_id: "root-1", faction_ids: ["faction"] }] };
  const api = {
    worldContent: vi.fn().mockImplementation(async () => items.slice()),
    socialSnapshot: vi.fn().mockImplementation(async () => structuredClone(social)),
    listActivityLocations: vi.fn().mockResolvedValue([]),
    listActivityCharacters: vi.fn().mockResolvedValue({ items: [], player_id: "player", has_more: false }),
    voiceCards: vi.fn().mockResolvedValue({ items: [], next_offset: null }),
    voiceBinding: vi.fn().mockResolvedValue({ card_id: null }),
    characterEvolution: vi.fn().mockResolvedValue([]),
    worldStyle: vi.fn().mockResolvedValue({ instructions: "", revision: 3 }),
    previewWorldStyle: vi.fn().mockImplementation(async (_w, instructions) => ({ instructions, expected_revision: 3, preview_hash: "preview" })),
    confirmWorldStyle: vi.fn().mockImplementation(async (_w, preview) => ({ instructions: preview.instructions, revision: 4 })),
    createFaction: vi.fn().mockImplementation(async (_w, name, parent) => { social.factions.push({ faction_id: "new-faction", name, parent_id: parent }); }),
    setFactionMember: vi.fn().mockImplementation(async (_w, factionId, root, enabled) => { if (!enabled) social.memberships = social.memberships.filter(member => member.faction_id !== factionId || member.root_import_id !== root); }),
    removeCharacterCard: vi.fn().mockImplementation(async (_w, id) => { items.splice(items.findIndex(item => item.import_id === id), 1); social.characters = social.characters.filter(person => person.current_import_id !== id); }),
    uploadCoverImage: vi.fn().mockResolvedValue({ digest: "background-digest" }),
    setCharacterChatBackground: vi.fn().mockResolvedValue({ common_background_digest: null, character_backgrounds: { "root-0": "background-digest" }, expressions: [] }),
  };
  const onOpenChat = vi.fn().mockResolvedValue(undefined), onDirtyChange = vi.fn(), onSaved = vi.fn(), onSelectedRootChange = vi.fn();
  const visuals = { visuals: { common_background_digest: null, character_backgrounds: {}, expressions: [] }, urls: {}, error: "", loading: false, refresh: vi.fn(), replace: vi.fn() };
  const client = api as unknown as CoreClient;
  return { api, client, social, items, visuals, onOpenChat, onDirtyChange, onSaved, onSelectedRootChange,
    props: { client, worldId: "world", refreshKey: 0, busy: false, onOpenChat, onSaved, onDirtyChange, visualState: visuals, onSelectedRootChange } };
}
async function choose(name = "角色甲") { fireEvent.click(await screen.findByRole("button", { name: name + "查看角色资料与阵营" })); }

test("mobile directory searches, opens a dossier and uses the latest import for chat", async () => {
  const f = fixture(); render(<MobileContacts {...f.props} />);
  await screen.findByRole("button", { name: "角色甲查看角色资料与阵营" });
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索角色名称" }), { target: { value: "乙" } });
  expect(screen.queryByRole("button", { name: "角色甲查看角色资料与阵营" })).toBeNull();
  await choose("角色乙");
  expect(f.onOpenChat).not.toHaveBeenCalled();
  await waitFor(() => expect(f.onSelectedRootChange).toHaveBeenLastCalledWith("root-1"));
  fireEvent.click(screen.getByRole("button", { name: /打开会话/ }));
  await waitFor(() => expect(f.onOpenChat).toHaveBeenCalledWith("new-b"));
  fireEvent.click(screen.getByRole("button", { name: "返回通讯录" }));
  expect(screen.getByRole("searchbox", { name: "搜索角色名称" })).toHaveProperty("value", "乙");
});
test("relationship list contains only confirmed links and opens the chosen profile", async () => {
  const f = fixture(); render(<MobileContacts {...f.props} />);
  await screen.findByRole("button", { name: "角色甲查看角色资料与阵营" });
  fireEvent.click(screen.getByRole("button", { name: "人物关系" }));
  fireEvent.change(screen.getByLabelText("搜索关系图角色"), { target: { value: "角色甲" } });
  fireEvent.click(screen.getByRole("button", { name: "聚焦角色甲" }));
  fireEvent.click(screen.getByRole("button", { name: "列表" }));
  const links = screen.getByRole("list");
  expect(within(links).getByText("角色乙")).toBeTruthy();
  expect(within(links).queryByText("角色丙")).toBeNull();
  expect(document.querySelector("canvas")).toBeNull();
  fireEvent.click(within(links).getByRole("button", { name: "查看角色乙资料" }));
  expect(await screen.findByRole("heading", { name: "角色乙" })).toBeTruthy();
});
test("faction draft cancellation is guarded and creation reuses the existing API", async () => {
  const f = fixture(); render(<MobileContacts {...f.props} />);
  await screen.findByRole("button", { name: "角色甲查看角色资料与阵营" });
  fireEvent.click(screen.getByRole("button", { name: "编辑阵营" }));
  fireEvent.change(screen.getByLabelText("新阵营名称"), { target: { value: "新阵营" } });
  await waitFor(() => expect(f.onDirtyChange).toHaveBeenLastCalledWith(true));
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  fireEvent.click(screen.getByRole("button", { name: "人物关系" }));
  expect(screen.getByLabelText("新阵营名称")).toHaveProperty("value", "新阵营");
  expect(confirm).toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "创建阵营" }));
  await waitFor(() => expect(f.api.createFaction).toHaveBeenCalledWith("world", "新阵营", null));
  expect(await screen.findByText("新阵营", { selector: "strong" })).toBeTruthy();
});
test("world style preserves preview and explicit confirm before persistence", async () => {
  const f = fixture(); render(<MobileContacts {...f.props} />);
  fireEvent.click(screen.getByRole("button", { name: "世界风格" }));
  const input = await screen.findByLabelText("当前世界的写作约定");
  fireEvent.change(input, { target: { value: "合成风格" } });
  fireEvent.click(screen.getByRole("button", { name: "预览修改" }));
  expect(await screen.findByRole("button", { name: "确认并保存" })).toBeTruthy();
  expect(f.api.previewWorldStyle).toHaveBeenCalledWith("world", "合成风格", 3);
  expect(f.api.confirmWorldStyle).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认并保存" }));
  await screen.findByText("已保存。从下一次角色发言起采用此风格。");
  expect(f.api.confirmWorldStyle).toHaveBeenCalledTimes(1);
});
test("compact profile uploads background by stable root and leaves expressions unmounted", async () => {
  const f = fixture(); render(<MobileContacts {...f.props} />); await choose();
  expect(screen.queryByText("表情类型")).toBeNull();
  const file = new File(["synthetic"], "background.png", { type: "image/png" });
  fireEvent.change(screen.getByLabelText("上传角色专属背景"), { target: { files: [file] } });
  await waitFor(() => expect(f.api.setCharacterChatBackground).toHaveBeenCalledWith("world", "root-0", "background-digest"));
  expect(f.visuals.replace).toHaveBeenCalledTimes(1);
});
test("removing a card clears stale profile and notifies workspace without deleting history", async () => {
  const f = fixture(); render(<MobileContacts {...f.props} />); await choose();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "删除角色卡" }));
  await waitFor(() => expect(f.api.removeCharacterCard).toHaveBeenCalledWith("world", "new-a"));
  await waitFor(() => expect(f.onSelectedRootChange).toHaveBeenLastCalledWith(null));
  expect(f.onSaved).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("heading", { name: "角色甲" })).toBeNull();
});
test("hidden directory does not read content, locations or avatars", () => {
  const f = fixture();
  render(<WorldContacts compact client={f.client} worldId="world" visible={false} canOpenChat openingChat={false} onOpenChat={f.onOpenChat} onIdentity={vi.fn()} onSettings={vi.fn()} />);
  expect(f.api.worldContent).not.toHaveBeenCalled(); expect(f.api.listActivityLocations).not.toHaveBeenCalled();
});
test("relationships paginate without inventing links for unconnected characters", () => {
  const social: SocialSnapshot = { factions: [], memberships: [], connections: [], characters: [] };
  for (let i = 0; i < 66; i++) {
    social.characters.push({ root_import_id: "r" + i, current_import_id: "i" + i, character_id: "c" + i, name: "合成角色" + i, avatar_digest: null });
    if (i > 0 && i < 65) social.connections.push({ first_root_import_id: "r0", second_root_import_id: "r" + i, faction_ids: [] });
  }
  render(<ContactRelations social={social} selected="r0" onChoose={vi.fn()} onProfile={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "个人关系" }));
  fireEvent.click(screen.getByRole("button", { name: "列表" }));
  expect(screen.getByText("64 位已确认相识符合筛选")).toBeTruthy();
  expect(screen.getAllByRole("listitem")).toHaveLength(30);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(within(screen.getByRole("list")).queryByText("合成角色1")).toBeNull();
  fireEvent.change(screen.getByLabelText("搜索关系图角色"), { target: { value: "合成角色65" } });
  expect(screen.getByText("没有匹配的相识角色。")).toBeTruthy();
});
test("missing position data never pretends an uninitialized character is present", () => {
  const f = fixture();
  render(<ContactPlaces locations={[]} directory={null} social={f.social} onSelect={vi.fn()} onEdit={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "列表" }));
  expect(screen.getAllByText("位置尚未读取")).toHaveLength(3);
  expect(screen.queryByText("尚未设置初始地点")).toBeNull();
});
test.each([{ label: "否，保留相识", cut: false }, { label: "是，切断联系", cut: true }])("leaving a faction requires explicit choice: $label", async ({ label, cut }) => {
  const f = fixture(); render(<MobileContacts {...f.props} />);
  await screen.findByRole("button", { name: "角色甲查看角色资料与阵营" });
  fireEvent.click(screen.getByRole("button", { name: "编辑阵营" }));
  fireEvent.change(screen.getByLabelText("编辑哪位角色的归属"), { target: { value: "root-0" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "角色甲属于该阵营" }));
  expect(f.api.setFactionMember).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: label }));
  await waitFor(() => expect(f.api.setFactionMember).toHaveBeenCalledWith("world", "faction", "root-0", false, cut));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});
