import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CoreClient } from "@dreamtalk/api-client";
import { invoke } from "@tauri-apps/api/core";
import { CardShare } from "./CardShare";

vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => true, invoke: vi.fn() }));
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value() { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value() { this.open = false; } });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("saves the reviewed revision and digest, and treats cancelling the native picker as cancellation", async () => {
  const info = { filename: "合成角色-角色卡.charx", digest: "a".repeat(64), size: 4000, warnings: [] };
  const client = { libraryShareInfo: vi.fn().mockResolvedValue(info) } as unknown as CoreClient;
  vi.mocked(invoke).mockResolvedValueOnce(null).mockResolvedValueOnce("synthetic.charx");
  render(<CardShare client={client} card={{ card_id: "card", name: "合成角色", revision: 4, design: null, world_ids: ["world"] }} onClose={vi.fn()} />);
  const save = await screen.findByRole("button", { name: "保存完整角色卡" });
  await waitFor(() => expect((save as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(save);
  await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1));
  expect(screen.queryByText(/角色卡已保存/)).toBeNull();
  await waitFor(() => expect((save as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(save);
  await screen.findByText(/角色卡已保存/);
  expect(invoke).toHaveBeenLastCalledWith("save_file_export", { request: { kind: "library_card", item_id: "card", expected_revision: 4, expected_digest: info.digest }, filename: info.filename });
  expect(client.libraryShareInfo).toHaveBeenCalledTimes(1);
});
