import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CoreClient } from "@dreamtalk/api-client";
import { CoreRequestError } from "@dreamtalk/api-client";
import { PackCollection } from "./PackCollection";
import { defaultPack } from "./packDesign";

vi.mock("../../useWindowStill", () => ({ useWindowStill: () => true }));
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: true, addEventListener() {}, removeEventListener() {} }) });
});
afterEach(cleanup);

const props = { worlds: [], active: true, onBrowseWorlds: vi.fn(), onCarryChange: vi.fn(), onJoined: vi.fn(), onEditingChange: vi.fn(), onCountChange: vi.fn() };

it("does not replace a failed real library read with synthetic packs and supports explicit retry", async () => {
  const packs = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue([]);
  const client = { cardPacks: packs, libraryCards: vi.fn().mockResolvedValue([]) } as unknown as CoreClient;
  render(<PackCollection {...props} client={client} />);
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "创建新卡包" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await screen.findByRole("button", { name: "创建新卡包" });
  expect(screen.queryByRole("button", { name: /选择卡包/ })).toBeNull();
  expect(packs).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "全部角色卡" })).toBeTruthy();
});

it("keeps an uncertain pack save as the same draft and revision for an explicit retry", async () => {
  const save = vi.fn().mockRejectedValueOnce(new CoreRequestError(503)).mockImplementation(async pack => ({ ...pack, revision: 1 }));
  const discard = vi.fn().mockResolvedValue({ discarded: true });
  const client = { cardPacks: vi.fn().mockResolvedValue([]), libraryCards: vi.fn().mockResolvedValue([]), saveCardPack: save, discardPackDraft: discard } as unknown as CoreClient;
  render(<PackCollection {...props} client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "创建新卡包" }));
  const name = screen.getByLabelText("卡包名称");
  fireEvent.change(name, { target: { value: "我的收藏" } });
  const confirm = screen.getByRole("button", { name: "保存卡包" });
  fireEvent.click(confirm);
  await screen.findByText(/保存结果暂未确认/);
  expect((name as HTMLInputElement).value).toBe("我的收藏");
  expect(save).toHaveBeenCalledTimes(1);
  expect(save.mock.calls[0][0].revision).toBe(0);
  await waitFor(() => expect((confirm as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(confirm);
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "设计卡包" })).toBeNull());
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0]);
  expect(screen.getByRole("button", { name: "选择卡包：我的收藏" })).toBeTruthy();
  expect(discard).toHaveBeenCalledTimes(1);
});

it("reports a stale revision without overwriting a saved pack", async () => {
  const pack = { ...defaultPack("已保存卡包"), revision: 7 };
  const save = vi.fn().mockRejectedValue(new CoreRequestError(409));
  const client = { cardPacks: vi.fn().mockResolvedValue([pack]), libraryCards: vi.fn().mockResolvedValue([]), saveCardPack: save, discardPackDraft: vi.fn().mockResolvedValue({ discarded: true }) } as unknown as CoreClient;
  render(<PackCollection {...props} client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "选择卡包：已保存卡包" }));
  fireEvent.click(screen.getByRole("button", { name: "设计与装卡" }));
  fireEvent.change(screen.getByLabelText("一句介绍"), { target: { value: "未保存的草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "保存卡包" }));
  await screen.findByText(/卡包已被其他编辑更新/);
  expect(save).toHaveBeenCalledTimes(1);
  expect(save.mock.calls[0][0].revision).toBe(7);
  expect((screen.getByLabelText("一句介绍") as HTMLInputElement).value).toBe("未保存的草稿");
});
