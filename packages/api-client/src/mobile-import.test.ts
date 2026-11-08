import { expect, test, vi } from "vitest";
import { CoreClient, type WorldContentItem } from "./index";
const preview: WorldContentItem = { import_id: "dba7951f-fb42-437e-aa47-28bd40d1d9d4", replaces_import_id: null, reviewed_hash: "a".repeat(64), kind: "character", characters: [], lorebooks: [], entries: [] };
test.each(["", undefined])("no-location imports omit an absent location instead of sending an invalid UUID (%s)", async location => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(preview), { status: 200 }));
  const client = new CoreClient({ endpoint: "http://127.0.0.1:9000", token: "synthetic-session", generation: "generation" }, fetcher);
  await client.commitWorldContent("world", preview, location);
  const body = JSON.parse(fetcher.mock.calls[0][1].body);
  expect(body.reviewed_hash).toBe(preview.reviewed_hash);
  expect(Object.hasOwn(body, "initial_location_id")).toBe(false);
});
test("an explicitly selected initial location is preserved", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(preview), { status: 200 }));
  const client = new CoreClient({ endpoint: "http://127.0.0.1:9000", token: "synthetic-session", generation: "generation" }, fetcher);
  const location = "6eaa2e90-4f20-4e05-8dbe-31bd161bbef0";
  await client.commitWorldContent("world", preview, location);
  expect(JSON.parse(fetcher.mock.calls[0][1].body).initial_location_id).toBe(location);
});
