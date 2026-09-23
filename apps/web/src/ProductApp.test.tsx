import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, type WorldSettings } from "@livingworld/api-client";
import { ProductApp } from "./ProductApp";

afterEach(cleanup);

const worldA: WorldSettings = { world_id: "world-a", name: "世界甲", world_time: "0", clock_state: "running", time_scale: "1", runtime_state: "ready" };
const worldB: WorldSettings = { world_id: "world-b", name: "世界乙", world_time: "60000000", clock_state: "paused", time_scale: "2", runtime_state: "paused" };

it("renders four bottom tabs and keeps the known-event entry pinned", async () => {
  const client = { worldContent: vi.fn().mockResolvedValue([]),
    listProductWorlds: vi.fn().mockResolvedValue([worldA]), listPlayers: vi.fn().mockResolvedValue([]), selectedPlayer: vi.fn().mockResolvedValue({ player_id: null }) } as unknown as CoreClient;
  render(<ProductApp client={client} />);
  expect((await screen.findAllByText("世界甲")).length).toBeGreaterThan(0);
  expect(screen.getByRole("navigation", { name: "主导航" }).querySelectorAll("button")).toHaveLength(4);
  expect(screen.getByRole("button", { name: "世界事件看看你知道的新鲜事，找个聊天话题置顶" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "通讯录" }));
  expect(await screen.findByText("当前世界还没有角色")).toBeTruthy();
});

it("creates and switches worlds using the product client", async () => {
  const listProductWorlds = vi.fn().mockResolvedValueOnce([worldA]).mockResolvedValue([worldA, worldB]);
  const createWorld = vi.fn().mockResolvedValue({ world_id: "world-b" });
  const client = { worldContent: vi.fn().mockResolvedValue([]), listProductWorlds, createWorld, pauseProductWorld: vi.fn(), listPlayers: vi.fn().mockResolvedValue([]), selectedPlayer: vi.fn().mockResolvedValue({ player_id: null }) } as unknown as CoreClient;
  render(<ProductApp client={client} />);
  fireEvent.click(screen.getByRole("button", { name: "设置" }));
  expect(await screen.findByRole("combobox", { name: "当前世界" })).toBeTruthy();
  fireEvent.change(screen.getByPlaceholderText("给世界起个名字"), { target: { value: "世界乙" } });
  fireEvent.click(screen.getByRole("button", { name: "创建世界" }));
  await waitFor(() => expect(createWorld).toHaveBeenCalledOnce());
  expect(createWorld.mock.calls[0][0]).toBe("世界乙");
  await waitFor(() => expect((screen.getByRole("combobox", { name: "当前世界" }) as HTMLSelectElement).value).toBe("world-b"));
  expect(screen.getByText("第 1 天 · 00:01")).toBeTruthy();
});

it("shows the player-scoped world-event thread in chronological order", async () => {
  const playerId = "player-a";
  const knownEvents = vi.fn().mockResolvedValue([
    { event_id: "event-1", title: "有人移动了位置", occurred_at: "60000000", observed_at: "60000000", ledger_position: 4 },
    { event_id: "event-2", title: "你获知了一件世界事件", occurred_at: "120000000", observed_at: "180000000", ledger_position: 7 },
  ]);
  const client = { worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]), listPlayers: vi.fn().mockResolvedValue([{ player_id: playerId, name: "我" }]), selectedPlayer: vi.fn().mockResolvedValue({ player_id: playerId }), knownEvents } as unknown as CoreClient;
  render(<ProductApp client={client} />);
  await screen.findAllByText("世界甲");
  await waitFor(() => expect(client.selectedPlayer).toHaveBeenCalledWith("world-a"));
  fireEvent.click(screen.getByRole("button", { name: "世界事件看看你知道的新鲜事，找个聊天话题置顶" }));
  const timeline = await screen.findByRole("region", { name: "世界事件时间线" });
  await waitFor(() => expect(knownEvents).toHaveBeenCalledWith("world-a"));
  await screen.findByText("有人移动了位置");
  expect(timeline.querySelectorAll("li")).toHaveLength(2);
  expect(timeline.querySelectorAll("li")[0]?.textContent).toContain("第 1 天 · 00:01");
  expect(timeline.querySelectorAll("li")[1]?.textContent).toContain("获知于 第 1 天 · 00:03");
  fireEvent.click(screen.getByRole("button", { name: "返回聊天" }));
  expect(screen.getByRole("button", { name: "世界事件看看你知道的新鲜事，找个聊天话题置顶" })).toBeTruthy();
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
  } as unknown as CoreClient;
  render(<ProductApp client={client} />);
  await waitFor(() => expect(client.selectedPlayer).toHaveBeenCalledWith("world-a"));
  fireEvent.click(screen.getByRole("button", { name: "世界事件看看你知道的新鲜事，找个聊天话题置顶" }));
  await waitFor(() => expect(knownEvents).toHaveBeenCalledWith("world-a"));
  fireEvent.click(screen.getByRole("button", { name: "设置" }));
  fireEvent.change(screen.getByRole("combobox", { name: "当前世界" }), { target: { value: "world-b" } });
  await waitFor(() => expect(client.selectedPlayer).toHaveBeenCalledWith("world-b"));
  fireEvent.click(screen.getByRole("button", { name: "聊天" }));
  fireEvent.click(screen.getByRole("button", { name: "世界事件看看你知道的新鲜事，找个聊天话题置顶" }));
  await waitFor(() => expect(knownEvents).toHaveBeenCalledWith("world-b"));
  await act(async () => { completeOldRequest([{ event_id: "old", title: "旧世界私有事件", occurred_at: "0", observed_at: "0", ledger_position: 1 }]); });
  expect(screen.queryByText("旧世界私有事件")).toBeNull();
  expect(screen.getByText("你目前还没有获知世界事件。以后在这里找聊天话题。")).toBeTruthy();
});

it("enters a new world at home through the product client", async () => {
  const player = { player_id: "player-home", name: "我" };
  const listPlayers = vi.fn().mockResolvedValueOnce([]).mockResolvedValue([player]);
  const selectedPlayer = vi.fn().mockResolvedValueOnce({ player_id: null }).mockResolvedValue({ player_id: player.player_id });
  const startAtHome = vi.fn().mockResolvedValue({ player_id: player.player_id });
  const client = { worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]), listPlayers, selectedPlayer, startAtHome,
    profile: vi.fn().mockResolvedValue({ name: "", description: "", revision: 0 }),
  } as unknown as CoreClient;
  render(<ProductApp client={client} />);
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
    profile: vi.fn().mockResolvedValue({ name: "", description: "", revision: 0 }),
  } as unknown as CoreClient;
  render(<ProductApp client={client} />);
  fireEvent.click(screen.getByRole("button", { name: "我" }));
  fireEvent.click(await screen.findByRole("button", { name: "继续从家进入" }));
  await waitFor(() => expect(client.startAtHome).toHaveBeenCalledWith("world-a"));
});

it("changes only the bound player's busy/available state from Settings", async () => {
  const selectedPlayer = vi.fn()
    .mockResolvedValueOnce({ player_id: "player-a", availability: "busy", presence_revision: 0 })
    .mockResolvedValueOnce({ player_id: "player-a", availability: "available", presence_revision: 1 });
  const setPlayerAvailability = vi.fn().mockResolvedValue({ availability: "available", presence_revision: 1 });
  const client = {
    worldContent: vi.fn().mockResolvedValue([]), listProductWorlds: vi.fn().mockResolvedValue([worldA]),
    listPlayers: vi.fn().mockResolvedValue([{ player_id: "player-a", name: "我" }]), selectedPlayer,
    setPlayerAvailability,
  } as unknown as CoreClient;
  render(<ProductApp client={client} />);
  await waitFor(() => expect(selectedPlayer).toHaveBeenCalledWith("world-a"));
  fireEvent.click(screen.getByRole("button", { name: "设置" }));
  const toggle = await screen.findByRole("button", { name: "设为可用" });
  fireEvent.click(toggle);
  await waitFor(() => expect(setPlayerAvailability).toHaveBeenCalledOnce());
  expect(setPlayerAvailability.mock.calls[0]?.slice(0, 3)).toEqual(["world-a", "available", 0]);
  expect(await screen.findByText("可用", { selector: "strong" })).toBeTruthy();
});
