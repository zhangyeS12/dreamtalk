import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ChatConversation, CoreClient, GroupChatConversation } from "@dreamtalk/api-client";
import { useWorkspaceNavigation } from "./useWorkspaceNavigation";
import { useWorkspaceDrafts } from "./useWorkspaceDrafts";
import { useConversationDirectory } from "./useConversationDirectory";

afterEach(cleanup);
const direct: ChatConversation = { conversation_id: "direct", player_id: "player", character_id: "a", root_import_id: "card-a", character_name: "A", kind: "direct" };
const group: GroupChatConversation = { conversation_id: "group", player_id: "player", kind: "group", participants: [] };

it("keeps visited pages mounted and retains other unsaved editors", () => {
  const { result } = renderHook(() => ({ nav: useWorkspaceNavigation("chats"), drafts: useWorkspaceDrafts() }));
  const callback = result.current.drafts.onDirty.chat;
  act(() => { result.current.nav.setTab("me"); result.current.drafts.onDirty.chat(true); result.current.drafts.onDirty.model(true); });
  act(() => { result.current.nav.setTab("contacts"); result.current.drafts.onDirty.chat(false); });
  expect(result.current.nav.meVisited).toBe(true);
  expect(result.current.nav.contactsVisited).toBe(true);
  expect(result.current.drafts.onDirty.chat).toBe(callback);
  expect(result.current.drafts.hasDrafts).toBe(true);
  expect(result.current.drafts.dirty.model).toBe(true);
});

it("retains a just-opened chat when an older directory read finishes and selects only one thread", async () => {
  let finish!: (items: ChatConversation[]) => void;
  const client = { conversations: vi.fn(() => new Promise<ChatConversation[]>(resolve => { finish = resolve; })),
    groupConversations: vi.fn().mockResolvedValue([]) } as unknown as CoreClient;
  const error = vi.fn();
  const { result } = renderHook(() => useConversationDirectory(client, "world", "player", true, 0, "", error));
  act(() => result.current.opened({ worldId: "world", playerId: "player" }, direct));
  await act(async () => finish([]));
  await waitFor(() => expect(result.current.conversationsLoading).toBe(false));
  expect(result.current.conversations).toEqual([direct]);
  act(() => result.current.created({ worldId: "world", playerId: "player" }, group));
  expect(result.current.selectedGroupId).toBe("group");
  expect(result.current.selectedConversationId).toBeNull();
  expect(error).not.toHaveBeenCalled();
});

it("ignores a delayed directory result after changing world and player", async () => {
  let finishOld!: (items: ChatConversation[]) => void;
  const client = { conversations: vi.fn((world: string) => world === "old" ? new Promise<ChatConversation[]>(resolve => { finishOld = resolve; }) : Promise.resolve([])),
    groupConversations: vi.fn().mockResolvedValue([]) } as unknown as CoreClient;
  const error = vi.fn();
  const { result, rerender } = renderHook(({ world, player }) => useConversationDirectory(client, world, player, true, 0, "", error),
    { initialProps: { world: "old", player: "old-player" } });
  rerender({ world: "new", player: "new-player" });
  await act(async () => finishOld([direct]));
  await waitFor(() => expect(result.current.conversationsLoading).toBe(false));
  expect(result.current.conversations).toEqual([]);
  expect(result.current.groups).toEqual([]);
  expect(error).not.toHaveBeenCalled();
});
