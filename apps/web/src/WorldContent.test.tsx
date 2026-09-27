import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CoreClient, type WorldContentItem } from "@dreamtalk/api-client";
import { WorldContacts } from "./WorldContent";

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
  const client = { worldContent: vi.fn().mockResolvedValue([item]) } as unknown as CoreClient;
  render(<WorldContacts client={client} worldId="world-a" onSettings={() => {}}
    onIdentity={() => {}} onOpenChat={onOpenChat} canOpenChat openingChat={false} />);
  fireEvent.click(await screen.findByRole("button", { name: "角色甲查看角色资料" }));
  expect(screen.getByText("你好，{{user}}。")).toBeTruthy();
  expect(screen.getByText("回复可参考其语气；不会自动作为消息发送。")).toBeTruthy();
  expect(onOpenChat).not.toHaveBeenCalled();
});
