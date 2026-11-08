import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreRequestError, type CoreClient, type LibraryCardItem } from "@dreamtalk/api-client";
import { PackCollection } from "./packs/PackCollection";
import { defaultPack } from "./packs/packDesign";

vi.mock("../useWindowStill", () => ({ useWindowStill: () => true }));
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value() { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value() { this.open = false; } });
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: true, addEventListener() {}, removeEventListener() {} }) });
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
});
afterEach(cleanup);
const props = { worlds: [], active: true, onBrowseWorlds: vi.fn(), onCarryChange: vi.fn(), onJoined: vi.fn(), onEditingChange: vi.fn(), onCountChange: vi.fn() };
const card: LibraryCardItem = { card_id: "synthetic-card", name: "合成角色", revision: 3, design: null, world_ids: ["existing-world"] };
const pack = { ...defaultPack("我的收藏"), cardIds: [card.card_id], revision: 5 };

it("confirms pack deletion, prevents double submission, and starts burning only after success", async () => {
  let resolve!: (result: { removed: boolean }) => void;
  const remove = vi.fn(() => new Promise<{ removed: boolean }>(done => { resolve = done; }));
  const client = { cardPacks: vi.fn().mockResolvedValue([pack]), libraryCards: vi.fn().mockResolvedValue([card]), deleteCardPack: remove } as unknown as CoreClient;
  render(<PackCollection {...props} client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "选择卡包：我的收藏" }));
  fireEvent.click(screen.getByRole("button", { name: "删除卡包" }));
  expect(screen.getByText(/里面的角色卡仍保留/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "取消，保留卡包" }));
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "删除卡包" }));
  const confirm = screen.getByRole("button", { name: "确认删除卡包" });
  fireEvent.click(confirm); fireEvent.click(confirm);
  expect(remove).toHaveBeenCalledTimes(1);
  expect(remove).toHaveBeenCalledWith(pack);
  expect(document.querySelector("[data-removal-effect]")).toBeNull();
  expect(screen.getByRole("button", { name: "正在删除…" })).toHaveProperty("disabled", true);
  resolve({ removed: true });
  await waitFor(() => expect(document.querySelector('[data-removal-effect="burn"]')).toBeTruthy());
  await waitFor(() => expect(screen.queryByRole("button", { name: "选择卡包：我的收藏" })).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "全部角色卡" }));
  expect(await screen.findByRole("button", { name: "查看角色卡：合成角色" })).toBeTruthy();
});

it("keeps the card and skips particles after a failure, then synchronizes every pack after success", async () => {
  let items = [card];
  const updated = { ...pack, cardIds: [], revision: 6 };
  const remove = vi.fn().mockRejectedValueOnce(new CoreRequestError(503)).mockImplementation(async () => { items = []; return { removed: true, packs: [updated] }; });
  const save = vi.fn().mockImplementation(async value => ({ ...value, revision: 7 }));
  const client = { cardPacks: vi.fn().mockResolvedValue([pack]), libraryCards: vi.fn(async () => items), deleteLibraryCard: remove, saveCardPack: save, discardPackDraft: vi.fn().mockResolvedValue({ discarded: true }) } as unknown as CoreClient;
  render(<PackCollection {...props} client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "全部角色卡" }));
  fireEvent.click(await screen.findByRole("button", { name: "查看角色卡：合成角色" }));
  fireEvent.click(screen.getByRole("button", { name: "删除角色卡" }));
  expect(screen.getByText(/已加入各世界的角色、聊天和记忆会保留/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "确认删除角色卡" }));
  await screen.findByRole("alert");
  expect(document.querySelector("[data-removal-effect]")).toBeNull();
  expect(remove).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "取消，保留角色卡" }));
  expect(screen.getByRole("button", { name: "查看角色卡：合成角色" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "删除角色卡" }));
  fireEvent.click(screen.getByRole("button", { name: "确认删除角色卡" }));
  await waitFor(() => expect(document.querySelector('[data-removal-effect="particles"]')).toBeTruthy());
  await waitFor(() => expect(screen.queryByRole("button", { name: "查看角色卡：合成角色" })).toBeNull());
  expect(remove).toHaveBeenLastCalledWith(card);
  fireEvent.click(screen.getByRole("button", { name: /返回卡包/ }));
  fireEvent.click(screen.getByRole("button", { name: "选择卡包：我的收藏" }));
  fireEvent.click(screen.getByRole("button", { name: "设计与装卡" }));
  fireEvent.change(screen.getByLabelText("一句介绍"), { target: { value: "删除后继续编辑" } });
  fireEvent.click(screen.getByRole("button", { name: "保存卡包" }));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  expect(save.mock.calls[0][0].revision).toBe(6);
  expect(save.mock.calls[0][0].cardIds).toEqual([]);
});

it("shows a stale revision without playing an effect or automatically retrying", async () => {
  const remove = vi.fn().mockRejectedValue(new CoreRequestError(409));
  const client = { cardPacks: vi.fn().mockResolvedValue([pack]), libraryCards: vi.fn().mockResolvedValue([card]), deleteCardPack: remove } as unknown as CoreClient;
  render(<PackCollection {...props} client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "选择卡包：我的收藏" }));
  fireEvent.click(screen.getByRole("button", { name: "删除卡包" }));
  fireEvent.click(screen.getByRole("button", { name: "确认删除卡包" }));
  await screen.findByText(/卡包已发生变化/);
  expect(remove).toHaveBeenCalledTimes(1);
  expect(document.querySelector("[data-removal-effect]")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await waitFor(() => expect(client.cardPacks).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("dialog", { name: "删除卡包？" })).toBeNull();
});
