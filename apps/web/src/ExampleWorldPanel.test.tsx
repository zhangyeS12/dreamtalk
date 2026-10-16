import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreRequestError, type CoreClient, type ExampleWorldTemplate } from "@dreamtalk/api-client";
import { ExampleWorldPanel } from "./ExampleWorldPanel";

afterEach(() => { cleanup(); localStorage.clear(); });
const template: ExampleWorldTemplate = {
  id: "campus-v1", name: "校园示例", description: "普通高中日常", reviewed_hash: "a".repeat(64),
  locations: ["教室"], entries: [{ key: "school", title: "校园背景", content: "公开校园设定" }],
  characters: [{ key: "classmate", name: "沈清禾", role: "清纯校花", description: "文静的同学",
    personality: "温柔", scenario: "课间", first_mes: "你好" }], pending: [],
};

function fixture(value = template) {
  const client = { exampleWorld: vi.fn().mockResolvedValue(value),
    createExampleWorld: vi.fn().mockResolvedValue({ world_id: "world-example" }) };
  const onCreated = vi.fn().mockResolvedValue(undefined), onBusy = vi.fn();
  const view = render(<ExampleWorldPanel client={client as unknown as CoreClient}
    onCreated={onCreated} onBusy={onBusy} onClose={vi.fn()} />);
  return { ...view, client, onCreated, onBusy };
}

it("previews without creating and sends only the explicitly confirmed public entries", async () => {
  const { client, onCreated } = fixture();
  await screen.findByRole("heading", { name: "校园示例" });
  expect(client.createExampleWorld).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("查看世界书与角色可见范围（1条）"));
  fireEvent.click(screen.getByRole("checkbox", { name: "校园背景 · 作为公共背景" }));
  fireEvent.click(screen.getByRole("button", { name: "确认设定并创建示例世界" }));
  await waitFor(() => expect(onCreated).toHaveBeenCalledWith("world-example"));
  expect(client.createExampleWorld).toHaveBeenCalledWith(template, expect.any(String), []);
  expect(localStorage.getItem("livingworld.exampleWorld.campus-v1")).toBeNull();
});

it("reuses the same confirmation after a lost response and a component remount", async () => {
  const first = fixture();
  first.client.createExampleWorld.mockRejectedValue(new Error("connection_lost"));
  fireEvent.click(await screen.findByRole("button", { name: "确认设定并创建示例世界" }));
  await screen.findByRole("alert");
  const identity = first.client.createExampleWorld.mock.calls[0][1];
  first.unmount();
  const second = fixture();
  fireEvent.click(await screen.findByRole("button", { name: "继续创建" }));
  await waitFor(() => expect(second.onCreated).toHaveBeenCalled());
  expect(second.client.createExampleWorld).toHaveBeenCalledWith(template, identity, ["school"]);
});

it("resumes a server-side unfinished setup and freezes the reviewed scope", async () => {
  const pending = { request_id: "00000000-0000-0000-0000-000000000001",
    reviewed_hash: template.reviewed_hash, public_entries: [] };
  const value = { ...template, pending: [pending] };
  const { client } = fixture(value);
  await screen.findByRole("button", { name: "继续创建" });
  fireEvent.click(screen.getByText("查看世界书与角色可见范围（1条）"));
  expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "继续创建" }));
  await waitFor(() => expect(client.createExampleWorld).toHaveBeenCalledWith(value, pending.request_id, []));
});

it("offers a fresh explicit creation after an old example was deleted", async () => {
  const { client } = fixture();
  client.createExampleWorld.mockRejectedValue(new CoreRequestError(409, "example_world_deleted"));
  fireEvent.click(await screen.findByRole("button", { name: "确认设定并创建示例世界" }));
  await screen.findByText("之前创建的示例已经删除。可以确认设定后重新创建。");
  expect((screen.getByRole("button", { name: "确认设定并创建示例世界" }) as HTMLButtonElement).disabled).toBe(false);
  expect(localStorage.getItem("livingworld.exampleWorld.campus-v1")).toBeNull();
});
