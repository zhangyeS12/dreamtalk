import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CoreClient } from "@dreamtalk/api-client";
import { mobileInvoke } from "./native";
import { hostCall } from "./host";
vi.mock("./host", () => ({ hostCall: vi.fn() }));
function syntheticBlob(data: Uint8Array | string): Blob {
  const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data;
  return { size: bytes.length, slice: (start: number, end: number) => ({ arrayBuffer: async () => bytes.slice(start, end).buffer }) } as Blob;
}
const host = vi.mocked(hostCall);
const request = { kind: "content" as const, world_id: "world", item_id: "import", format: "character_card_v3" as const, content_id: "definition", reviewed_hash: "reviewed", expected_digest: "snapshot-digest", use_regex: false };
beforeEach(() => {
  vi.resetAllMocks();
  host.mockImplementation(async operation => {
    if (operation === "connection") return { endpoint: "http://127.0.0.1:1", token: "synthetic", generation: "synthetic" };
    if (operation === "create_transfer") return "synthetic-transfer.json";
    return true;
  });
});
afterEach(() => vi.restoreAllMocks());
test("JSON export preserves the complete digest-bound request and writes bounded chunks before SAF", async () => {
  const data = new Uint8Array(40001).map((_, index) => index % 251);
  const read = vi.spyOn(CoreClient.prototype, "fileExport").mockResolvedValue(syntheticBlob(data));
  expect(await mobileInvoke("save_file_export", { request, filename: "synthetic.json" })).toBe("已导出");
  expect(read).toHaveBeenCalledWith(request);
  expect(host).toHaveBeenCalledWith("create_transfer", { extension: "json" });
  const chunks = host.mock.calls.filter(([operation]) => operation === "append_transfer").map(([, payload]) => (payload as { data: string }).data);
  expect(chunks).toHaveLength(3);
  expect(Uint8Array.from(chunks.map(chunk => atob(chunk)).join(""), character => character.charCodeAt(0))).toEqual(data);
  expect(chunks.every(chunk => atob(chunk).length <= 16384)).toBe(true);
  expect(host).toHaveBeenLastCalledWith("export_document", { path: "synthetic-transfer.json", filename: "synthetic.json" });
});
test("SAF cancellation returns no false success or API retry", async () => {
  const read = vi.spyOn(CoreClient.prototype, "fileExport").mockResolvedValue(syntheticBlob("{}"));
  host.mockImplementation(async operation => operation === "connection" ? { endpoint: "http://127.0.0.1:1", token: "synthetic", generation: "synthetic" } : operation === "create_transfer" ? "synthetic-transfer.json" : operation !== "export_document");
  expect(await mobileInvoke("save_file_export", { request })).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
});
test("oversized content is rejected before creating a native transfer", async () => {
  vi.spyOn(CoreClient.prototype, "fileExport").mockResolvedValue({ size: 64 * 1024 * 1024 + 1 } as Blob);
  await expect(mobileInvoke("save_file_export", { request })).rejects.toThrow("mobile_export_size_limit");
  expect(host.mock.calls.some(([operation]) => operation === "create_transfer")).toBe(false);
});
test("failed transfer is discarded without another export read", async () => {
  const read = vi.spyOn(CoreClient.prototype, "fileExport").mockResolvedValue(syntheticBlob("{}"));
  host.mockImplementation(async operation => {
    if (operation === "connection") return { endpoint: "http://127.0.0.1:1", token: "synthetic", generation: "synthetic" };
    if (operation === "create_transfer") return "synthetic-transfer.json";
    if (operation === "append_transfer") throw new Error("synthetic_failure");
    return true;
  });
  await expect(mobileInvoke("save_file_export", { request })).rejects.toThrow("synthetic_failure");
  expect(host).toHaveBeenLastCalledWith("discard_transfer", { path: "synthetic-transfer.json" });
  expect(read).toHaveBeenCalledTimes(1);
});
test("voice cards retain their existing format and dedicated API", async () => {
  const voice = vi.spyOn(CoreClient.prototype, "exportVoiceCard").mockResolvedValue(syntheticBlob("voice"));
  await mobileInvoke("save_file_export", { request: { kind: "voice", world_id: "world", item_id: "voice-id" }, filename: "voice.voicecard" });
  expect(voice).toHaveBeenCalledWith("world", "voice-id");
  expect(host).toHaveBeenCalledWith("create_transfer", { extension: "voicecard" });
});

test("library CHARX keeps revision and digest binding through the Android transfer", async () => {
  const cardRequest = { kind: "library_card" as const, item_id: "synthetic-card", expected_revision: 7, expected_digest: "synthetic-digest" };
  const read = vi.spyOn(CoreClient.prototype, "fileExport").mockResolvedValue(syntheticBlob("synthetic CHARX"));
  await mobileInvoke("save_file_export", { request: cardRequest, filename: "synthetic.charx" });
  expect(read).toHaveBeenCalledWith(cardRequest);
  expect(host).toHaveBeenCalledWith("create_transfer", { extension: "charx" });
  expect(host).toHaveBeenCalledWith("export_document", { path: "synthetic-transfer.json", filename: "synthetic.charx" });
});
test("cancelling the Android document picker reports cancellation without another export", async () => {
  const read = vi.spyOn(CoreClient.prototype, "fileExport").mockResolvedValue(syntheticBlob("synthetic CHARX"));
  host.mockImplementation(async operation => {
    if (operation === "connection") return { endpoint: "http://127.0.0.1:1", token: "synthetic", generation: "synthetic" };
    if (operation === "create_transfer") return "synthetic.charx";
    return operation !== "export_document";
  });
  expect(await mobileInvoke("save_file_export", { request: { kind: "library_card", item_id: "synthetic-card", expected_revision: 1, expected_digest: "digest" } })).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
});
