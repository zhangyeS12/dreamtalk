import { invoke, isTauri } from "@tauri-apps/api/core";
export interface ModelSetup {
  provider_kind: "openai-compatible" | "openai-responses" | "anthropic-messages" | "gemini-interactions";
  model_id: string; base_url: string | null; max_billable_input_tokens: number; max_output_tokens: number;
  streaming: boolean; timeout_ms: number; secret?: string;
}
declare global { interface Window { __DREAMTALK_MOBILE_TEST_HOST__?: <T>(operation: string, payload: unknown) => Promise<T> } }
export async function hostCall<T>(operation: string, payload: unknown = {}): Promise<T> {
  if (isTauri()) {
    const envelope = await invoke<{ result: T }>("plugin:mobile-core|call", { operation, payload: JSON.stringify(payload) });
    return envelope.result;
  }
  if (import.meta.env.DEV && window.__DREAMTALK_MOBILE_TEST_HOST__) return window.__DREAMTALK_MOBILE_TEST_HOST__<T>(operation, payload);
  throw new Error("mobile_host_required");
}
export function feedback(error: unknown): string {
  const code = error instanceof Error ? error.message : String(error);
  if (code.includes("save_recovery_required")) return "存档需要恢复确认，请查看存档与恢复。";
  if (code.includes("mobile_notification_permission")) return "尚未允许通知，请在系统设置中开启消息通知。";
  if (code.includes("mobile_background_start_failed")) return "后台尚未启动，请核对系统后台运行限制后重试。";
  if (code.includes("mobile_background_consent")) return "请先确认后台 API 用量与耗电说明。";
  if (code.includes("mobile_busy")) return "还有任务正在处理，请完成后再保存设置。";
  if (code.includes("mobile_host_required")) return "请在安卓应用中打开 dreamtalk。";
  if (code.includes("mobile_secure_store")) return "安全存储暂时不可用，API 配置未保存。请重试。";
  if (code.includes("mobile_invalid")) return "请核对模型、服务地址和容量设置。";
  return "操作未完成，已有数据会保留。请重试。";
}
