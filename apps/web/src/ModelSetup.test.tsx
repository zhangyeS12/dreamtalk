import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { type CoreClient } from "@dreamtalk/api-client";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { ModelSetup } from "./ModelSetup";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), isTauri: vi.fn(() => true) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function client(status: string): CoreClient {
  return { health: vi.fn().mockResolvedValue({ llm_status: status }) } as unknown as CoreClient;
}

it("keeps first-time setup unavailable outside desktop and after configuration", async () => {
  vi.mocked(isTauri).mockReturnValue(false);
  const view = render(<ModelSetup client={client("unconfigured")} />);
  expect(await screen.findByText("当前浏览器开发入口不保存模型密钥。请在桌面应用完成首次设置。")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "保存模型设置" })).toBeNull();
  view.unmount();
  vi.mocked(isTauri).mockReturnValue(true);
  render(<ModelSetup client={client("ready")} />);
  expect(await screen.findByText("模型和凭据已就绪。首次聊天时才会实际联系提供商。")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "保存模型设置" })).toBeNull();
});

it("submits one explicit model, secure secret and trusted limits only after all fields are present", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue(undefined);
  const onConfigured = vi.fn();
  render(<ModelSetup client={client("unconfigured")} onConfigured={onConfigured} />);
  const save = await screen.findByRole("button", { name: "保存模型设置" });
  expect(save).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByRole("textbox", { name: "模型名称" }), { target: { value: "exact-model" } });
  fireEvent.change(screen.getByLabelText("API 密钥"), { target: { value: "KEY-CANARY" } });
  expect(save).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByRole("spinbutton", { name: "单次输入 Token 上界" }), { target: { value: "20000" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "单次输出 Token 上界" }), { target: { value: "2000" } });
  fireEvent.click(save);
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("configure_chat_model", {
    setup: { provider_kind: "openai-responses", model_id: "exact-model", base_url: null,
      max_billable_input_tokens: 20000, max_output_tokens: 2000 },
    secret: "KEY-CANARY",
  }));
  await waitFor(() => expect(onConfigured).toHaveBeenCalledOnce());
  expect(screen.getByLabelText("API 密钥")).toHaveProperty("value", "");
});

it("does not claim a failed secure-store write configured the model", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockRejectedValue("secure_storage_unavailable");
  const onConfigured = vi.fn();
  render(<ModelSetup client={client("unconfigured")} onConfigured={onConfigured} />);
  await screen.findByRole("button", { name: "保存模型设置" });
  fireEvent.change(screen.getByRole("textbox", { name: "模型名称" }), { target: { value: "exact-model" } });
  fireEvent.change(screen.getByLabelText("API 密钥"), { target: { value: "KEY-CANARY" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "单次输入 Token 上界" }), { target: { value: "20000" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "单次输出 Token 上界" }), { target: { value: "2000" } });
  fireEvent.click(screen.getByRole("button", { name: "保存模型设置" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Windows 安全凭据存储不可用，密钥未保存。");
  expect(onConfigured).not.toHaveBeenCalled();
});
