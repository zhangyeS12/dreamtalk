import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CoreClient, type WorldContentItem } from "@dreamtalk/api-client";
import { WorldContacts, WorldImports } from "./WorldContent";

afterEach(cleanup);

it("shows the imported greeting as source preview without creating a chat message", async () => {
  const item: WorldContentItem = {
    import_id: "card-a", replaces_import_id: null, kind: "character", reviewed_hash: "hash",
    characters: [{
      id: "definition-a", name: "角色甲", description: "", personality: "", background: "",
      scenario: "", speech_guidance: "", creator_notes: "", tags: [], example_dialogue: [],
      authored_instructions: { character_card: { first_mes: "你好，{{user}}。" } },
    }],
    lorebooks: [], entries: [],
  };
  const onOpenChat = vi.fn();
  const client = { worldContent: vi.fn().mockResolvedValue([item]), socialSnapshot: vi.fn().mockResolvedValue({ factions: [], characters: [], memberships: [], connections: [] }), listActivityLocations: vi.fn().mockResolvedValue([]), listActivityCharacters: vi.fn().mockResolvedValue({ items: [], has_more: false }) } as unknown as CoreClient;
  render(<WorldContacts client={client} worldId="world-a" onSettings={() => {}}
    onIdentity={() => {}} onOpenChat={onOpenChat} canOpenChat openingChat={false} />);
  fireEvent.click(await screen.findByRole("button", { name: "角色甲查看角色资料与阵营" }));
  expect(screen.getByText("你好，{{user}}。")).toBeTruthy();
  expect(screen.getByText("回复可参考其语气；不会自动作为消息发送。")).toBeTruthy();
  expect(onOpenChat).not.toHaveBeenCalled();
});

it("keeps imported lore hidden until the current world explicitly exposes an entry", async () => {
  const item: WorldContentItem = {
    import_id: "book-a", replaces_import_id: null, kind: "lorebook", reviewed_hash: "hash",
    characters: [], lorebooks: [{ id: "collection-a", name: "世界资料", description: "" }],
    entries: [{ id: "entry-a", title: "城镇", keywords: [], content: "城镇背景", enabled: true, common: false }],
  };
  const setCommonLore = vi.fn().mockImplementation(async () => { item.entries[0].common = true; return { common: true }; });
  const client = { worldContent: vi.fn().mockResolvedValue([item]), setCommonLore } as unknown as CoreClient;
  render(<WorldImports client={client} worldId="world-a" onlyKind="lorebook" />);
  fireEvent.click(await screen.findByText("世界资料 · 世界书"));
  fireEvent.click(screen.getByText("世界书条目（1）"));
  await new Promise(resolve => setTimeout(resolve, 0));
  const exposure = screen.getByLabelText(/^角色可见范围/);
  expect((exposure as HTMLSelectElement).value).toBe("hidden");
  fireEvent.change(exposure, { target: { value: "common" } });
  expect(await screen.findByText("已保存并核对：公共背景。无需再保存世界书。")).toBeTruthy();
  expect(setCommonLore).toHaveBeenCalledWith("world-a", "book-a", "entry-a", true);
});
