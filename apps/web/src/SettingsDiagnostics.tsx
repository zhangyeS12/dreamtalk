import { useCallback, useEffect, useRef, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { CoreClient, type CoreHealth } from "@dreamtalk/api-client";
import type { DesktopStatus } from "./BackgroundSettings";

export function SettingsDiagnostics({ client, worldId, visible, desktop, onBackground }: {
  client: CoreClient; worldId?: string; visible: boolean; desktop: DesktopStatus | null; onBackground: () => void;
}) {
  const [health, setHealth] = useState<CoreHealth | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    pending.current?.abort(); const abort = new AbortController(); pending.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 10000);
    setBusy(true); setError("");
    try { const result = await client.health(abort.signal, worldId); if (pending.current === abort && !abort.signal.aborted) setHealth(result); }
    catch { if (pending.current === abort) { setHealth(null); setError("未能读取本机核心状态，请检查连接后刷新。"); } }
    finally { window.clearTimeout(timeout); if (pending.current === abort) { pending.current = null; setBusy(false); } }
  }, [client, worldId]);
  useEffect(() => {
    if (visible) void refresh();
    return () => { const abort = pending.current; pending.current = null; abort?.abort(); };
  }, [visible, refresh]);
  const model = health ? { ready: "配置已就绪", unconfigured: "尚未配置", partially_configured: "配置不完整", degraded: "配置状态异常" }[health.llm_status] : "尚未确认";
  return <section className="settings-section handbook-diagnostics"><div className="section-heading"><h2>dreamtalk</h2><p>版本与连接信息来自当前运行程序。</p></div>
    <dl><div><dt>运行环境</dt><dd>{isTauri() ? "桌面版" : "浏览器版"}</dd></div><div><dt>桌面版本</dt><dd>{isTauri() ? desktop?.app_version ?? "暂未读取，可在后台运行中刷新" : "使用浏览器连接本机核心"}</dd></div><div><dt>核心版本</dt><dd>{health?.core_version ?? "尚未读取"}</dd></div><div><dt>核心连接</dt><dd>{busy ? "正在核对…" : health ? "本次读取成功" : "尚未确认"}</dd></div><div><dt>模型配置</dt><dd>{model}</dd></div>{desktop && <div><dt>当前程序位置</dt><dd>{desktop.executable_path}</dd></div>}</dl>
    <div className="profile-actions"><button type="button" className="secondary-button" disabled={busy} onClick={() => void refresh()}>{busy ? "读取中…" : "刷新连接状态"}</button>{isTauri() && <button type="button" className="text-action" onClick={onBackground}>前往后台运行</button>}</div>
    {error && <p className="app-alert" role="alert">{error}</p>}<p className="inline-hint">刷新仅读取本机状态，不调用模型。模型配置就绪不代表服务商密钥、余额或网络已经验证。</p>
  </section>;
}
