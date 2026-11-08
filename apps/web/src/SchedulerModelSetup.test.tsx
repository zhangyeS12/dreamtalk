import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { type CoreClient } from "@dreamtalk/api-client";
import { ModelSetup } from "./ModelSetup";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), isTauri: vi.fn(() => true) }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.resetAllMocks(); });
const setup = { provider_kind: "openai-compatible", model_id: "synthetic-pro", base_url: "https://synthetic.invalid/v1", max_billable_input_tokens: 20000, max_output_tokens: 8192, timeout_ms: 30000, native_json: false, inherited: true };
function environment(inherited = true) {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockImplementation(async command => command === "managed_chat_model_setup" || command === "managed_scheduler_model_setup" ? { ...setup, inherited } : { old_credential_cleanup_incomplete: false });
  return { health: vi.fn().mockResolvedValue({ llm_status: "ready" }) } as unknown as CoreClient;
}

it("selects scheduler settings with an explicit purpose and preserves the selected world", async () => {
  const client = environment();
  const changed = vi.fn();
  render(<ModelSetup client={client} worldId="synthetic-world" onConfigured={changed} />);
  fireEvent.click(screen.getByRole("tab", { name: "群聊调度器" }));
  await screen.findByText("当前跟随全局调度器配置。保存后仅为这个世界设置独立调度器模型。");
  expect(client.health).toHaveBeenCalledWith(undefined, "synthetic-world", "group_scheduler");
  expect(invoke).toHaveBeenCalledWith("managed_scheduler_model_setup", { worldId: "synthetic-world" });
  expect(screen.queryByRole("checkbox", { name: "逐步显示回复" })).toBeNull();
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "synthetic-flash" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "模型输入容量" }), { target: { value: "20000" } });
  fireEvent.click(screen.getByRole("button", { name: "保存调度器模型" }));
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("configure_scheduler_model", expect.objectContaining({
    setup: expect.objectContaining({ model_id: "synthetic-flash", native_json: false }),
    worldId: "synthetic-world", secret: "", streaming: false,
  })));
  expect(invoke).not.toHaveBeenCalledWith("update_chat_model", expect.anything());
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
});

it.each([undefined, "synthetic-world"])("restores the correct scheduler inheritance for world=%s", async worldId => {
  const client = environment(false);
  render(<ModelSetup client={client} worldId={worldId} onConfigured={vi.fn()} />);
  fireEvent.click(screen.getByRole("tab", { name: "群聊调度器" }));
  fireEvent.click(await screen.findByRole("button", { name: worldId ? "恢复继承全局调度器" : "恢复跟随全局模型" }));
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("use_default_scheduler_model", { worldId: worldId ?? null }));
});

it("keeps a dirty model form when switching is declined and supports keyboard tabs", async () => {
  const client = environment();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<ModelSetup client={client} />);
  fireEvent.change(await screen.findByLabelText("模型名称"), { target: { value: "unsaved-model" } });
  fireEvent.click(screen.getByRole("tab", { name: "群聊调度器" }));
  expect(confirm).toHaveBeenCalledOnce();
  expect(screen.getByLabelText("模型名称")).toHaveProperty("value", "unsaved-model");
  confirm.mockReturnValue(true);
  fireEvent.keyDown(screen.getByRole("tab", { name: "聊天模型" }), { key: "ArrowRight" });
  await screen.findByRole("region", { name: "群聊调度器模型" });
  expect(screen.getByRole("tab", { name: "群聊调度器" }).getAttribute("aria-selected")).toBe("true");
});
