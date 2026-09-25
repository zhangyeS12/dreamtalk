import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, type GroupChatConversation, type WorldContentItem } from "@livingworld/api-client";
import { GroupChatSetup } from "./GroupChat";

afterEach(cleanup);

const contact = (id: string, name: string): WorldContentItem => ({
  import_id: id, replaces_import_id: null, kind: "character", reviewed_hash: "hash",
  characters: [{ id, name, description: "", personality: "", background: "", scenario: "", speech_guidance: "", creator_notes: "", tags: [], example_dialogue: [], authored_instructions: {} }],
  lorebooks: [], entries: [],
});

it("retries an uncertain group create with the same request identity and member set", async () => {
  const group: GroupChatConversation = { conversation_id: "group-a", player_id: "player-a", kind: "group", participants: [] };
  const createGroupConversation = vi.fn().mockRejectedValueOnce(new Error("network_uncertain")).mockResolvedValue(group);
  const onCreated = vi.fn();
  const client = {
    worldContent: vi.fn().mockResolvedValue([contact("card-a", "角色甲"), contact("card-b", "角色乙")]),
    createGroupConversation,
  } as unknown as CoreClient;
  render(<GroupChatSetup client={client} worldId="world-a" onCreated={onCreated} onBack={() => {}} />);
  fireEvent.click(await screen.findByRole("checkbox", { name: "角色甲" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "角色乙" }));
  fireEvent.click(screen.getByRole("button", { name: "创建群聊" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "群聊保存结果尚未确认。可以重试同一次创建，不会重复建立会话。");
  expect(screen.getByRole("checkbox", { name: "角色甲" })).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByRole("button", { name: "重试创建" }));
  await waitFor(() => expect(onCreated).toHaveBeenCalledWith(group));
  expect(createGroupConversation).toHaveBeenCalledTimes(2);
  expect(createGroupConversation.mock.calls[1]).toEqual(createGroupConversation.mock.calls[0]);
});
