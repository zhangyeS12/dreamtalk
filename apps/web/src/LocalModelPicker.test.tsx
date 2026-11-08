import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { CoreClient, type ChatMediaSettings, type SpeechStatus } from "@dreamtalk/api-client";
import { LocalModelPicker, type LocalModelCatalog } from "./LocalModelPicker";
import { ChatMediaSettingsPanel } from "./ChatMedia";
import { SpeechSettings } from "./SpeechSettings";

const native = vi.hoisted(() => ({ invoke: vi.fn(), isTauri: vi.fn(() => true) }));
vi.mock("@tauri-apps/api/core", () => native);
vi.mock("./DesktopUpdates", () => ({ useDesktopUpdateBlock: vi.fn() }));
vi.mock("./SpeechPlayback", () => ({ useSpeech: () => null, speechFailure: (e: unknown) => String(e) }));
beforeEach(() => { native.invoke.mockReset(); native.isTauri.mockReturnValue(true); });
afterEach(cleanup);

function catalog(ids = ["synthetic:vision"], selected: string | null = null, complete = true): LocalModelCatalog {
  return { models: ids.map(id => ({ id, name: id })), selected, complete };
}
function Harness({ initial = "", endpoint = "http://127.0.0.1:11434", disabled = false, onChange = vi.fn(), kind = "vision" }: {
  initial?: string; endpoint?: string; disabled?: boolean; onChange?: (id: string) => void; kind?: "vision" | "speech";
}) {
  const [value, setValue] = useState(initial);
  return <LocalModelPicker kind={kind} value={value} endpoint={endpoint} disabled={disabled} onChange={id => { onChange(id); setValue(id); }} />;
}

it("automatically selects a sole verified vision model in the draft without writing settings", async () => {
  native.invoke.mockResolvedValue(catalog());
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  await waitFor(() => expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("synthetic:vision"));
  expect(onChange).toHaveBeenCalledOnce();
  expect(native.invoke).toHaveBeenCalledExactlyOnceWith("local_image_models", { endpoint: "http://127.0.0.1:11434" });
});

it("requires a choice among multiple models and preserves an existing missing model", async () => {
  native.invoke.mockResolvedValue(catalog(["first", "second"]));
  const first = render(<Harness />);
  await screen.findByRole("option", { name: "second" });
  expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("");
  first.unmount();
  render(<Harness initial="saved-model" />);
  await screen.findByRole("option", { name: "second" });
  expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("saved-model");
  expect(screen.getByRole("option", { name: /saved-model.*暂未检测到/ })).toBeTruthy();
});

it("keeps the saved model on failure and allows a metadata-only refresh", async () => {
  native.invoke.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(catalog());
  render(<Harness initial="saved-model" />);
  await screen.findByText(/暂时无法读取视觉模型/);
  expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("saved-model");
  fireEvent.click(screen.getByRole("button", { name: "刷新模型列表" }));
  await screen.findByRole("option", { name: "synthetic:vision" });
  expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("saved-model");
  expect(native.invoke).toHaveBeenCalledTimes(2);
});

it("does not silently choose from an incomplete catalog or during a save", async () => {
  native.invoke.mockResolvedValueOnce(catalog(["only"], null, false)).mockResolvedValueOnce(catalog());
  const onChange = vi.fn();
  const first = render(<Harness onChange={onChange} />);
  await screen.findByText(/部分模型信息尚未读取完整/);
  expect(onChange).not.toHaveBeenCalled();
  first.unmount();
  const second = render(<Harness disabled onChange={onChange} />);
  await screen.findByRole("option", { name: "synthetic:vision" });
  expect(onChange).not.toHaveBeenCalled();
  second.rerender(<Harness onChange={onChange} />);
  await waitFor(() => expect(onChange).toHaveBeenCalledWith("synthetic:vision"));
});

it("ignores a late catalog from a previous endpoint", async () => {
  let finish: (value: LocalModelCatalog) => void = () => undefined;
  native.invoke.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce(catalog(["new-model"]));
  const { rerender } = render(<Harness endpoint="http://127.0.0.1:11434" />);
  rerender(<Harness endpoint="http://127.0.0.1:11435" />);
  await waitFor(() => expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("new-model"));
  await act(async () => finish(catalog(["old-model"])));
  expect(screen.queryByRole("option", { name: "old-model" })).toBeNull();
});

it("shows the registered speech deployment without issuing a selection or starting it", async () => {
  native.invoke.mockResolvedValue(catalog(["speech-root"], "speech-root"));
  const onChange = vi.fn();
  render(<Harness kind="speech" onChange={onChange} />);
  await waitFor(() => expect((screen.getByLabelText("本地配音模型") as HTMLSelectElement).value).toBe("speech-root"));
  expect(onChange).not.toHaveBeenCalled();
  expect(native.invoke).toHaveBeenCalledExactlyOnceWith("local_speech_models");
});

it("does not attempt native discovery in a standalone browser", async () => {
  native.isTauri.mockReturnValue(false);
  render(<Harness initial="saved" />);
  await screen.findByText("请在桌面版中选择本地模型。");
  expect(native.invoke).not.toHaveBeenCalled();
  expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("saved");
});

const media: ChatMediaSettings = { enabled: true, frequency: 4, unlimited_stickers: false, online_enabled: false, auto_caption: false, caption_route: "ollama", caption_endpoint: "http://127.0.0.1:11434", caption_model: "", secret_ref: null, remote_caption_consent: false, daily_caption_limit: 10, caption_output_tokens: 256 };

it("saves the automatically chosen vision model through the existing media settings path", async () => {
  native.invoke.mockImplementation(async command => command === "local_image_models" ? catalog() : { state: "ready", model_root: "synthetic-root" });
  const api = Object.assign(Object.create(CoreClient.prototype) as CoreClient, {
    mediaSettings: vi.fn().mockResolvedValue(media), mediaUsage: vi.fn().mockResolvedValue({ caption_calls: 0 }),
    saveMediaSettings: vi.fn().mockImplementation(async (_world, next) => next),
  });
  render(<ChatMediaSettingsPanel client={api} worldId="world" onDirtyChange={() => {}} />);
  fireEvent.click(await screen.findByText("图片分析与用量"));
  await waitFor(() => expect((screen.getByLabelText("本地视觉模型") as HTMLSelectElement).value).toBe("synthetic:vision"));
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  await screen.findByText("已保存。保存设置不会发起搜索或图片分析。");
  expect(api.saveMediaSettings).toHaveBeenCalledWith("world", expect.objectContaining({ caption_model: "synthetic:vision", auto_caption: false }));
  expect(native.invoke.mock.calls.every(([command]) => ["local_image_models", "local_image_status", "prepare_local_image", "forget_media_credentials"].includes(command))).toBe(true);
});

it.each([false, true])("speech selection preserves its previous choice on failure=%s", async fails => {
  let selected = "first-root";
  native.invoke.mockImplementation(async (command, args) => {
    if (command === "local_speech_models") return catalog(["first-root", "second-root"], selected);
    if (command === "local_speech_status") return { model_root: selected, state: "stopped" };
    if (command === "select_local_speech_model") {
      if (fails) throw "speech_model_folder_busy";
      selected = args.modelId;
      return { model_root: selected, state: "configured" };
    }
    throw new Error("unexpected native command");
  });
  const settings = { enabled: false, provider: "local", local_url: "http://127.0.0.1:7861", secret_ref: null, max_characters: 1600, daily_calls: 20, skip_actions: true, consent_remote: false, consent_paid: false };
  const api = Object.assign(Object.create(CoreClient.prototype) as CoreClient, {
    speechSettings: vi.fn().mockResolvedValue({ settings, revision: 0 } as SpeechStatus),
    saveSpeechSettings: vi.fn(),
  });
  render(<SpeechSettings client={api} worldId="world" />);
  await screen.findByRole("option", { name: "second-root" });
  fireEvent.change(screen.getByLabelText("本地配音模型"), { target: { value: "second-root" } });
  await waitFor(() => expect(native.invoke).toHaveBeenCalledWith("select_local_speech_model", { modelId: "second-root" }));
  await waitFor(() => expect((screen.getByLabelText("本地配音模型") as HTMLSelectElement).value).toBe(fails ? "first-root" : "second-root"));
  expect(api.saveSpeechSettings).not.toHaveBeenCalled();
  expect(native.invoke.mock.calls.some(([command]) => ["prepare_local_speech", "repair_local_speech"].includes(command))).toBe(false);
});
