import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, type ChatConversation, type ChatMessage } from "@livingworld/api-client";
import { ChatTranscript } from "./ChatTranscript";

afterEach(cleanup);

const conversation: ChatConversation = {
  conversation_id: "conversation-a", player_id: "player-a", character_id: "character-a",
  root_import_id: "import-a", character_name: "角色甲", kind: "direct",
};

it("shows committed messages in transcript order without turning them into world events", async () => {
  const rows: ChatMessage[] = [
    { message_id: "message-a", turn_id: "turn-a", conversation_id: "conversation-a", position: 0, sender_kind: "player", sender_id: "player-a", text: "你好", created_at_utc: "2026-09-24T10:00:00+00:00" },
    { message_id: "message-b", turn_id: "turn-a", conversation_id: "conversation-a", position: 1, sender_kind: "character", sender_id: "character-a", text: "欢迎回来", created_at_utc: "2026-09-24T10:00:01+00:00" },
  ];
  const conversationMessages = vi.fn().mockResolvedValue(rows);
  const client = { conversationMessages } as unknown as CoreClient;
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} onBack={() => {}} />);
  await screen.findByText("欢迎回来");
  expect(conversationMessages).toHaveBeenCalledWith("world-a", "conversation-a");
  const list = screen.getByRole("list");
  expect(list.querySelectorAll("li")[0]?.textContent).toContain("你好");
  expect(list.querySelectorAll("li")[1]?.textContent).toContain("欢迎回来");
  expect(screen.getByText("消息发送功能尚未开放。")).toBeTruthy();
});

it("does not reveal a late transcript from the previous world", async () => {
  let finishOld!: (messages: ChatMessage[]) => void;
  const old = new Promise<ChatMessage[]>(resolve => { finishOld = resolve; });
  const conversationMessages = vi.fn((worldId: string) => worldId === "world-a" ? old : Promise.resolve([]));
  const client = { conversationMessages } as unknown as CoreClient;
  const renderThread = (worldId: string) => <ChatTranscript key={worldId} client={client} worldId={worldId} playerId="player-a" conversation={conversation} onBack={() => {}} />;
  const view = render(renderThread("world-a"));
  await waitFor(() => expect(conversationMessages).toHaveBeenCalledWith("world-a", "conversation-a"));
  view.rerender(renderThread("world-b"));
  await waitFor(() => expect(conversationMessages).toHaveBeenCalledWith("world-b", "conversation-a"));
  await act(async () => {
    finishOld([{ message_id: "private", turn_id: "turn-a", conversation_id: "conversation-a", position: 0, sender_kind: "player", sender_id: "player-a", text: "旧世界私聊", created_at_utc: "2026-09-24T10:00:00+00:00" }]);
  });
  expect(screen.queryByText("旧世界私聊")).toBeNull();
});
