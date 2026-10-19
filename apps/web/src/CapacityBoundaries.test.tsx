import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, type ContentEditorDraft, type ContentEditorEntry, type ContentEditorPage } from "@dreamtalk/api-client";
import { ContentEditorPages } from "./contentEditorPages";
import { ContentEditor } from "./ContentEditor";

afterEach(cleanup);
const entry = (index: number): ContentEditorEntry => ({ source_entry_id: `entry-${index}`, title: `标题-${index}`,
  content: "完整正文", keywords: [], secondary_keywords: [], enabled: true, constant: true,
  selective_logic: "AND_ANY", priority: 0, order: index });
const header: ContentEditorDraft = { kind: "lorebook", name: "大世界书", description: "", personality: "", background: "",
  scenario: "", speech_guidance: "", first_message: "", creator_notes: "", tags: [], example_dialogue: [], entries: [] };
const page = (offset: number): ContentEditorPage => ({ draft: { ...header, entries: Array.from({ length: 32 }, (_, i) => entry(offset + i)) },
  research: null, offset, total_entries: 150, next_offset: offset + 32 });

it("only deletes loaded entries explicitly removed by the user", () => {
  const pages = new ContentEditorPages();
  pages.accept(page(0));
  const draft = { ...header, name: "改名", entries: page(0).draft.entries.slice(1) };
  const patch = pages.patch(draft);
  expect(patch.fields).toEqual({ name: "改名" });
  expect(patch.removed).toEqual(["entry-0"]);
  expect(patch.updates).toEqual([]);
  expect(patch.added).toEqual([]);
});

it("keeps edits on multiple pages and does not resubmit an untouched long field", () => {
  const pages = new ContentEditorPages();
  const first = page(0);
  first.draft.entries[0].content = "长中文".repeat(10000);
  pages.accept(first);
  pages.capture(first.draft.entries.map((value, i) => i ? value : { ...value, title: "只改标题" }));
  pages.accept(page(32));
  const patch = pages.patch({ ...header, entries: page(32).draft.entries.map((value, i) => i ? value : { ...value, enabled: false }) });
  expect(patch.updates).toEqual([
    { source_entry_id: "entry-0", fields: { title: "只改标题" } },
    { source_entry_id: "entry-32", fields: { enabled: false } },
  ]);
  expect(patch.removed).toEqual([]);
});

it("opens a large book, retains edits while paging and sends a sparse preview", async () => {
  const preview = { import_id: "preview", replaces_import_id: "book", kind: "lorebook" as const,
    reviewed_hash: "hash", characters: [], lorebooks: [], entries: [] };
  const client = { contentEditorPage: vi.fn(async (_world, _book, offset = 0) => page(offset)),
    previewContentChanges: vi.fn().mockResolvedValue(preview), discardWorldContent: vi.fn().mockResolvedValue({ discarded: true }) };
  render(<ContentEditor client={client as unknown as CoreClient} worldId="world" kind="lorebook"
    editing={{ ...preview, import_id: "book", replaces_import_id: null }} onSaved={vi.fn()} onCancel={vi.fn()} />);
  await screen.findByDisplayValue("标题-0");
  fireEvent.change(screen.getAllByLabelText("标题")[0], { target: { value: "跨页保留" } });
  fireEvent.click(screen.getByText("下一页"));
  await screen.findByDisplayValue("标题-32");
  fireEvent.click(screen.getByText("上一页"));
  await screen.findByDisplayValue("跨页保留");
  fireEvent.click(screen.getByText("预览并保存"));
  await waitFor(() => expect(client.previewContentChanges).toHaveBeenCalled());
  expect(client.previewContentChanges.mock.calls[0][2]).toEqual({ fields: {},
    updates: [{ source_entry_id: "entry-0", fields: { title: "跨页保留" } }], removed: [], added: [] });
});

it("reads all unread pages and keeps the server global unread flag", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ player_id: "p", items: [],
    waiting_conversation_id: null, has_unread: true, next_after: "next" })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ player_id: "p", items: [{ conversation_id: "last", latest_position: 1, unread: 1 }],
      waiting_conversation_id: null, has_unread: true, next_after: null })));
  const client = new CoreClient({ endpoint: "http://127.0.0.1:49152", token: "synthetic", generation: "g" }, fetcher);
  const value = await client.chatUnread("world");
  expect(value.items.map(item => item.conversation_id)).toEqual(["last"]);
  expect(value.has_unread).toBe(true);
  expect(value.next_after).toBeNull();
  expect(String(fetcher.mock.calls[1][0])).toContain("after=next");
});

it("rejects a repeated unread cursor rather than reading forever", async () => {
  const value = { player_id: "p", items: [], waiting_conversation_id: null, next_after: "same" };
  const fetcher = vi.fn(async () => new Response(JSON.stringify(value)));
  const client = new CoreClient({ endpoint: "http://127.0.0.1:49152", token: "synthetic", generation: "g" }, fetcher);
  await expect(client.chatUnread("world")).rejects.toMatchObject({ status: 502, code: "unread_cursor_invalid" });
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it("returns to the previous local page after deleting its final entry", () => {
  render(<ContentEditor client={{} as CoreClient} worldId="world" kind="lorebook" onSaved={vi.fn()} onCancel={vi.fn()} />);
  for (let i = 0; i < 32; i++) fireEvent.click(screen.getByText("添加条目"));
  expect(screen.getByText("条目 33")).toBeTruthy();
  fireEvent.click(screen.getByText("删除条目"));
  expect(screen.getByText("条目 1")).toBeTruthy();
  expect(screen.getAllByText("删除条目")).toHaveLength(32);
});
