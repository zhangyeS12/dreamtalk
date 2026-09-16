import contract from "../../../services/core/src/livingworld/domain/api_contract.json";

export const API_PROTOCOL = contract.api_protocol;
export interface CoreConnection { endpoint: string; token: string; generation: string }
export interface CoreHealth { ready: boolean; core_version: string; api_protocol: number; generation: string }

export class CoreClient {
  private readonly endpoint: URL;
  constructor(private readonly connection: CoreConnection, private readonly fetcher = globalThis.fetch.bind(globalThis)) {
    this.endpoint = new URL(connection.endpoint);
    if (!(["http:", "https:"].includes(this.endpoint.protocol)) || this.endpoint.username ||
        this.endpoint.password || this.endpoint.pathname !== "/" || this.endpoint.search || this.endpoint.hash) {
      throw new Error("invalid_core_endpoint");
    }
    if (!connection.token || !connection.generation) throw new Error("missing_core_session");
  }

  async health(signal?: AbortSignal): Promise<CoreHealth> {
    const response = await this.fetcher(new URL("/system/health", this.endpoint), {
      headers: { Authorization: `Bearer ${this.connection.token}` }, signal,
      credentials: "omit", cache: "no-store",
    });
    if (!response.ok) throw new Error("core_health_rejected");
    const health: unknown = await response.json();
    if (typeof health !== "object" || health === null || !("ready" in health) ||
        health.ready !== true || !("api_protocol" in health) || health.api_protocol !== API_PROTOCOL ||
        !("generation" in health) || health.generation !== this.connection.generation ||
        !("core_version" in health) || typeof health.core_version !== "string") {
      throw new Error("core_contract_mismatch");
    }
    return health as CoreHealth;
  }

  async shutdown(requestId: string, signal?: AbortSignal): Promise<void> {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId)) {
      throw new Error("valid_request_id_required");
    }
    const response = await this.fetcher(new URL("/system/shutdown", this.endpoint), {
      method: "POST", headers: { Authorization: `Bearer ${this.connection.token}`, "X-Request-Id": requestId },
      signal, credentials: "omit",
    });
    if (!response.ok) throw new Error("core_shutdown_rejected");
  }
}
