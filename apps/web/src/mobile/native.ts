import type { invoke as PlatformInvoke } from "@tauri-apps/api/core";
import { hostCall } from "./host";
import { CoreClient, type CoreConnection, type FileExportRequest } from "@dreamtalk/api-client";
export const mobileInvoke: typeof PlatformInvoke = async <T>(operation: string, payload?: unknown): Promise<T> => {
  const value = (payload ?? {}) as { request?: Record<string, unknown> };
  if (operation === "operate_save_slot" && value.request?.action === "import") {
    const path = await hostCall<string | null>("import_document");
    if (!path) return { ...await hostCall<object>("save_slots_status"), cancelled: true } as T;
    return hostCall<T>(operation, { request: { ...value.request, source: path } });
  }
  if (operation === "operate_save_slot" && value.request?.action === "export") {
    const path = await hostCall<string>("mobile_export_path", value);
    const exported = await hostCall<boolean>("export_document", { path });
    return { ...await hostCall<object>("save_slots_status"), cancelled: !exported } as T;
  }
  if (operation === "save_file_export") {
    const request = value.request as { kind: string; world_id: string; item_id: string };
    if (request.kind !== "voice" && request.kind !== "content" && request.kind !== "library_card") throw new Error("mobile_invalid");
    const client = new CoreClient(await hostCall<CoreConnection>("connection"));
    const blob = request.kind === "voice" ? await client.exportVoiceCard(request.world_id, request.item_id) : await client.fileExport(value.request as FileExportRequest);
    if (blob.size > (request.kind === "voice" ? 16 : 64) * 1024 * 1024) throw new Error("mobile_export_size_limit");
    const path = await hostCall<string>("create_transfer", { extension: request.kind === "voice" ? "voicecard" : request.kind === "library_card" ? "charx" : "json" });
    try {
      for (let offset = 0; offset < blob.size; offset += 16384) {
        const bytes = new Uint8Array(await blob.slice(offset, offset + 16384).arrayBuffer());
        await hostCall("append_transfer", { path, data: btoa(String.fromCharCode(...bytes)) });
      }
      return (await hostCall<boolean>("export_document", { path, filename: (payload as { filename?: string }).filename }) ? "已导出" : null) as T;
    } catch (error) { await hostCall("discard_transfer", { path }).catch(() => undefined); throw error; }
  }
  return hostCall<T>(operation, payload);
};
