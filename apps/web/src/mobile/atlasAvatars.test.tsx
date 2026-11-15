import { afterEach, expect, test, vi } from "vitest";
import { loadAtlasAvatars, smallAvatar } from "./atlasAvatars";
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
test("local media reads are limited to two, deduplicated and continue after missing media", async () => {
  vi.stubGlobal("createImageBitmap", undefined);
  vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:synthetic"), revokeObjectURL: vi.fn() });
  let active = 0, peak = 0;
  const read = vi.fn(async (digest: string) => {
    active++; peak = Math.max(peak, active);
    await Promise.resolve(); active--;
    if (digest === "bad") throw new Error("synthetic_missing_media");
    return new Blob(["synthetic"], { type: "image/png" });
  }), ready = vi.fn();
  await loadAtlasAvatars(["a", "b", "a", "bad", "c"], read, new AbortController().signal, ready);
  expect(read).toHaveBeenCalledTimes(4); expect(peak).toBe(2);
  expect(ready.mock.calls.map(call => call[0]).sort()).toEqual(["a", "b", "c"]);
});
test("aborting during read produces no new URL or late update", async () => {
  vi.stubGlobal("createImageBitmap", undefined);
  const create = vi.fn(), ready = vi.fn(); vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: vi.fn() });
  let finish: (blob: Blob) => void = () => {};
  const read = vi.fn(() => new Promise<Blob>(resolve => { finish = resolve; }));
  const abort = new AbortController(), result = loadAtlasAvatars(["a"], read, abort.signal, ready);
  abort.abort(); finish(new Blob(["synthetic"])); await result;
  expect(create).not.toHaveBeenCalled(); expect(ready).not.toHaveBeenCalled();
});
test("thumbnail crops without distortion and promptly closes the source bitmap", async () => {
  const image = { width: 400, height: 200, close: vi.fn() }, draw = vi.fn();
  vi.stubGlobal("createImageBitmap", vi.fn(async () => image));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: draw } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(callback => callback(new Blob(["small"])));
  await smallAvatar(new Blob(["synthetic"]), new AbortController().signal);
  expect(draw).toHaveBeenCalledWith(image, 100, 0, 200, 200, 0, 0, 112, 112);
  expect(image.close).toHaveBeenCalledTimes(1);
});
test("failed thumbnail encoding still closes decoded source pixels", async () => {
  const image = { width: 200, height: 200, close: vi.fn() };
  vi.stubGlobal("createImageBitmap", vi.fn(async () => image));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(callback => callback(null));
  await expect(smallAvatar(new Blob(["synthetic"]), new AbortController().signal)).rejects.toThrow("avatar_thumbnail_failed");
  expect(image.close).toHaveBeenCalledTimes(1);
});
