import { invoke, isTauri } from "@tauri-apps/api/core";
import developmentConnection from "virtual:core-connection";
import type { CoreConnection } from "@dreamtalk/api-client";

export async function discoverConnection(): Promise<CoreConnection> {
  if (isTauri()) return invoke<CoreConnection>("core_connection");
  if (developmentConnection) return developmentConnection;
  throw new Error("core_connection_not_configured");
}

let recovery: Promise<CoreConnection> | null = null;
export function recoverConnection(): Promise<CoreConnection> {
  if (!isTauri()) return discoverConnection();
  // Share one native operation across StrictMode effects and repeated requests.
  recovery ??= invoke<CoreConnection>("retry_core_start").finally(() => { recovery = null; });
  return recovery;
}

export async function acknowledgeReady(generation: string): Promise<void> {
  if (isTauri()) await invoke("report_ui_ready", { generation });
}
