import { expect, it, vi } from "vitest";
import { CoreClient, type ChatReplyProgress } from "./index";

const world = "11111111-1111-4111-8111-111111111111";
const conversation = "22222222-2222-4222-8222-222222222222";
const turn = "33333333-3333-4333-8333-333333333333";
const speaker = "44444444-4444-4444-8444-444444444444";
const message = {
  message_id: "55555555-5555-4555-8555-555555555555", turn_id: turn,
  conversation_id: conversation, sender_kind: "character", sender_id: speaker,
  text: "SECRET public", position: 2, created_at_utc: "2026-11-07T00:00:00Z",
  privacy: [{ start: 0, end: 6, character_id: speaker }],
  privacy_fallback: false,
};
const frame = (kind: string, extra: object = {}) => ({ turn_id: turn, kind, ...extra });
function stream(frames: object[]) {
  const fetcher = vi.fn().mockResolvedValue(new Response(
    frames.map(value => `data: ${JSON.stringify(value)}\n\n`).join(""),
    { headers: { "Content-Type": "text/event-stream" } },
  ));
  const client = new CoreClient({ endpoint: "http://127.0.0.1:49152", token: "synthetic", generation: "test" }, fetcher);
  return { fetcher, client };
}

it("preserves private audiences in the committed message with one authenticated call", async () => {
  const { client, fetcher } = stream([
    frame("preparing"), frame("replying", { speaker_id: speaker }),
    frame("message", { message }), frame("completed"),
  ]);
  const received: ChatReplyProgress[] = [];
  await client.streamChatReply(world, conversation, turn, "group", value => received.push(value), new AbortController().signal);
  expect(received.at(-1)).toEqual({ kind: "message", message });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer synthetic");
});

it.each([
  frame("message", { message: { ...message, turn_id: world } }),
  frame("message", { message: { ...message, conversation_id: world } }),
  frame("message", { message: { ...message, sender_id: world } }),
  frame("delta", { speaker_id: world, text: "wrong speaker" }),
  frame("completed", { turn_id: world }),
])("rejects mismatched turn, conversation or speaker without repeating the call", async bad => {
  const { client, fetcher } = stream([frame("replying", { speaker_id: speaker }), bad]);
  await expect(client.streamChatReply(world, conversation, turn, "group", () => undefined, new AbortController().signal))
    .rejects.toMatchObject({ code: "chat_reply_invalid" });
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("keeps a prior committed group message when a later provider error ends the stream", async () => {
  const { client, fetcher } = stream([
    frame("replying", { speaker_id: speaker }), frame("message", { message }),
    frame("error", { status: 502, code: "chat_reply_format_invalid" }),
  ]);
  const received: ChatReplyProgress[] = [];
  await expect(client.streamChatReply(world, conversation, turn, "group", value => received.push(value), new AbortController().signal))
    .rejects.toMatchObject({ code: "chat_reply_format_invalid" });
  expect(received.filter(value => value.kind === "message")).toEqual([{ kind: "message", message }]);
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it.each([false, true])("rejects an uncommitted final speaker when completion is %s", async completed => {
  const frames = [frame("replying", { speaker_id: speaker }), frame("delta", { speaker_id: speaker, text: "unfinished" })];
  if (completed) frames.push(frame("completed"));
  const { client, fetcher } = stream(frames);
  await expect(client.streamChatReply(world, conversation, turn, "direct", () => undefined, new AbortController().signal))
    .rejects.toMatchObject({ code: "chat_stream_interrupted" });
  expect(fetcher).toHaveBeenCalledTimes(1);
});
