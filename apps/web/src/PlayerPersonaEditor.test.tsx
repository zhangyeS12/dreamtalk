import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, CoreRequestError, type PlayerPersonaDraft } from "@dreamtalk/api-client";
import { PlayerPersonaEditor } from "./PlayerPersonaEditor";
import { PersonaSourcePicker } from "./PersonaSourcePicker";

afterEach(cleanup);

function fixture() {
  const source = { reference: { import_id: "source", content_id: "content", reviewed_hash: "a".repeat(64) }, kind: "lorebook", title: "哲", text: "录像店店主", excerpt: false };
  const client = {
    playerPersona: vi.fn().mockResolvedValue({ player_id: "player", revision: 2, draft: {}, source_state: "original" }),
    playerPersonaSources: vi.fn().mockResolvedValue({ items: [source], next_after: null }),
    previewPlayerPersona: vi.fn().mockImplementation(async (_world, draft: PlayerPersonaDraft, revision) => ({ preview_id: "preview", expected_revision: revision, draft, source_title: "哲", expires_in_seconds: 600 })),
    confirmPlayerPersona: vi.fn().mockImplementation(async () => ({ player_id: "player", revision: 3, draft: { identity_name: "哲", public_identity: "录像店店主", source: source.reference }, source_state: "current" })),
  };
  return { client, asClient: client as unknown as CoreClient, source };
}

it("requires preview and explicit confirmation before applying the selected persona", async () => {
  const { client, asClient } = fixture();
  const dirty = vi.fn();
  render(<PlayerPersonaEditor client={asClient} worldId="world" onDirtyChange={dirty} />);
  fireEvent.click(await screen.findByText("从世界书选择身份"));
  fireEvent.click(await screen.findByRole("button", { name: "采用哲" }));
  expect(client.confirmPlayerPersona).not.toHaveBeenCalled();
  expect((screen.getByLabelText("设定人物名称") as HTMLInputElement).value).toBe("哲");
  fireEvent.click(screen.getByRole("button", { name: "预览身份修改" }));
  await screen.findByRole("region", { name: "身份修改预览" });
  expect(client.previewPlayerPersona).toHaveBeenCalledWith("world", expect.objectContaining({ identity_name: "哲" }), 2, "player");
  expect(client.confirmPlayerPersona).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认采用身份" }));
  await screen.findByText("设定身份已采用。");
  expect(client.confirmPlayerPersona).toHaveBeenCalledWith("world", "preview");
  expect(dirty).toHaveBeenLastCalledWith(false);
});

it("keeps edits on source conflict and makes returning from preview editable", async () => {
  const { client, asClient } = fixture();
  render(<PlayerPersonaEditor client={asClient} worldId="world" onDirtyChange={vi.fn()} />);
  const name = await screen.findByLabelText("设定人物名称");
  fireEvent.change(name, { target: { value: "手动身份" } });
  client.previewPlayerPersona.mockRejectedValueOnce(new CoreRequestError(409));
  fireEvent.click(screen.getByRole("button", { name: "预览身份修改" }));
  await screen.findByRole("alert");
  expect((name as HTMLInputElement).value).toBe("手动身份");
  fireEvent.click(screen.getByRole("button", { name: "预览身份修改" }));
  fireEvent.click(await screen.findByRole("button", { name: "返回编辑" }));
  expect((name as HTMLInputElement).disabled).toBe(false);
  expect(client.confirmPlayerPersona).not.toHaveBeenCalled();
});

it("ignores a late response from the previous world", async () => {
  const { client, asClient } = fixture();
  let finish: (value: unknown) => void = () => {};
  client.playerPersona.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<PlayerPersonaEditor client={asClient} worldId="a" onDirtyChange={vi.fn()} />);
  view.rerender(<PlayerPersonaEditor client={asClient} worldId="b" onDirtyChange={vi.fn()} />);
  await screen.findByLabelText("设定人物名称");
  finish({ player_id: "old", revision: 9, draft: { identity_name: "旧世界" }, source_state: "original" });
  await waitFor(() => expect((screen.getByLabelText("设定人物名称") as HTMLInputElement).value).toBe(""));
});

it("pages sources without truncating the world to its first page and rejects repeated cursors", async () => {
  const { client, asClient, source } = fixture();
  client.playerPersonaSources.mockResolvedValueOnce({ items: [source], next_after: "next" });
  client.playerPersonaSources.mockResolvedValueOnce({ items: [{ ...source, title: "后续资料" }], next_after: null });
  render(<PersonaSourcePicker client={asClient} worldId="world" onChoose={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "下一页资料" }));
  await screen.findByRole("button", { name: "采用后续资料" });
  expect(client.playerPersonaSources).toHaveBeenLastCalledWith("world", "", "next", false, expect.any(AbortSignal));
  fireEvent.click(screen.getByRole("button", { name: "返回第一页" }));
  client.playerPersonaSources.mockResolvedValueOnce({ items: [source], next_after: "again" });
  fireEvent.change(screen.getByLabelText("查找设定资料"), { target: { value: "哲" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "搜索" }).hasAttribute("disabled")).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  client.playerPersonaSources.mockResolvedValueOnce({ items: [source], next_after: "again" });
  fireEvent.click(await screen.findByRole("button", { name: "下一页资料" }));
  await screen.findByRole("alert");
});

it("a source change suspends the persona and adding the same recipient keeps a single row", async () => {
  const { client, asClient, source } = fixture();
  client.playerPersona.mockResolvedValue({ player_id: "player", revision: 2, draft: {}, source_state: "changed" });
  client.playerPersonaSources.mockResolvedValue({ items: [{ ...source, kind: "character", root_import_id: "root" }], next_after: null });
  render(<PlayerPersonaEditor client={asClient} worldId="world" onDirtyChange={vi.fn()} />);
  await screen.findByText(/绑定的资料已被替换/);
  fireEvent.click(screen.getByText("添加角色的初始认识（0）"));
  const add = await screen.findByRole("button", { name: "添加哲" });
  fireEvent.click(add); fireEvent.click(add);
  expect(screen.getAllByLabelText("与哲的初始关系")).toHaveLength(1);
});

it("keeps complete emoji characters when preparing a long source excerpt", async () => {
  const { client, asClient, source } = fixture();
  client.playerPersonaSources.mockResolvedValue({ items: [{ ...source, text: "文" + "😀".repeat(2100) }], next_after: null });
  render(<PlayerPersonaEditor client={asClient} worldId="world" onDirtyChange={vi.fn()} />);
  fireEvent.click(await screen.findByText("从世界书选择身份"));
  fireEvent.click(await screen.findByRole("button", { name: "采用哲" }));
  fireEvent.click(screen.getByRole("button", { name: "预览身份修改" }));
  await screen.findByRole("region", { name: "身份修改预览" });
  const draft = client.previewPlayerPersona.mock.calls[0][1];
  expect(draft.public_identity).toBe("文" + "😀".repeat(1999));
});
