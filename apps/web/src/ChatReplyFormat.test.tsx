import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { CoreClient, CoreRequestError, type ChatConversation, type ChatMessage } from "@dreamtalk/api-client";
import { ChatTranscript } from "./ChatTranscript";
import { chatFailureNeedsModelSettings, chatReplyFailureFeedback } from "./chatFeedback";
import { withChatReads } from "./testClient";
import { useReplyStream } from "./useReplyStream";

afterEach(cleanup);

it.each(["direct", "group"] as const)("reports a %s format failure without blaming settings", kind => {
  const failure = new CoreRequestError(502, "chat_reply_format_invalid");
  const feedback = chatReplyFailureFeedback(failure, kind);
  expect(feedback).toContain("未能解析出完整的角色正文");
  expect(feedback).toContain("可能已产生用量");
  expect(feedback).toContain("系统不会自动重试");
  expect(feedback).not.toContain("请检查模型设置");
  expect(chatFailureNeedsModelSettings(failure)).toBe(false);
  expect(chatFailureNeedsModelSettings(new CoreRequestError(502, "chat_provider_authentication"))).toBe(true);
});

it("keeps a saved player message and offers no misleading settings action or automatic retry", async () => {
  const conversation: ChatConversation = {
    conversation_id: "conversation-a", player_id: "player-a", character_id: "character-a",
    root_import_id: "import-a", character_name: "角色甲", kind: "direct",
  };
  const message: ChatMessage = {
    message_id: "player-message", turn_id: "turn-a", conversation_id: "conversation-a", position: 1,
    sender_kind: "player", sender_id: "player-a", text: "合成问题", created_at_utc: "2026-01-01T00:00:00Z",
  };
  const streamChatReply = vi.fn().mockRejectedValue(new CoreRequestError(502, "chat_reply_format_invalid"));
  const client = withChatReads({
    conversationMessagePage: vi.fn().mockResolvedValue({ items: [message], next_before_position: null }),
    directReplyAvailability: vi.fn().mockResolvedValue({ available: true }),
    sendPlayerMessage: vi.fn().mockResolvedValue({ turn_id: "turn-a", message }),
    directTurn: vi.fn().mockResolvedValue({ state: "claimed" }), streamChatReply,
  } as unknown as CoreClient);
  const settings = vi.fn();
  render(<ChatTranscript client={client} worldId="world-a" playerId="player-a" conversation={conversation} tokenCeiling={50_000} onBack={() => {}} onModelSettings={settings} />);
  const draft = screen.getByRole("textbox");
  await waitFor(() => expect(draft).toHaveProperty("disabled", false));
  fireEvent.change(draft, { target: { value: "合成问题" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  expect(await screen.findByText(/未能解析出完整的角色正文/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "打开当前世界模型设置" })).toBeNull();
  expect(settings).not.toHaveBeenCalled();
  expect(client.sendPlayerMessage).toHaveBeenCalledOnce();
  expect(streamChatReply).toHaveBeenCalledOnce();
  expect(client.directTurn).toHaveBeenCalledOnce();
  expect(screen.getByText("合成问题")).toBeTruthy();
});

it("replaces a provisional preview with the committed message once", async () => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const message: ChatMessage = {
    message_id: "final-message", turn_id: "turn-a", conversation_id: "conversation-a", position: 2,
    sender_kind: "character", sender_id: "character-a", text: "最终完整正文", created_at_utc: "2026-01-01T00:00:00Z",
  };
  const streamChatReply = vi.fn<CoreClient["streamChatReply"]>(async (...args) => {
    const emit = args[4];
    emit({ kind: "replying", speaker_id: "character-a" });
    emit({ kind: "delta", speaker_id: "character-a", text: "临时预览" });
    await gate;
    emit({ kind: "message", message });
  });
  const client = { streamChatReply } as unknown as CoreClient;
  const accepted = vi.fn();
  const hook = renderHook(useReplyStream);
  let pending!: Promise<void>;
  await act(async () => {
    pending = hook.result.current.run(client, "world-a", "conversation-a", "turn-a", "direct", ["character-a"], accepted);
    await Promise.resolve();
  });
  expect(hook.result.current.draft?.text).toBe("临时预览");
  await act(async () => { release(); await pending; });
  expect(accepted).toHaveBeenCalledExactlyOnceWith(message);
  expect(hook.result.current.draft).toBeNull();
  expect(streamChatReply).toHaveBeenCalledOnce();
});
