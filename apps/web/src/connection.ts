import { invoke, isTauri } from "@tauri-apps/api/core";
import developmentConnection from "virtual:core-connection";
import type { CoreConnection } from "@livingworld/api-client";

export async function discoverConnection(): Promise<CoreConnection> {
  if (isTauri()) return invoke<CoreConnection>("core_connection");
  if (developmentConnection) return developmentConnection;
  throw new Error("core_connection_not_configured");
}

export async function acknowledgeReady(generation: string): Promise<void> {
  if (isTauri()) await invoke("report_ui_ready", { generation });
}
