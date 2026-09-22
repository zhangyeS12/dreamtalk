import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, CoreRequestError } from "@livingworld/api-client";
import { ProfileEditor } from "./ProfileEditor";

afterEach(cleanup);

it("saves the selected world's description with its loaded edit revision", async () => {
  const saveProfile = vi.fn().mockResolvedValue({ name: "旅人", description: "新的身份", revision: 4 });
  const client = { profile: vi.fn().mockResolvedValue({ name: "旅人", description: "旧身份", revision: 3 }), saveProfile } as unknown as CoreClient;
  const onDirtyChange = vi.fn();
  render(<ProfileEditor client={client} worldId="world-a" onDirtyChange={onDirtyChange} />);
  const description = await screen.findByLabelText("我在这个世界的身份");
  fireEvent.change(description, { target: { value: "新的身份" } });
  fireEvent.click(screen.getByRole("button", { name: "保存世界身份" }));
  await screen.findByText("已保存。");
  expect(saveProfile).toHaveBeenCalledWith({ name: "旅人", description: "新的身份", revision: 3 }, "world-a");
  expect(onDirtyChange).toHaveBeenLastCalledWith(false);
});

it("retains user input when another window has already saved a newer profile", async () => {
  const client = {
    profile: vi.fn().mockResolvedValue({ name: "我", description: "原始描述", revision: 2 }),
    saveProfile: vi.fn().mockRejectedValue(new CoreRequestError(409)),
  } as unknown as CoreClient;
  render(<ProfileEditor client={client} />);
  const description = await screen.findByLabelText("关于我");
  fireEvent.change(description, { target: { value: "尚未保存的输入" } });
  fireEvent.click(screen.getByRole("button", { name: "保存通用信息" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("其他窗口修改"));
  expect((description as HTMLTextAreaElement).value).toBe("尚未保存的输入");
});
