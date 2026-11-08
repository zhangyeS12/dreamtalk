import { vi } from "vitest";
import type { CoreClient } from "@dreamtalk/api-client";

// Read-only UI ports added after the original chat fixtures. Never replace a
// method supplied by the test, and never supply generation or write operations.
export function withChatReads(client: CoreClient): CoreClient {
  const defaults = {
    chatPaths: vi.fn(async (_world: string, conversation: string) => ({ active: { path_id: conversation, parent_id: null, name: "主线", kind: "main", created_at: "2026-01-01T00:00:00Z", fork_message_id: null }, revision: 0, paths: [], next_before: null })),
    replyRecovery: vi.fn().mockResolvedValue({ can_generate: false, can_recover: false, reason: "chat_recovery_has_replies" }),
    chatUnread: vi.fn().mockResolvedValue({ player_id: "player-a", items: [] }),
    chatVisuals: vi.fn().mockResolvedValue({ common_background_digest: null, character_backgrounds: {}, expressions: [] }),
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
