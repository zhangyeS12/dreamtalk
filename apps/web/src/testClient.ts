import { vi } from "vitest";
import type { CoreClient } from "@dreamtalk/api-client";

// Read-only UI ports added after the original chat fixtures. Never replace a
// method supplied by the test, and never supply generation or write operations.
export function withChatReads(client: CoreClient): CoreClient {
  const defaults = {
    replyRecovery: vi.fn().mockResolvedValue({ can_generate: false, can_recover: false, reason: "chat_recovery_has_replies" }),
    chatUnread: vi.fn().mockResolvedValue({ player_id: "player-a", items: [] }),
  };
  for (const [name, value] of Object.entries(defaults)) {
    if (!(name in client)) Object.assign(client, { [name]: value });
  }
  if (typeof Reflect.get(client, "streamChatReply") !== "function") Object.assign(client, {
    // Adapt the existing committed-reply fixtures to the current SSE UI port.
    streamChatReply: vi.fn(async (world: string, conversation: string, turn: string, kind: "direct" | "group", receive: (event: unknown) => void) => {
      const result = kind === "direct" ? await client.generateDirectReply(world, conversation, turn) : await client.generateGroupReply(world, conversation, turn);
      const messages = "replies" in result ? result.replies : result.reply ? [result.reply] : [];
      for (const message of messages) receive({ kind: "message", message });
    }),
  });
  return client;
}
