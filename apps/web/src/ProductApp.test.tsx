import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, type ChatConversation, type GroupChatConversation, type WorldContentItem, type WorldSettings } from "@dreamtalk/api-client";
import { withChatReads } from "./testClient";
import { ProductApp } from "./ProductApp";

// jsdom has no layout engine. Exercise the real archive/navigation workflow
// through an accessible shelf double; the actual carousel is checked in browser.
vi.mock("./WorldShelf", async () => {
  const { useEffect } = await import("react");
  return {
    worldShelfBlankCount: (count: number) => Math.max(12, count + 1) - count,
    WorldShelf: ({ worlds, selectedKey, onSelect, onCreate, onSettled }: {
      worlds: WorldSettings[]; selectedKey: string | null; onSelect: (world: string) => void;
      onCreate: (index: number) => void; onSettled: (key: string | null) => void;
    }) => {
      useEffect(() => onSettled(selectedKey), [selectedKey, onSettled]);
      return <div>{worlds.map(world => <button key={world.world_id} aria-pressed={selectedKey === `world:${world.world_id}`} onClick={() => onSelect(world.world_id)}>预览世界：{world.name}</button>)}<button onClick={() => onCreate(0)}>创建或导入一个新世界，空白书 1</button></div>;
    },
  };
});

afterEach(() => { cleanup(); window.localStorage.removeItem("livingworld.lastWorldId"); });

const worldA: WorldSettings = { world_id: "world-a", name: "世界甲", world_time: "0", clock_state: "running", time_scale: "1", runtime_state: "ready" };
const worldB: WorldSettings = { world_id: "world-b", name: "世界乙", world_time: "60000000", clock_state: "paused", time_scale: "2", runtime_state: "paused" };
const cardA: WorldContentItem = {
  import_id: "card-a", replaces_import_id: null, kind: "character", reviewed_hash: "hash",
  characters: [{ id: "character-a", name: "角色甲", description: "", personality: "", background: "", scenario: "", speech_guidance: "", creator_notes: "", tags: [], example_dialogue: [], authored_instructions: {} }],
  lorebooks: [], entries: [],
};
const chatA: ChatConversation = { conversation_id: "chat-a", player_id: "player-a", character_id: "character-a", root_import_id: "card-a", character_name: "角色甲", kind: "direct" };
const cardB: WorldContentItem = { ...cardA, import_id: "card-b", characters: [{ ...cardA.characters[0], id: "character-b", name: "角色乙" }] };
const groupA: GroupChatConversation = { conversation_id: "group-a", player_id: "player-a", kind: "group", participants: [
  { character_id: "character-a", root_import_id: "card-a", character_name: "角色甲" },
  { character_id: "character-b", root_import_id: "card-b", character_name: "角色乙" },
] };

async function enterBook(world = "world-a") {
  const label = world === "world-b" ? "预览世界：世界乙" : "预览世界：世界甲";
  const book = await screen.findByRole("button", { name: label });
  if (book.getAttribute("aria-pressed") !== "true") fireEvent.click(book);
  fireEvent.click(await screen.findByRole("button", { name: "进入世界 →" }));
  await screen.findByRole("navigation", { name: "主导航" });
  fireEvent.click(screen.getByRole("button", { name: "聊天" }));
}
async function switchBook(world: string) {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "世界书架" }));
  await enterBook(world);
}
async function renderProduct(client: CoreClient, enter = true) {
  const defaults = {
    avatarDigests: vi.fn().mockResolvedValue([]),
    groupConversations: vi.fn().mockResolvedValue([]), conversations: vi.fn().mockResolvedValue([]),
    health: vi.fn().mockResolvedValue({ llm_status: "unconfigured" }), listWorldCovers: vi.fn().mockResolvedValue([]),
    mediaSettings: vi.fn().mockResolvedValue({ enabled: false, frequency: 4, unlimited_stickers: false, online_enabled: false, auto_caption: false, caption_route: "ollama", caption_endpoint: "http://127.0.0.1:11434", caption_model: "", secret_ref: null, remote_caption_consent: false, daily_caption_limit: 10, caption_output_tokens: 256 }),
    mediaUsage: vi.fn().mockResolvedValue({ caption_calls: 0 }),
    speechSettings: vi.fn().mockResolvedValue({ revision: 0, settings: { enabled: false, provider: "local", local_url: "http://127.0.0.1:7861", secret_ref: null, max_characters: 10000, daily_calls: 0, skip_actions: true, consent_remote: false, consent_paid: false } }),
    speechPreviews: vi.fn().mockResolvedValue({ items: [] }),
    profile: vi.fn().mockResolvedValue({ name: "", description: "", revision: 0 }),
    playerPersona: vi.fn().mockResolvedValue({ player_id: null, revision: 0, draft: {}, source_state: "original" }),
    socialSnapshot: vi.fn().mockResolvedValue({ factions: [], characters: [], memberships: [], connections: [] }),
    listActivityLocations: vi.fn().mockResolvedValue([]), listActivityCharacters: vi.fn().mockResolvedValue({ items: [], has_more: false }),
  };
  for (const [name, value] of Object.entries(defaults)) if (!(name in client)) Object.assign(client, { [name]: value });
  withChatReads(client);
  const view = render(<ProductApp client={client} />);
  if (enter) await enterBook();
  return view;
}

it("renders four bottom tabs and keeps the known-event entry pinned", async () => {
  const client = { worldContent: vi.fn().mockResolvedValue([]),
    listProductWorlds: vi.fn().mockResolvedValue([worldA]), listPlayers: vi.fn().mockResolvedValue([]), selectedPlayer: vi.fn().mockResolvedValue({ player_id: null }) } as unknown as CoreClient;
  await renderProduct(client);
  expect((await screen.findAllByText("世界甲")).length).toBeGreaterThan(0);
  expect(screen.getByRole("navigation", { name: "主导航" }).querySelectorAll("button")).toHaveLength(4);
  expect(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "通讯录" }));
  expect(await screen.findByText("当前世界还没有角色")).toBeTruthy();
});

it("creates and switches worlds using the product client", async () => {
  const listProductWorlds = vi.fn().mockResolvedValueOnce([worldA]).mockResolvedValue([worldA, worldB]);
  const createWorld = vi.fn().mockResolvedValue({ world_id: "world-b" });
  const client = { worldContent: vi.fn().mockResolvedValue([]), listProductWorlds, createWorld, pauseProductWorld: vi.fn(), listPlayers: vi.fn().mockResolvedValue([]), selectedPlayer: vi.fn().mockResolvedValue({ player_id: null }) } as unknown as CoreClient;
  await renderProduct(client, false);
  fireEvent.click(await screen.findByRole("button", { name: "创建或导入一个新世界，空白书 1" }));
  fireEvent.click(await screen.findByRole("button", { name: "创建世界" }));
  fireEvent.change(screen.getByPlaceholderText("例如：绝区零"), { target: { value: "世界乙" } });
  fireEvent.click(screen.getByRole("button", { name: "创建档案并添加世界书" }));
  await waitFor(() => expect(createWorld).toHaveBeenCalledOnce());
  expect(createWorld.mock.calls[0][0]).toBe("世界乙");
  expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
  expect(await screen.findByRole("button", { name: "预览世界：世界乙" })).toBeTruthy();

});

it("reopens the last valid world and ignores a world that no longer exists", async () => {
  window.localStorage.setItem("livingworld.lastWorldId", "world-b");
  const client = {
    worldContent: vi.fn().mockResolvedValue([]),
    listProductWorlds: vi.fn().mockResolvedValue([worldA, worldB]),
    listPlayers: vi.fn().mockResolvedValue([]),
    selectedPlayer: vi.fn().mockResolvedValue({ player_id: null }),
    conversations: vi.fn().mockResolvedValue([]),
    groupConversations: vi.fn().mockResolvedValue([]),
  } as unknown as CoreClient;
  const view = await renderProduct(client, false);
  await screen.findByRole("button", { name: "预览世界：世界乙" });
  expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
  await enterBook("world-b");
  expect(window.localStorage.getItem("livingworld.lastWorldId")).toBe("world-b");
  view.unmount();
  window.localStorage.setItem("livingworld.lastWorldId", "missing-world");
  await renderProduct(client);
  expect(window.localStorage.getItem("livingworld.lastWorldId")).toBe("world-a");

});

it("shows the player-scoped world-event thread in chronological order", async () => {
  const playerId = "player-a";
  const knownEvents = vi.fn().mockResolvedValue([
    { event_id: "event-1", title: "有人移动了位置", occurred_at: "60000000", observed_at: "60000000", ledger_position: 4 },
    { event_id: "event-2", title: "你获知了一件世界事件", occurred_at: "120000000", observed_at: "180000000", ledger_position: 7 },
  ]);
  const client = { worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]), listPlayers: vi.fn().mockResolvedValue([{ player_id: playerId, name: "我" }]), selectedPlayer: vi.fn().mockResolvedValue({ player_id: playerId }), knownEvents, conversations: vi.fn().mockResolvedValue([]) } as unknown as CoreClient;
  await renderProduct(client);
  await screen.findAllByText("世界甲");
  await waitFor(() => expect(client.selectedPlayer).toHaveBeenCalledWith("world-a"));
  fireEvent.click(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" }));
  const timeline = await screen.findByRole("region", { name: "世界事件时间线" });
  await waitFor(() => expect(knownEvents).toHaveBeenCalledWith("world-a", expect.any(AbortSignal)));
  await screen.findByText("有人移动了位置");
  expect(timeline.querySelectorAll("li")).toHaveLength(2);
  expect(timeline.querySelectorAll("li")[0]?.textContent).toContain("第 1 天 · 00:01");
  expect(timeline.querySelectorAll("li")[1]?.textContent).toContain("获知于 第 1 天 · 00:03");
  fireEvent.click(screen.getByRole("button", { name: "返回聊天" }));
  expect(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" })).toBeTruthy();
});

it("turns a known event into an editable direct or group topic without sending it", async () => {
  const sendPlayerMessage = vi.fn();
  const sendGroupMessage = vi.fn();
  const client = {
    worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]),
    listPlayers: vi.fn().mockResolvedValue([{ player_id: "player-a", name: "我" }]),
    selectedPlayer: vi.fn().mockResolvedValue({ player_id: "player-a" }),
    knownEvents: vi.fn().mockResolvedValue([{ event_id: "event-1", title: "有人移动了位置", occurred_at: "60000000", observed_at: "60000000", ledger_position: 4 }]),
    conversations: vi.fn().mockResolvedValue([chatA]), groupConversations: vi.fn().mockResolvedValue([groupA]),
    conversationMessagePage: vi.fn().mockResolvedValue({ items: [], next_before_position: null }), directReplyAvailability: vi.fn().mockResolvedValue({ available: false }),
    groupReplyAvailability: vi.fn().mockResolvedValue({ available: false }), sendPlayerMessage, sendGroupMessage,
  } as unknown as CoreClient;
  await renderProduct(client);
  await waitFor(() => expect(client.conversations).toHaveBeenCalledWith("world-a", expect.any(AbortSignal)));
  fireEvent.click(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" }));
  fireEvent.click((await screen.findByText("有人移动了位置")).closest("li")!.querySelector("button")!);
  fireEvent.click(screen.getByRole("button", { name: /^角色甲$/ }));
  const directDraft = await screen.findByRole("textbox", { name: "发送给角色甲的消息" });
  expect(directDraft).toHaveProperty("value", "我看到一条世界事件：「有人移动了位置」（第 1 天 · 00:01）。你知道这件事吗？");
  expect(sendPlayerMessage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" }));
  fireEvent.click((await screen.findByText("有人移动了位置")).closest("li")!.querySelector("button")!);
  fireEvent.click(screen.getByRole("button", { name: "群聊：角色甲、角色乙" }));
  const groupDraft = await screen.findByRole("textbox", { name: "发送群聊消息" });
  expect(groupDraft).toHaveProperty("value", "我看到一条世界事件：「有人移动了位置」（第 1 天 · 00:01）。你知道这件事吗？");
  expect(sendGroupMessage).not.toHaveBeenCalled();
});

it("does not carry an event topic draft into another world", async () => {
  const otherChat: ChatConversation = { ...chatA, conversation_id: "chat-b", player_id: "player-b", character_id: "character-b" };
  const client = {
    worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA, worldB]),
    listPlayers: vi.fn((id: string) => Promise.resolve([{ player_id: id === "world-a" ? "player-a" : "player-b", name: "我" }])),
    selectedPlayer: vi.fn((id: string) => Promise.resolve({ player_id: id === "world-a" ? "player-a" : "player-b" })),
    knownEvents: vi.fn((id: string) => Promise.resolve(id === "world-a" ? [{ event_id: "event-a", title: "甲世界事件", occurred_at: "0", observed_at: "0", ledger_position: 1 }] : [])),
    conversations: vi.fn((id: string) => Promise.resolve([id === "world-a" ? chatA : otherChat])),
    groupConversations: vi.fn().mockResolvedValue([]), conversationMessagePage: vi.fn().mockResolvedValue({ items: [], next_before_position: null }),
    directReplyAvailability: vi.fn().mockResolvedValue({ available: false }),
  } as unknown as CoreClient;
  await renderProduct(client);
  await waitFor(() => expect(client.conversations).toHaveBeenCalledWith("world-a", expect.any(AbortSignal)));
  fireEvent.click(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" }));
  fireEvent.click((await screen.findByText("甲世界事件")).closest("li")!.querySelector("button")!);
  fireEvent.click(screen.getByRole("button", { name: /^角色甲$/ }));
  expect(await screen.findByRole("textbox", { name: "发送给角色甲的消息" })).toHaveProperty("value", expect.stringContaining("甲世界事件"));
  await switchBook("world-b");
  fireEvent.click(screen.getByRole("button", { name: "聊天" }));
  await waitFor(() => expect(client.conversations).toHaveBeenCalledWith("world-b", expect.any(AbortSignal)));
  fireEvent.click(await screen.findByRole("button", { name: /角色甲私聊/ }));
  expect(await screen.findByRole("textbox", { name: "发送给角色甲的消息" })).toHaveProperty("value", "");
});

it("does not display a late event response after switching worlds", async () => {
  let completeOldRequest!: (events: Array<{ event_id: string; title: string; occurred_at: string; observed_at: string; ledger_position: number }>) => void;
  const oldRequest = new Promise<Parameters<typeof completeOldRequest>[0]>(resolve => { completeOldRequest = resolve; });
  const knownEvents = vi.fn((id: string) => id === "world-a" ? oldRequest : Promise.resolve([]));
  const client = {
    worldContent: vi.fn().mockResolvedValue([]),
    listProductWorlds: vi.fn().mockResolvedValue([worldA, worldB]),
    listPlayers: vi.fn((id: string) => Promise.resolve([{ player_id: `${id}-player`, name: "我" }])),
    selectedPlayer: vi.fn((id: string) => Promise.resolve({ player_id: `${id}-player` })),
    knownEvents,
    conversations: vi.fn().mockResolvedValue([]),
  } as unknown as CoreClient;
  await renderProduct(client);
  await waitFor(() => expect(client.selectedPlayer).toHaveBeenCalledWith("world-a"));
  fireEvent.click(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" }));
  await waitFor(() => expect(knownEvents).toHaveBeenCalledWith("world-a", expect.any(AbortSignal)));
  await switchBook("world-b");
  await waitFor(() => expect(client.selectedPlayer).toHaveBeenCalledWith("world-b"));
  fireEvent.click(screen.getByRole("button", { name: "聊天" }));
  fireEvent.click(screen.getByRole("button", { name: "世界事件你已获知的事件置顶" }));
  await waitFor(() => expect(knownEvents).toHaveBeenCalledWith("world-b", expect.any(AbortSignal)));
  await act(async () => { completeOldRequest([{ event_id: "old", title: "旧世界私有事件", occurred_at: "0", observed_at: "0", ledger_position: 1 }]); });
  expect(screen.queryByText("旧世界私有事件")).toBeNull();
  expect(screen.getByText("我亲历的活动记录（0）")).toBeTruthy();
});

it("enters a new world at home through the product client", async () => {
  const player = { player_id: "player-home", name: "我" };
  let entered = false;
  const listPlayers = vi.fn().mockImplementation(async () => entered ? [player] : []);
  const selectedPlayer = vi.fn().mockImplementation(async () => ({ player_id: entered ? player.player_id : null }));
  const startAtHome = vi.fn().mockImplementation(async () => { entered = true; return { player_id: player.player_id }; });
  const client = { worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]), listPlayers, selectedPlayer, startAtHome,
    mediaSettings: vi.fn().mockResolvedValue({ enabled: false, frequency: 4, unlimited_stickers: false, online_enabled: false, auto_caption: false, caption_route: "ollama", caption_endpoint: "http://127.0.0.1:11434", caption_model: "", secret_ref: null, remote_caption_consent: false, daily_caption_limit: 10, caption_output_tokens: 256 }),
    mediaUsage: vi.fn().mockResolvedValue({ caption_calls: 0 }),
    speechSettings: vi.fn().mockResolvedValue({ revision: 0, settings: { enabled: false, provider: "local", local_url: "http://127.0.0.1:7861", secret_ref: null, max_characters: 10000, daily_calls: 0, skip_actions: true, consent_remote: false, consent_paid: false } }),
    speechPreviews: vi.fn().mockResolvedValue({ items: [] }),
    profile: vi.fn().mockResolvedValue({ name: "", description: "", revision: 0 }),
  } as unknown as CoreClient;
  await renderProduct(client);
  fireEvent.click(screen.getByRole("button", { name: "我" }));
  const enter = await screen.findByRole("button", { name: "进入世界" });
  expect(screen.getByText(/你会从“家”开始/)).toBeTruthy();
  fireEvent.click(enter);
  await waitFor(() => expect(startAtHome).toHaveBeenCalledWith("world-a"));
  expect(await screen.findByText("已绑定：我")).toBeTruthy();
});

it("offers home-entry recovery when player creation completed before binding", async () => {
  const player = { player_id: "player-home", name: "我" };
  const client = {
    worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]),
    listPlayers: vi.fn().mockResolvedValue([player]), selectedPlayer: vi.fn().mockResolvedValue({ player_id: null }),
    startAtHome: vi.fn().mockResolvedValue({ player_id: player.player_id }),
    mediaSettings: vi.fn().mockResolvedValue({ enabled: false, frequency: 4, unlimited_stickers: false, online_enabled: false, auto_caption: false, caption_route: "ollama", caption_endpoint: "http://127.0.0.1:11434", caption_model: "", secret_ref: null, remote_caption_consent: false, daily_caption_limit: 10, caption_output_tokens: 256 }),
    mediaUsage: vi.fn().mockResolvedValue({ caption_calls: 0 }),
    speechSettings: vi.fn().mockResolvedValue({ revision: 0, settings: { enabled: false, provider: "local", local_url: "http://127.0.0.1:7861", secret_ref: null, max_characters: 10000, daily_calls: 0, skip_actions: true, consent_remote: false, consent_paid: false } }),
    speechPreviews: vi.fn().mockResolvedValue({ items: [] }),
    profile: vi.fn().mockResolvedValue({ name: "", description: "", revision: 0 }),
  } as unknown as CoreClient;
  await renderProduct(client);
  fireEvent.click(screen.getByRole("button", { name: "我" }));
  fireEvent.click(await screen.findByRole("button", { name: "继续从家进入" }));
  await waitFor(() => expect(client.startAtHome).toHaveBeenCalledWith("world-a"));
});

it("changes only the bound player's busy/available state from Settings", async () => {
  let available = false;
  const selectedPlayer = vi.fn().mockImplementation(async () => ({ player_id: "player-a", availability: available ? "available" : "busy", presence_revision: available ? 1 : 0 }));
  const setPlayerAvailability = vi.fn().mockImplementation(async () => { available = true; return { availability: "available", presence_revision: 1 }; });
  const client = {
    worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]),
    listPlayers: vi.fn().mockResolvedValue([{ player_id: "player-a", name: "我" }]), selectedPlayer,
    setPlayerAvailability, conversations: vi.fn().mockResolvedValue([]),
  } as unknown as CoreClient;
  await renderProduct(client);
  await waitFor(() => expect(selectedPlayer).toHaveBeenCalledWith("world-a"));
  fireEvent.click(screen.getByRole("button", { name: "设置" }));
  fireEvent.click(await screen.findByRole("button", { name: /主动联系/ }));
  const toggle = await screen.findByRole("button", { name: "设为可用" });
  fireEvent.click(toggle);
  await waitFor(() => expect(setPlayerAvailability).toHaveBeenCalledOnce());
  expect(setPlayerAvailability.mock.calls[0]?.slice(0, 3)).toEqual(["world-a", "available", 0]);
  expect(await screen.findByText("可用", { selector: "strong" })).toBeTruthy();
});

it("opens a contact lazily and shows only the selected world's real conversations", async () => {
  const conversations = vi.fn().mockResolvedValue([]);
  const openDirectConversation = vi.fn().mockResolvedValue(chatA);
  const client = {
    worldContent: vi.fn((worldId: string) => Promise.resolve(worldId === "world-a" ? [cardA] : [])),
    listProductWorlds: vi.fn().mockResolvedValue([worldA, worldB]),
    listPlayers: vi.fn((worldId: string) => Promise.resolve([{ player_id: worldId === "world-a" ? "player-a" : "player-b", name: "我" }])),
    selectedPlayer: vi.fn((worldId: string) => Promise.resolve({ player_id: worldId === "world-a" ? "player-a" : "player-b" })),
    conversations, openDirectConversation, conversationMessagePage: vi.fn().mockResolvedValue({ items: [], next_before_position: null }),
    directReplyAvailability: vi.fn().mockResolvedValue({ available: false }),
  } as unknown as CoreClient;
  await renderProduct(client);
  fireEvent.click(screen.getByRole("button", { name: "通讯录" }));
  const contact = await screen.findByRole("button", { name: "角色甲查看角色资料与阵营" });
  expect(openDirectConversation).not.toHaveBeenCalled();
  fireEvent.click(contact);
  fireEvent.click(await screen.findByRole("button", { name: "打开会话" }));
  await waitFor(() => expect(openDirectConversation).toHaveBeenCalledWith("world-a", "card-a"));
  expect(await screen.findByRole("region", { name: "角色甲的会话" })).toBeTruthy();
  expect(await screen.findByText(/当前聊天模型尚不可用/)).toBeTruthy();
  await switchBook("world-b");
  fireEvent.click(screen.getByRole("button", { name: "聊天" }));
  expect(screen.queryByRole("region", { name: "角色甲的会话" })).toBeNull();
  await waitFor(() => expect(conversations).toHaveBeenCalledWith("world-b", expect.any(AbortSignal)));
});

it("creates a durable group from current-world cards and opens its transcript", async () => {
  const createGroupConversation = vi.fn().mockResolvedValue(groupA);
  const client = {
    worldContent: vi.fn().mockResolvedValue([cardA, cardB]),
    listProductWorlds: vi.fn().mockResolvedValue([worldA]),
    listPlayers: vi.fn().mockResolvedValue([{ player_id: "player-a", name: "我" }]),
    selectedPlayer: vi.fn().mockResolvedValue({ player_id: "player-a" }),
    conversations: vi.fn().mockResolvedValue([]), groupConversations: vi.fn().mockResolvedValue([]),
    createGroupConversation,
    conversationMessagePage: vi.fn().mockResolvedValue({ items: [], next_before_position: null }),
    groupReplyAvailability: vi.fn().mockResolvedValue({ available: false }),
  } as unknown as CoreClient;
  await renderProduct(client);
  fireEvent.click(await screen.findByRole("button", { name: "新建群聊" }));
  const setup = await screen.findByRole("region", { name: "创建群聊" });
  fireEvent.click(screen.getByRole("checkbox", { name: "角色甲" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "角色乙" }));
  fireEvent.click(screen.getByRole("button", { name: "创建群聊" }));
  await waitFor(() => expect(createGroupConversation).toHaveBeenCalledOnce());
  expect(createGroupConversation.mock.calls[0]?.slice(0, 2)).toEqual(["world-a", ["card-a", "card-b"]]);
  expect(setup.isConnected).toBe(false);
  expect(await screen.findByRole("region", { name: "群聊" })).toBeTruthy();
  expect(await screen.findByText(/当前聊天模型尚不可用/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "发送" })).toHaveProperty("disabled", true);
});

it("does not carry a group into another world's conversation list", async () => {
  const client = {
    worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA, worldB]),
    listPlayers: vi.fn((id: string) => Promise.resolve([{ player_id: `${id}-player`, name: "我" }])),
    selectedPlayer: vi.fn((id: string) => Promise.resolve({ player_id: `${id}-player` })),
    conversations: vi.fn().mockResolvedValue([]),
    groupConversations: vi.fn((id: string) => Promise.resolve(id === "world-a" ? [groupA] : [])),
    conversationMessagePage: vi.fn().mockResolvedValue({ items: [], next_before_position: null }),
    groupReplyAvailability: vi.fn().mockResolvedValue({ available: false }),
  } as unknown as CoreClient;
  await renderProduct(client);
  const groupRow = await screen.findByRole("button", { name: /角色甲、角色乙群聊/ });
  fireEvent.click(groupRow);
  expect(await screen.findByRole("region", { name: "群聊" })).toBeTruthy();
  await switchBook("world-b");
  fireEvent.click(screen.getByRole("button", { name: "聊天" }));
  await waitFor(() => expect(client.groupConversations).toHaveBeenCalledWith("world-b", expect.any(AbortSignal)));
  expect(screen.queryByRole("region", { name: "群聊" })).toBeNull();
  expect(screen.queryByRole("button", { name: /角色甲、角色乙群聊/ })).toBeNull();
});
