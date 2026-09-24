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
  it("uses authenticated developer routes and preserves typed trigger input", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ trigger_id: "trigger" })));
    await new CoreClient(connection, fetcher).scheduleTrigger("world", 1_000_000, "character");
    expect(fetcher.mock.calls[0][0].toString()).toBe(`${connection.endpoint}/developer/worlds/world/triggers`);
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer memory-session");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      delay_microseconds: 1_000_000,
      target_character_id: "character",
    });
  });
  it("uses versioned authenticated product routes and stable creation identity", async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ world_id: "world" })));
    const client = new CoreClient(connection, fetcher);
    const requestId = "0f6d14aa-1363-4451-a1bf-9ed40a9cbb95";
    await client.createWorld("我的世界", requestId);
    expect(fetcher.mock.calls[0][0].toString()).toBe(`${connection.endpoint}/api/v${API_PROTOCOL}/worlds`);
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer memory-session");
    expect(fetcher.mock.calls[0][1].headers["X-Request-Id"]).toBe(requestId);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ name: "我的世界" });
    await client.listProductWorlds();
    expect(fetcher.mock.calls[1][0].toString()).toBe(`${connection.endpoint}/api/v${API_PROTOCOL}/worlds`);
  });
  it("reads a transcript through the authenticated versioned product route", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("[]"));
    expect(await new CoreClient(connection, fetcher).conversationMessages("world", "conversation")).toEqual([]);
    expect(fetcher.mock.calls[0][0].toString()).toBe(`${connection.endpoint}/api/v${API_PROTOCOL}/worlds/world/conversations/conversation/messages`);
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer memory-session");
  });
});
