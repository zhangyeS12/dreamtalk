import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, type GroupChatConversation, type WorldContentItem } from "@livingworld/api-client";
import { GroupChatDetails, GroupChatSetup } from "./GroupChat";

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

it("sends one group turn and shows the committed character reply", async () => {
  const group: GroupChatConversation = {
    conversation_id: "group-a", player_id: "player-a", kind: "group",
    participants: [{ character_id: "character-a", root_import_id: "card-a", character_name: "角色甲" }, { character_id: "character-b", root_import_id: "card-b", character_name: "角色乙" }],
  };
  const player = { message_id: "m1", turn_id: "t1", conversation_id: "group-a", position: 1, sender_kind: "player" as const, sender_id: "player-a", text: "@角色乙 你好", created_at_utc: "2026-01-01T00:00:00Z" };
  const reply = { ...player, message_id: "m2", position: 2, sender_kind: "character" as const, sender_id: "character-b", text: "你好" };
  const sendGroupMessage = vi.fn().mockResolvedValue({ turn_id: "t1", token_ceiling: 500, status: "pending", message: player });
  const generateGroupReply = vi.fn().mockResolvedValue({ turn_id: "t1", state: "completed", token_ceiling: 500, player_message: player, replies: [reply] });
  const conversationMessages = vi.fn().mockResolvedValueOnce([]).mockResolvedValue([player, reply]);
  const client = { conversationMessages, sendGroupMessage, generateGroupReply, groupReplyAvailability: vi.fn().mockResolvedValue({ available: true }) } as unknown as CoreClient;
  render(<GroupChatDetails client={client} worldId="world-a" playerId="player-a" group={group} tokenCeiling={500} onBack={() => {}} />);
  const draft = await screen.findByRole("textbox", { name: "发送群聊消息" });
  await waitFor(() => expect(draft).toHaveProperty("disabled", false));
  fireEvent.change(draft, { target: { value: "@角色乙 你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(generateGroupReply).toHaveBeenCalledWith("world-a", "group-a", "t1"));
  expect(sendGroupMessage.mock.calls[0]?.slice(0, 4)).toEqual(["world-a", "group-a", "@角色乙 你好", 500]);
  expect(await screen.findByText("你好")).toBeTruthy();
  expect(screen.getByText("角色乙")).toBeTruthy();
});
