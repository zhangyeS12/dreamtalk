import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { CoreClient, type ChatMessage, type ChatPathPreview, type ChatPathSnapshot } from "@dreamtalk/api-client";
import { ChatPathTools } from "./ChatPathTools";
import { useChatPaths } from "./useChatPaths";
import { useTranscriptPages } from "./useTranscriptPages";
import { LoreAdvancedControls } from "./LoreAdvancedControls";

afterEach(cleanup);
const message: ChatMessage = { message_id: "reply", conversation_id: "chat", turn_id: "turn", position: 2,
  sender_kind: "character", sender_id: "npc", text: "original", created_at_utc: "2026-01-01T00:00:00Z" };
const snapshot: ChatPathSnapshot = { revision: 0, active: { path_id: "main", name: "主线", kind: "main", parent_id: null, fork_message_id: null, created_at: "2026-01-01T00:00:00Z" }, paths: [], next_before: null };

it("requires preview confirmation, reuses an uncertain save and generates only once", async () => {
  const onGenerate = vi.fn().mockResolvedValue(undefined);
  const commit = vi.fn().mockRejectedValueOnce(new Error("network uncertain")).mockResolvedValue({ path_id: "alternative", revision: 1, turn_id: "candidate-turn" });
  const preview = vi.fn().mockImplementation(async (_world, _conversation, draft) => ({ draft, original_text: "original", reviewed_hash: "a".repeat(64), calls_model: true, creates_path: true } satisfies ChatPathPreview));
  const api = { chatPaths: vi.fn().mockResolvedValue(snapshot), previewChatPath: preview, commitChatPath: commit } as unknown as CoreClient;
  function Harness() {
    const paths = useChatPaths(api, "world", "chat");
    return <ChatPathTools client={api} worldId="world" conversationId="chat" paths={paths} blocked={false} tokenCeiling={10000} action={{ action: "candidate", message }} onAction={() => {}} onGenerate={onGenerate} />;
  }
  render(<Harness />);
  const previewButton = await screen.findByRole("button", { name: "预览修改" });
  expect(document.activeElement).toBe(screen.getByLabelText("聊天路线"));
  fireEvent.click(previewButton);
  expect(commit).not.toHaveBeenCalled(); expect(onGenerate).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: "确认保存并生成" }));
  await screen.findByText(/操作未确认/);
  fireEvent.click(screen.getByRole("button", { name: "确认保存并生成" }));
  await waitFor(() => expect(onGenerate).toHaveBeenCalledExactlyOnceWith("candidate-turn"));
  expect(commit.mock.calls[0][2].request_id).toBe(commit.mock.calls[1][2].request_id);
});

it("resets transcript pages on a route switch and rejects a late older-page result", async () => {
  let finishOld!: (value: { items: ChatMessage[]; next_before_position: null }) => void;
  const delayed = new Promise<{ items: ChatMessage[]; next_before_position: null }>(resolve => { finishOld = resolve; });
  const api = { conversationMessagePage: vi.fn().mockResolvedValueOnce({ items: [message], next_before_position: 2 })
    .mockReturnValueOnce(delayed).mockResolvedValue({ items: [{ ...message, message_id: "other", position: 4, text: "other route" }], next_before_position: null }) } as unknown as CoreClient;
  const hook = renderHook(({ path }) => useTranscriptPages(api, "world", "chat", 0, false, path), { initialProps: { path: "main" } });
  await waitFor(() => expect(hook.result.current.messages?.[0].text).toBe("original"));
  let older!: Promise<void>;
  act(() => { older = hook.result.current.loadOlder(() => {}); });
  hook.rerender({ path: "branch" });
  await waitFor(() => expect(hook.result.current.messages?.[0].text).toBe("other route"));
  await act(async () => { finishOld({ items: [{ ...message, message_id: "hidden-old", position: 1, text: "hidden old route" }], next_before_position: null }); await older; });
  expect(hook.result.current.messages?.map(row => row.text)).toEqual(["other route"]);
});

it("offers bounded lore controls without changing an inherited setting implicitly", () => {
  const change = vi.fn();
  render(<LoreAdvancedControls onChange={change} />);
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByLabelText("启用概率触发"));
  expect(change).toHaveBeenLastCalledWith(expect.objectContaining({ use_probability: true, probability: 100, scan_depth: null, insertion_depth: null }));
  fireEvent.change(screen.getByLabelText(/历史插入深度/), { target: { value: "0" } });
  expect(change).toHaveBeenLastCalledWith(expect.objectContaining({ insertion_depth: 0 }));
});
