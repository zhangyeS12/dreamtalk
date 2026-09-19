import { afterEach, describe, expect, it, vi } from "vitest";
import { API_PROTOCOL, CoreClient } from "./index";

afterEach(() => vi.restoreAllMocks());
const connection = { endpoint: "http://127.0.0.1:49152", token: "memory-session", generation: "generation" };
const health = { ready: true, core_version: "0.1.0", api_protocol: API_PROTOCOL, generation: "generation", llm_status: "unconfigured" };

describe("CoreClient", () => {
  it("uses discovered endpoint and bearer auth", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(health)));
    expect(await new CoreClient(connection, fetcher).health()).toEqual(health);
    expect(fetcher.mock.calls[0][0].toString()).toBe(`${connection.endpoint}/system/health`);
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer memory-session");
  });
  it.each([{ ...health, generation: "stale" }, { ...health, api_protocol: API_PROTOCOL + 1 }, { ...health, ready: false }])(
    "rejects incompatible or stale readiness", async (value) => {
      await expect(new CoreClient(connection, vi.fn().mockResolvedValue(new Response(JSON.stringify(value)))).health())
        .rejects.toThrow("core_contract_mismatch");
    },
  );
  it("rejects missing session and unsafe endpoint", () => {
    expect(() => new CoreClient({ ...connection, token: "" })).toThrow("missing_core_session");
    expect(() => new CoreClient({ ...connection, endpoint: "http://user:password@127.0.0.1" })).toThrow("invalid_core_endpoint");
  });
  it("passes request identity for shutdown", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}"));
    const id = "0f6d14aa-1363-4451-a1bf-9ed40a9cbb95";
    await new CoreClient(connection, fetcher).shutdown(id);
    expect(fetcher.mock.calls[0][1].headers["X-Request-Id"]).toBe(id);
  });
});
