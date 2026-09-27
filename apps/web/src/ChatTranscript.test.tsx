import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, CoreRequestError, type ChatConversation, type ChatMessage } from "@dreamtalk/api-client";
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
  const client = { conversationMessages, directReplyAvailability: vi.fn().mockResolvedValue({ available: false }) } as unknown as CoreClient;
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} />);
  await screen.findByText("欢迎回来");
  expect(conversationMessages).toHaveBeenCalledWith("world-a", "conversation-a");
  const list = screen.getByRole("list");
  expect(list.querySelectorAll("li")[0]?.textContent).toContain("你好");
  expect(list.querySelectorAll("li")[1]?.textContent).toContain("欢迎回来");
  expect(screen.getByText(/尚未配置可用的聊天模型或路由/)).toBeTruthy();
});

it("does not reveal a late transcript from the previous world", async () => {
  let finishOld!: (messages: ChatMessage[]) => void;
  const old = new Promise<ChatMessage[]>(resolve => { finishOld = resolve; });
  const conversationMessages = vi.fn((worldId: string) => worldId === "world-a" ? old : Promise.resolve([]));
  const client = { conversationMessages, directReplyAvailability: vi.fn().mockResolvedValue({ available: false }) } as unknown as CoreClient;
  const renderThread = (worldId: string) => <ChatTranscript key={worldId} client={client} worldId={worldId} playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} />;
  const view = render(renderThread("world-a"));
  await waitFor(() => expect(conversationMessages).toHaveBeenCalledWith("world-a", "conversation-a"));
  view.rerender(renderThread("world-b"));
  await waitFor(() => expect(conversationMessages).toHaveBeenCalledWith("world-b", "conversation-a"));
  await act(async () => {
    finishOld([{ message_id: "private", turn_id: "turn-a", conversation_id: "conversation-a", position: 0, sender_kind: "player", sender_id: "player-a", text: "旧世界私聊", created_at_utc: "2026-09-24T10:00:00+00:00" }]);
  });
  expect(screen.queryByText("旧世界私聊")).toBeNull();
});

it("sends one durable turn, requests one reply, then refreshes the transcript", async () => {
  const player: ChatMessage = { message_id: "m1", turn_id: "t1", conversation_id: "conversation-a", position: 1, sender_kind: "player", sender_id: "player-a", text: "你好", created_at_utc: "2026-09-24T10:00:00+00:00" };
  const reply: ChatMessage = { ...player, message_id: "m2", position: 2, sender_kind: "character", sender_id: "character-a", text: "你好呀" };
  const conversationMessages = vi.fn().mockResolvedValueOnce([]).mockResolvedValue([player, reply]);
  const sendPlayerMessage = vi.fn().mockResolvedValue({ turn_id: "t1", token_ceiling: 50_000, status: "pending", message: player });
  const generateDirectReply = vi.fn().mockResolvedValue({ turn_id: "t1", state: "completed", player_message: player, reply });
  const client = { conversationMessages, sendPlayerMessage, generateDirectReply, directReplyAvailability: vi.fn().mockResolvedValue({ available: true }) } as unknown as CoreClient;
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} />);
  await waitFor(() => expect(screen.getByRole("textbox").hasAttribute("disabled")).toBe(false));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await screen.findByText("你好呀");
  expect(sendPlayerMessage).toHaveBeenCalledOnce();
  expect(sendPlayerMessage.mock.calls[0]?.slice(0, 4)).toEqual(["world-a", "conversation-a", "你好", 50_000]);
  expect(generateDirectReply).toHaveBeenCalledOnce();
  expect(generateDirectReply).toHaveBeenCalledWith("world-a", "conversation-a", "t1");
});

it("sends on Enter but not while composing Chinese text or inserting a newline", async () => {
  const sendPlayerMessage = vi.fn().mockRejectedValue(new CoreRequestError(422));
  const client = { conversationMessages: vi.fn().mockResolvedValue([]), sendPlayerMessage,
    directReplyAvailability: vi.fn().mockResolvedValue({ available: true }) } as unknown as CoreClient;
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} />);
  const draft = await screen.findByRole("textbox");
  await waitFor(() => expect(draft).toHaveProperty("disabled", false));
  fireEvent.change(draft, { target: { value: "你好" } });
  fireEvent.keyDown(draft, { key: "Enter", isComposing: true });
  fireEvent.keyDown(draft, { key: "Enter", keyCode: 229 });
  fireEvent.keyDown(draft, { key: "Enter", shiftKey: true });
  expect(sendPlayerMessage).not.toHaveBeenCalled();
  fireEvent.keyDown(draft, { key: "Enter" });
  await waitFor(() => expect(sendPlayerMessage).toHaveBeenCalledOnce());
});

it("checks an uncertain reply without replaying the model call", async () => {
  const player: ChatMessage = { message_id: "m1", turn_id: "t1", conversation_id: "conversation-a", position: 1, sender_kind: "player", sender_id: "player-a", text: "你好", created_at_utc: "2026-09-24T10:00:00+00:00" };
  const sendPlayerMessage = vi.fn().mockResolvedValue({ turn_id: "t1", token_ceiling: 50_000, status: "pending", message: player });
  const generateDirectReply = vi.fn().mockRejectedValue(new Error("network failure"));
  const directTurn = vi.fn().mockResolvedValue({ turn_id: "t1", state: "claimed", player_message: player, reply: null });
  const client = { conversationMessages: vi.fn().mockResolvedValue([player]), sendPlayerMessage, generateDirectReply, directTurn, directReplyAvailability: vi.fn().mockResolvedValue({ available: true }) } as unknown as CoreClient;
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} />);
  await waitFor(() => expect(screen.getByRole("textbox").hasAttribute("disabled")).toBe(false));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await screen.findByText(/这轮回复未完成/);
  expect(generateDirectReply).toHaveBeenCalledOnce();
  expect(directTurn).toHaveBeenCalledOnce();
});

it("explains a budget denial without replaying an already saved player message", async () => {
  const player: ChatMessage = { message_id: "m1", turn_id: "t1", conversation_id: "conversation-a", position: 1, sender_kind: "player", sender_id: "player-a", text: "你好", created_at_utc: "2026-09-24T10:00:00+00:00" };
  const sendPlayerMessage = vi.fn().mockResolvedValue({ turn_id: "t1", token_ceiling: 50_000, status: "pending", message: player });
  const generateDirectReply = vi.fn().mockRejectedValue(new CoreRequestError(422));
  const client = { conversationMessages: vi.fn().mockResolvedValue([player]), sendPlayerMessage,
    generateDirectReply, directTurn: vi.fn().mockResolvedValue({ state: "pending" }),
    directReplyAvailability: vi.fn().mockResolvedValue({ available: true }) } as unknown as CoreClient;
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} />);
  await waitFor(() => expect(screen.getByRole("textbox").hasAttribute("disabled")).toBe(false));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  expect(await screen.findByText(/这轮回复未获预算授权/)).toBeTruthy();
  expect(sendPlayerMessage).toHaveBeenCalledOnce();
  expect(generateDirectReply).toHaveBeenCalledOnce();
});

it("releases a rejected message for editing but reuses identity after an uncertain save", async () => {
  const sendPlayerMessage = vi.fn()
    .mockRejectedValueOnce(new CoreRequestError(422))
    .mockRejectedValueOnce(new Error("connection lost"))
    .mockRejectedValueOnce(new Error("connection lost"));
  const client = { conversationMessages: vi.fn().mockResolvedValue([]), sendPlayerMessage,
    directReplyAvailability: vi.fn().mockResolvedValue({ available: true }) } as unknown as CoreClient;
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} />);
  const draft = await screen.findByRole("textbox");
  await waitFor(() => expect(draft).toHaveProperty("disabled", false));
  fireEvent.change(draft, { target: { value: "原文" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await screen.findByText(/消息未保存/);
  expect(draft).toHaveProperty("disabled", false);
  fireEvent.change(draft, { target: { value: "修改后" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await screen.findByText(/保存结果尚未确认/);
  expect(draft).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByRole("button", { name: "重试保存" }));
  await waitFor(() => expect(sendPlayerMessage).toHaveBeenCalledTimes(3));
  expect(sendPlayerMessage.mock.calls[1]?.slice(2)).toEqual(sendPlayerMessage.mock.calls[2]?.slice(2));
  expect(sendPlayerMessage.mock.calls[0]?.[4]).not.toBe(sendPlayerMessage.mock.calls[1]?.[4]);
});
