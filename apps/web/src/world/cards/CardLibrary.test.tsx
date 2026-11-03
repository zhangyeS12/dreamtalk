import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ActivityCharacterDirectory, ActivityLocation, CoreClient, LibraryCardPreview, SocialSnapshot } from "@dreamtalk/api-client";
import { LocationMap } from "../../LocationWorkspace";
import { CardAuthor } from "./CardAuthor";
import { CardFace } from "./CardFaces";
import { defaultDesign } from "./cardDesign";

beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value() { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value() { this.open = false; } });
});
afterEach(cleanup);

it("keeps existing saved layer coordinates while new cards use the approved centered layout", () => {
  const design = defaultDesign({ name: "合成角色", design: null });
  const original = { ...design.front.layers[0], anchor: undefined, x: 12, y: 63 };
  const face = { ...design.front, layers: [original] };
  const view = render(<CardFace design={design} face={face} side="front" />);
  expect((screen.getByText("合成角色") as HTMLElement).style.transform).toBe("rotate(0deg)");
  expect((screen.getByText("合成角色") as HTMLElement).style.left).toBe("12%");
  view.rerender(<CardFace design={design} face={design.front} side="front" />);
  expect((screen.getByText("合成角色") as HTMLElement).style.transform).toContain("translate(-50%,-50%)");
  expect(original.x).toBe(12);
});

it("keeps an unplaced character out of the map even when focused", () => {
  const place: ActivityLocation = { location_id: "home", name: "家", is_home: true, parent_id: null, hidden: false, is_region: false, allowed_character_ids: [], revision: 0 };
  const directory: ActivityCharacterDirectory = { player_id: "player", items: [
    { character_id: "actor", name: "无地点角色", initialized: false, root_import_id: "root", initial_location_id: null, current_location_id: null, locked: false, residency: "strong", revision: null, policy_revision: 0 },
  ] };
  const social: SocialSnapshot = { characters: [{ root_import_id: "root", current_import_id: "root", character_id: "actor", name: "无地点角色", avatar_digest: null }], factions: [], memberships: [], connections: [] };
  const props = { locations: [place], directory, social, urls: {}, selected: "root", onSelect: vi.fn(), onChat: vi.fn(), openingChat: false, onEdit: vi.fn() };
  const view = render(<LocationMap {...props} />);
  expect(screen.queryByText("无地点角色")).toBeNull();
  expect(screen.queryByRole("button", { name: "打开会话" })).toBeNull();
  view.rerender(<LocationMap {...props} directory={{ ...directory, items: [{ ...directory.items[0], initialized: true, initial_location_id: "home", current_location_id: "home", revision: 0 }] }} />);
  expect(screen.getByRole("button", { name: "无地点角色，家" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "打开会话" })).toBeTruthy();
});

const preview: LibraryCardPreview = { preview_id: "preview", card_id: "card", expected_revision: 0, reviewed_hash: "reviewed", content: {
  import_id: "card", replaces_import_id: null, kind: "character", reviewed_hash: "reviewed", characters: [{ id: "definition", name: "合成角色", description: "", personality: "", background: "", scenario: "", speech_guidance: "", creator_notes: "", tags: [], example_dialogue: [], authored_instructions: {} }], lorebooks: [], entries: [], warnings: [],
} };
it("requires the reviewed preview and retains its identity after an uncertain save", async () => {
  const commit = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ card_id: "card", name: "合成角色", revision: 1, design: null, world_ids: [] });
  const client = { previewLibraryEditor: vi.fn().mockResolvedValue(preview), confirmLibraryCard: commit, discardLibraryPreview: vi.fn().mockResolvedValue({ discarded: true }) } as unknown as CoreClient;
  const onSaved = vi.fn();
  render(<CardAuthor client={client} editing={null} onSaved={onSaved} onClose={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("角色名称"), { target: { value: "合成角色" } });
  fireEvent.click(screen.getByRole("button", { name: "预览角色设定" }));
  const confirm = await screen.findByRole("button", { name: "确认保存到卡库" });
  expect(commit).not.toHaveBeenCalled();
  fireEvent.click(confirm);
  await screen.findByRole("alert");
  expect(commit).toHaveBeenCalledTimes(1);
  expect(onSaved).not.toHaveBeenCalled();
  await waitFor(() => expect((confirm as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(confirm);
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  expect(commit.mock.calls.map(call => call[0])).toEqual([preview, preview]);
});
