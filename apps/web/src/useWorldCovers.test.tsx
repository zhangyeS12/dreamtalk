import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { CoreClient, WorldCover } from "@dreamtalk/api-client";
import { useWorldCovers } from "./useWorldCovers";
import { designFor } from "./world/archive/bookDesign";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each(["spine", "back"] as const)("keeps a designed %s image without a front image, including after refresh", async face => {
  const revoke = vi.fn();
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = vi.fn(() => "blob:face");
    static revokeObjectURL = revoke;
  });
  const image = { digest: "a".repeat(64), width: 980, height: 1430, size: 10, media_type: "image/webp" };
  const cover: WorldCover = { world_id: "world-a", mode: "text", title: "世界甲", show_title: true, revision: 1,
    faces: { [face]: { source: image, display: image, crop: { x: 0, y: 0, width: 100, height: 100, rotation: 0 } } },
    design: designFor(undefined, "世界甲") };
  const client = { listWorldCovers: vi.fn().mockResolvedValueOnce([cover]).mockResolvedValue([{ ...cover, revision: 2 }]),
    coverImage: vi.fn().mockResolvedValue(new Blob(["image"])) } as unknown as CoreClient;
  const view = renderHook(() => useWorldCovers(client));
  await waitFor(() => expect(view.result.current.appearances["world-a"]?.urls[face]).toBe("blob:face"));
  await act(async () => { await view.result.current.refresh(); });
  await waitFor(() => expect(view.result.current.appearances["world-a"]?.full.revision).toBe(2));
  expect(client.coverImage).toHaveBeenCalledOnce();
  expect(revoke).not.toHaveBeenCalled();
  view.unmount();
  expect(revoke).toHaveBeenCalledWith("blob:face");
});

it("still hides legacy image faces when an old cover explicitly uses text mode", async () => {
  const image = { digest: "a".repeat(64), width: 980, height: 1430, size: 10, media_type: "image/webp" };
  const cover: WorldCover = { world_id: "world-a", mode: "text", title: "世界甲", show_title: true, revision: 1,
    faces: { front: { source: image, display: image, crop: { x: 0, y: 0, width: 100, height: 100, rotation: 0 } } } };
  const client = { listWorldCovers: vi.fn().mockResolvedValue([cover]), coverImage: vi.fn() } as unknown as CoreClient;
  const { result } = renderHook(() => useWorldCovers(client));
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(client.coverImage).not.toHaveBeenCalled();
  expect(result.current.appearances["world-a"].urls).toEqual({});
});
