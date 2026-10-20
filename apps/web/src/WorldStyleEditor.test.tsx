import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, CoreRequestError } from "@dreamtalk/api-client";
import { WorldStyleEditor } from "./WorldStyleEditor";

vi.mock("./DesktopUpdates", () => ({ useDesktopUpdateBlock: vi.fn() }));
afterEach(cleanup);

function client() {
  return Object.assign(Object.create(CoreClient.prototype) as CoreClient, {
    worldStyle: vi.fn().mockResolvedValue({ instructions: "", revision: 0 }),
    previewWorldStyle: vi.fn().mockImplementation(async (_world, instructions, revision) => ({ instructions, revision, preview_id: "a".repeat(64) })),
    confirmWorldStyle: vi.fn().mockResolvedValue({ instructions: "都市悬疑", revision: 1 }),
  });
}

it("requires a preview and explicit confirmation and reports unsaved state", async () => {
  const api = client(), dirty = vi.fn();
  render(<WorldStyleEditor client={api} worldId="world-a" onDirtyChange={dirty} />);
  const input = await screen.findByLabelText("当前世界的写作约定");
  fireEvent.change(input, { target: { value: "都市悬疑" } });
  await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(true));
  fireEvent.click(screen.getByRole("button", { name: "预览修改" }));
  await screen.findByRole("heading", { name: "确认后的世界风格" });
  expect(api.confirmWorldStyle).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认并保存" }));
  await screen.findByText(/已保存。从下一次角色发言起/);
  expect(api.confirmWorldStyle).toHaveBeenCalledOnce();
  expect(api.confirmWorldStyle).toHaveBeenCalledWith("world-a", expect.objectContaining({ instructions: "都市悬疑", revision: 0 }));
  await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(false));
});

it("retains a conflicting draft and does not automatically resubmit", async () => {
  const api = client();
  vi.mocked(api.confirmWorldStyle).mockRejectedValue(new CoreRequestError(409, "world_style_conflict"));
  render(<WorldStyleEditor client={api} worldId="world-a" onDirtyChange={() => {}} />);
  fireEvent.change(await screen.findByLabelText("当前世界的写作约定"), { target: { value: "都市悬疑" } });
  fireEvent.click(screen.getByRole("button", { name: "预览修改" }));
  fireEvent.click(await screen.findByRole("button", { name: "确认并保存" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("textbox").getAttribute("disabled")).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "返回修改" }));
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("都市悬疑");
  expect(api.confirmWorldStyle).toHaveBeenCalledOnce();
});
