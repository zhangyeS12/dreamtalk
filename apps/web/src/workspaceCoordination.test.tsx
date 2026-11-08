import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { CoreClient, KnownWorldEvent, SelectedPlayerState, WorldSettings } from "@dreamtalk/api-client";
import { useWorldIdentity } from "./useWorldIdentity";
import { useWorldEvents } from "./useWorldEvents";
import { useWorkspaceActions } from "./useWorkspaceActions";
import { useWorkspaceWorld } from "./useWorkspaceWorld";

afterEach(() => { cleanup(); vi.useRealTimers(); });
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const selected = (player: string): SelectedPlayerState => ({ player_id: player,
  availability: "available", presence_revision: 0 });

it("keeps the new world's identity when the old read completes late", async () => {
  const old = deferred<SelectedPlayerState>();
  const client = { listPlayers: vi.fn().mockResolvedValue([]), selectedPlayer: vi.fn((world: string) =>
    world === "old" ? old.promise : Promise.resolve(selected("new-player"))) } as unknown as CoreClient;
  const error = vi.fn();
  const { result, rerender } = renderHook(({ world }) => useWorldIdentity(client, world, error), { initialProps: { world: "old" } });
  rerender({ world: "new" });
  await waitFor(() => expect(result.current.selectedPlayer).toBe("new-player"));
  await act(async () => old.resolve(selected("old-player")));
  expect(result.current.selectedPlayer).toBe("new-player");
  expect(error).not.toHaveBeenCalled();
});

it("does not display errors from the previous world's identity request", async () => {
  const old = deferred<SelectedPlayerState>();
  const client = { listPlayers: vi.fn().mockResolvedValue([]), selectedPlayer: vi.fn((world: string) =>
    world === "old" ? old.promise : Promise.resolve(selected("new-player"))) } as unknown as CoreClient;
  const error = vi.fn();
  const { rerender } = renderHook(({ world }) => useWorldIdentity(client, world, error), { initialProps: { world: "old" } });
  rerender({ world: "new" });
  await act(async () => old.reject(new Error("old connection failed")));
  expect(error).not.toHaveBeenCalled();
});

it("creates only a local event discussion draft and clears it when identity changes", () => {
  const client = { knownEvents: vi.fn() } as unknown as CoreClient;
  const error = vi.fn(), display = (raw: string) => raw;
  const event: KnownWorldEvent = { event_id: "event", title: "节日", occurred_at: "60", observed_at: "60", ledger_position: 1 };
  const { result, rerender } = renderHook(({ player }) => useWorldEvents(client, "world", player, error, display),
    { initialProps: { player: "a" } });
  act(() => result.current.setTopicEvent(event));
  act(() => { expect(result.current.discuss("chat")).toBe(true); });
  expect(result.current.suggestedFor("chat")).toContain("节日");
  expect(result.current.suggestedFor("other-chat")).toBeNull();
  expect(client.knownEvents).not.toHaveBeenCalled();
  rerender({ player: "b" });
  expect(result.current.suggestedFor("chat")).toBeNull();
  expect(result.current.topicEvent).toBeNull();
});

it("allows only one pending user action and ignores late completion after leaving", async () => {
  const pending = deferred<void>(), action = vi.fn(() => pending.promise), second = vi.fn();
  const { result, unmount } = renderHook(() => useWorkspaceActions());
  let completed!: Promise<void>;
  act(() => { completed = result.current.run(action, "saved"); void result.current.run(second, "duplicate"); });
  expect(result.current.busy).toBe(true);
  expect(action).toHaveBeenCalledTimes(1);
  expect(second).not.toHaveBeenCalled();
  unmount();
  await act(async () => { pending.resolve(); await completed; });
  expect(result.current.notice).toBe("");
});

it("preserves an edited clock scale during polling until the canonical scale changes", async () => {
  vi.useFakeTimers();
  const world: WorldSettings = { world_id: "world", name: "World", clock_state: "running",
    time_scale: "1", world_time: "0", runtime_state: "running" };
  const client = { listProductWorlds: vi.fn().mockResolvedValue([world]) } as unknown as CoreClient;
  const error = vi.fn();
  const { result } = renderHook(() => useWorkspaceWorld(client, "world", error));
  await act(async () => { await Promise.resolve(); });
  act(() => result.current.setScale("7"));
  await act(async () => vi.advanceTimersByTimeAsync(2_000));
  expect(result.current.scale).toBe("7");
  vi.mocked(client.listProductWorlds).mockResolvedValue([{ ...world, time_scale: "2" }]);
  await act(async () => vi.advanceTimersByTimeAsync(2_000));
  expect(result.current.scale).toBe("2");
});
