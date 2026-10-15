import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { type CoreClient } from "@dreamtalk/api-client";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { ModelSetup } from "./ModelSetup";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), isTauri: vi.fn(() => true) }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

function client(status: string): CoreClient {
  return { health: vi.fn().mockResolvedValue({ llm_status: status }) } as unknown as CoreClient;
}

it("keeps first-time setup unavailable outside desktop and after configuration", async () => {
  vi.mocked(isTauri).mockReturnValue(false);
  const view = render(<ModelSetup client={client("unconfigured")} />);
  expect(await screen.findByText("当前浏览器开发入口不保存模型密钥。请在桌面应用完成首次设置。")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "保存默认模型配置" })).toBeNull();
  view.unmount();
  vi.mocked(isTauri).mockReturnValue(true);
  render(<ModelSetup client={client("ready")} />);
  expect(await screen.findByText("模型和凭据已就绪。聊天或联网生成时才会实际联系提供商。")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "保存默认模型配置" })).toBeNull();
});

it("submits one explicit model, secure secret and trusted limits only after all fields are present", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue(undefined);
  const onConfigured = vi.fn();
  render(<ModelSetup client={client("unconfigured")} onConfigured={onConfigured} />);
  const save = await screen.findByRole("button", { name: "保存默认模型配置" });
  fireEvent.click(save);
  expect(onConfigured).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "exact-model" } });
  fireEvent.change(screen.getByLabelText("API 密钥"), { target: { value: "KEY-CANARY" } });
  fireEvent.click(save);
  expect(onConfigured).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "模型输入容量" }), { target: { value: "20000" } });
  fireEvent.change(screen.getByLabelText("单次回复上限"), { target: { value: "custom" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "自定义回复上限" }), { target: { value: "2000" } });
  fireEvent.click(save);
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("configure_chat_model", {
    setup: { provider_kind: "openai-responses", model_id: "exact-model", base_url: null,
      max_billable_input_tokens: 20000, max_output_tokens: 2000, timeout_ms: 30000, native_json: false },
    secret: "KEY-CANARY", streaming: true, worldId: null,
  }));
  await waitFor(() => expect(onConfigured).toHaveBeenCalledOnce());
  expect(screen.getByLabelText("API 密钥")).toHaveProperty("value", "");
});

it("does not claim a failed secure-store write configured the model", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockImplementation(async command => { if (command === "managed_chat_model_setup") return null; throw "secure_storage_unavailable"; });
  const onConfigured = vi.fn();
  render(<ModelSetup client={client("unconfigured")} onConfigured={onConfigured} />);
  await screen.findByRole("button", { name: "保存默认模型配置" });
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "exact-model" } });
  fireEvent.change(screen.getByLabelText("API 密钥"), { target: { value: "KEY-CANARY" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "模型输入容量" }), { target: { value: "20000" } });
  fireEvent.change(screen.getByLabelText("单次回复上限"), { target: { value: "custom" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "自定义回复上限" }), { target: { value: "2000" } });
  fireEvent.click(screen.getByRole("button", { name: "保存默认模型配置" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Windows 安全凭据存储不可用，密钥未保存。");
  expect(onConfigured).not.toHaveBeenCalled();
});

it("edits a managed model without reading or resubmitting the existing key", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockImplementation(async command => {
    if (command === "managed_chat_model_setup") return {
      provider_kind: "anthropic", model_id: "old-model", base_url: null,
      max_billable_input_tokens: 10000, max_output_tokens: 1000,
    };
    return { old_credential_cleanup_incomplete: false };
  });
  const onConfigured = vi.fn();
  render(<ModelSetup client={client("ready")} onConfigured={onConfigured} />);
  const save = await screen.findByRole("button", { name: "更新默认模型配置" });
  expect(screen.getByLabelText("模型名称")).toHaveProperty("value", "old-model");
  expect(screen.getByLabelText("新 API 密钥（可留空）")).toHaveProperty("value", "");
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "new-model" } });
  fireEvent.change(screen.getByLabelText("模型输入容量"), { target: { value: "10000" } });
  fireEvent.click(save);
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("update_chat_model", {
    setup: { provider_kind: "anthropic", model_id: "new-model", base_url: null,
      max_billable_input_tokens: 10000, max_output_tokens: 1000, timeout_ms: 30000, native_json: false },
    secret: "", streaming: false, worldId: null,
  }));
  expect(onConfigured).toHaveBeenCalledOnce();
});

it("requires a new key when changing provider and never overwrites an advanced configuration", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValueOnce({
    provider_kind: "anthropic", model_id: "old-model", base_url: null,
    max_billable_input_tokens: 10000, max_output_tokens: 1000,
  });
  const view = render(<ModelSetup client={client("ready")} />);
  const save = await screen.findByRole("button", { name: "更新默认模型配置" });
  fireEvent.change(screen.getByLabelText("提供商"), { target: { value: "gemini" } });
  fireEvent.click(save);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("请填写 API 密钥"));
  expect(invoke).not.toHaveBeenCalledWith("update_chat_model", expect.anything());
  view.unmount();

  vi.mocked(invoke).mockRejectedValue("model_edit_requires_managed_single_chat_configuration");
  render(<ModelSetup client={client("ready")} />);
  expect(await screen.findByText("当前配置由高级方式管理；此处不会覆盖其中的路由、定价或其他设置。")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "更新默认模型配置" })).toBeNull();
});

it("warns when the current turn ceiling cannot fit the trusted input bound", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue({
    provider_kind: "anthropic", model_id: "large-model", base_url: null,
    max_billable_input_tokens: 50_000, max_output_tokens: 2_000,
  });
  render(<ModelSetup client={client("ready")} turnTokenCeiling={50_000} />);
  expect(await screen.findByText(/至少 50,001 才能留出输出空间/)).toBeTruthy();
});

it("fills a reviewed compatible service without a model call or silently raising the budget", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue(null);
  const apply = vi.fn();
  render(<ModelSetup client={client("unconfigured")} turnTokenCeiling={50_000} onApplyTokenCeiling={apply} />);
  const choices = await screen.findByLabelText("常用服务与型号");
  const option = [...(choices as HTMLSelectElement).options].find(item => item.textContent?.endsWith(" · kimi-k2.5"))!;
  fireEvent.change(choices, { target: { value: option.value } });
  expect(screen.getByLabelText("模型名称")).toHaveProperty("value", "kimi-k2.5");
  expect(screen.getByLabelText("服务地址")).toHaveProperty("value", "https://api.moonshot.cn/v1");
  expect(screen.getByLabelText("模型输入容量")).toHaveProperty("value", "262144");
  expect(apply).not.toHaveBeenCalled();
  expect(invoke).toHaveBeenCalledTimes(1); // Read the managed configuration only.
  fireEvent.click(screen.getByRole("button", { name: "应用此型号所需的聊天额度" }));
  expect(apply).toHaveBeenCalledWith(270336);
  fireEvent.change(screen.getByLabelText("服务地址"), { target: { value: "https://proxy.invalid/v1" } });
  expect(screen.getByLabelText("模型输入容量")).toHaveProperty("value", "");
});

it("repairs only an explicitly selected degraded world with a newly supplied key", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockImplementation(async command => {
    if (command === "managed_chat_model_setup") throw "llm_config_invalid";
  });
  const onConfigured = vi.fn();
  render(<ModelSetup client={client("degraded")} worldId="world-a" onConfigured={onConfigured} />);
  expect(screen.queryByRole("button", { name: "保存 API 并修复" })).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "重新配置当前世界API" }));
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "gpt-4o" } });
  fireEvent.change(screen.getByLabelText("API 密钥"), { target: { value: "REPAIR-KEY-CANARY" } });
  fireEvent.click(screen.getByRole("button", { name: "保存 API 并修复" }));
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("repair_chat_model", expect.objectContaining({
    worldId: "world-a", secret: "REPAIR-KEY-CANARY", setup: expect.objectContaining({ model_id: "gpt-4o" }),
  })));
  expect(invoke).not.toHaveBeenCalledWith("configure_chat_model", expect.anything());
  expect(onConfigured).toHaveBeenCalledOnce();
});
