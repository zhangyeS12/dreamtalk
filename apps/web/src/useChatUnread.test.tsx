import { useRef } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import type { ChatMessage, CoreClient } from "@dreamtalk/api-client";
import { useConversationRead } from "./useChatUnread";
import { ThreadFrame } from "./world/chat/ThreadParts";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("acknowledges visible messages inside the actual chat scroller, not messages clipped above it", async () => {
  vi.spyOn(document, "hasFocus").mockReturnValue(true);
  const messages: ChatMessage[] = [1, 2].map(position => ({ message_id: `m${position}`, position, turn_id: "turn", conversation_id: "chat",
    sender_kind: "character", sender_id: "character", text: "合成回归消息", created_at_utc: "2026-10-29T00:00:00Z" }));
  const markConversationRead = vi.fn().mockResolvedValue({});
  const client = { markConversationRead } as unknown as CoreClient;
  function Chat() {
    const thread = useRef<HTMLElement>(null);
    useConversationRead(client, "world", "chat", messages);
    return <ThreadFrame label="回归会话" header={null} composer={null} staged={false} scrollRef={thread}>
      {messages.map(message => <div key={message.message_id} data-message-id={message.message_id}>{message.text}</div>)}
    </ThreadFrame>;
  }
  const { container } = render(<Chat />);
  const rect = (top: number, bottom: number) => ({ top, bottom, height: bottom - top } as DOMRect);
  vi.spyOn(container.querySelector("[data-chat-scroll]")!, "getBoundingClientRect").mockReturnValue(rect(100, 500));
  vi.spyOn(container.querySelector('[data-message-id="m1"]')!, "getBoundingClientRect").mockReturnValue(rect(20, 80));
  vi.spyOn(container.querySelector('[data-message-id="m2"]')!, "getBoundingClientRect").mockReturnValue(rect(200, 260));
  await waitFor(() => expect(markConversationRead).toHaveBeenCalledWith("world", "chat", 2));
  expect(markConversationRead).toHaveBeenCalledOnce();
});
