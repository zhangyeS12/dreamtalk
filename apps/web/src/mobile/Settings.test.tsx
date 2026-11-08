import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CoreClient, type WorldSettings } from "@dreamtalk/api-client";
import { MobileSettings } from "./Settings";
import { BackgroundSettings } from "./BackgroundSettings";
import { hostCall } from "./host";
import { mobileInvoke } from "./native";
import { settingsPages } from "../SettingsHandbook";
vi.mock("./host", () => ({ hostCall: vi.fn(), feedback: () => "操作未完成" }));
vi.mock("../ModelSetup", () => ({ ModelSetup: () => <div>模型设置组件</div> }));
vi.mock("../WorldStyleEditor", () => ({ WorldStyleEditor: () => <div>世界文风组件</div> }));
const call = vi.mocked(hostCall);
const world = { world_id: "world", name: "合成校园", world_time: "0", time_scale: "1", clock_state: "running", runtime_state: "ready" } as WorldSettings;
const status = { enabled: false, running: false, start_on_boot: false, notifications_allowed: false, battery_unrestricted: false, problem: null };
afterEach(cleanup);
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); });
test("all eleven Windows settings categories have mobile entries", () => {
  render(<MobileSettings client={{} as CoreClient} world={world} player="player" budget={8192} onBudget={vi.fn()} onConfigured={vi.fn()} onDirtyChange={vi.fn()} />);
  for (const page of settingsPages) expect(screen.getByText(page.id === "background" ? "后台运行与通知" : page.label)).toBeTruthy();
});
test("editing token ceiling does not change applied chat budget until explicit apply", async () => {
  const apply = vi.fn(), dirty = vi.fn();
  render(<MobileSettings client={{} as CoreClient} world={world} budget={8192} onBudget={apply} onConfigured={vi.fn()} onDirtyChange={dirty} />);
  fireEvent.click(screen.getByText("模型与聊天"));
  fireEvent.change(screen.getByLabelText("每轮 Token 上限"), { target: { value: "16000" } });
  expect(apply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "应用聊天额度" }));
  expect(apply).toHaveBeenCalledWith(16000);
});
test("background session requires consent and notification permission", async () => {
  call.mockImplementation(async (operation) => operation === "background_status" ? status : false);
  render(<BackgroundSettings />);
  const enable = await screen.findByRole("button", { name: "开启后台运行" });
  expect((enable as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByText(/我同意已开启的后台功能/));
  fireEvent.click(enable);
  await screen.findByRole("alert");
  expect(call).toHaveBeenCalledWith("request_notifications");
  expect(call.mock.calls.some(([operation]) => operation === "configure_background")).toBe(false);
});
test("stopping background does not require new billing consent", async () => {
  call.mockResolvedValue({ ...status, enabled: true, running: true, notifications_allowed: true });
  render(<BackgroundSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "停止后台运行" }));
  await waitFor(() => expect(call).toHaveBeenCalledWith("configure_background", { enabled: false, start_on_boot: false, consent: false }));
});
test("cancelling SAF import never starts import or load", async () => {
  call.mockImplementation(async operation => operation === "import_document" ? null : { revision: 1, slots: [null] });
  const value = await mobileInvoke<{ cancelled: boolean }>("operate_save_slot", { request: { action: "import", slot: 1 } });
  expect(value.cancelled).toBe(true);
  expect(call.mock.calls.some(([operation]) => operation === "operate_save_slot")).toBe(false);
});
