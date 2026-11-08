import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { SaveSlotsPanel } from "./SaveSlots";

const native = vi.hoisted(() => ({ invoke: vi.fn(), blockReason: "" }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => true, invoke: native.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("./DesktopUpdates", () => ({ useDesktopSaveBlock: () => native.blockReason, useDesktopUpdateBlock: () => {} }));

const entry = (name: string) => ({ name, saved_at: "2026-10-17T01:23:45+00:00", available: true, counts: { worlds: 2, chat_messages: 8 } });
const catalog = () => ({ directory: "synthetic-saves", revision: 7, slots: [entry("启动自动档"), entry("分享手动档"), null, null, null] });
afterEach(() => { cleanup(); vi.restoreAllMocks(); native.invoke.mockReset(); native.blockReason = ""; });

async function mount() {
  native.invoke.mockImplementation(() => Promise.resolve(catalog()));
  const view = render(<SaveSlotsPanel />);
  await act(async () => {});
  return view;
}

it("shows exactly five positions and repeats the full replacement warning on each opening", async () => {
  const view = await mount();
  expect(screen.getAllByRole("listitem")).toHaveLength(5);
  expect(screen.getByRole("note").textContent).toContain("同时覆盖自动存档");
  expect(screen.getAllByRole("time")).toHaveLength(5);
  expect(screen.queryByRole("button", { name: /清空|删除全部/ })).toBeNull();
  view.unmount();
  await mount();
  expect(screen.getByRole("note").textContent).toContain("先将它另存到一个手动位置");
});

it("imports a supplied path to its manual position without loading", async () => {
  await mount();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const row = within(screen.getAllByRole("listitem")[1]);
  fireEvent.change(row.getByRole("textbox", { name: "手动位置 1 的导入路径" }), { target: { value: "Z:\\synthetic\\friend.dreamsave" } });
  await act(async () => { fireEvent.click(row.getByRole("button", { name: "从此路径导入" })); });
  const operations = native.invoke.mock.calls.filter(([command]) => command === "operate_save_slot");
  expect(operations).toHaveLength(1);
  expect(operations[0][1].request).toMatchObject({ action: "import", slot: 1, source: "Z:\\synthetic\\friend.dreamsave", revision: 7, confirmed: true });
  expect(screen.getByRole("status").textContent).toContain("尚未加载");
});

it("copies the actual automatic save instead of requesting a current-data save", async () => {
  await mount();
  const row = within(screen.getAllByRole("listitem")[2]);
  await act(async () => { fireEvent.click(row.getByRole("button", { name: "另存自动存档到此处" })); });
  expect(native.invoke).toHaveBeenLastCalledWith("operate_save_slot", expect.objectContaining({ request: expect.objectContaining({ action: "copy_auto", slot: 2 }) }));
  expect(screen.getByRole("status").textContent).toContain("当前数据没有切换");
});

it("requires load confirmation and cancellation never invokes a load", async () => {
  await mount();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  fireEvent.click(within(screen.getAllByRole("listitem")[1]).getByRole("button", { name: "加载" }));
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining("同时覆盖自动存档"));
  expect(native.invoke.mock.calls.filter(([command]) => command === "operate_save_slot")).toHaveLength(0);
});

it("keeps existing saves visible on a failed load and offers reconnection", async () => {
  await mount();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  native.invoke.mockRejectedValueOnce("save_snapshot_damaged");
  await act(async () => { fireEvent.click(within(screen.getAllByRole("listitem")[1]).getByRole("button", { name: "加载" })); });
  expect(screen.getByRole("alert").textContent).toContain("原数据和已有存档保留");
  expect(screen.getByRole("button", { name: "重新连接" })).toBeTruthy();
  expect(screen.getByDisplayValue("分享手动档")).toBeTruthy();
});

it("blocks loading while an existing edit is unsaved", async () => {
  native.blockReason = "世界书有未保存的编辑。";
  await mount();
  expect(screen.getAllByRole<HTMLButtonElement>("button", { name: "加载" }).every(button => button.disabled)).toBe(true);
  expect(screen.getByText(/世界书有未保存的编辑/)).toBeTruthy();
});

it("does not show an import-success message when the native picker was cancelled", async () => {
  await mount();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  native.invoke.mockResolvedValueOnce({ ...catalog(), cancelled: true });
  await act(async () => { fireEvent.click(within(screen.getAllByRole("listitem")[1]).getByRole("button", { name: "导入文件" })); });
  expect(screen.queryByRole("status")).toBeNull();
});

it("offers stored saves during recovery without allowing a damaged current store to overwrite them", async () => {
  native.invoke.mockResolvedValue(catalog());
  render(<SaveSlotsPanel recovery />);
  await act(async () => {});
  expect(screen.getAllByRole("button", { name: "加载" })).toHaveLength(2);
  expect(screen.queryByRole("button", { name: /保存当前数据/ })).toBeNull();
  expect(screen.getAllByRole("listitem")).toHaveLength(5);
});
