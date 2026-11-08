import { useCallback, useEffect, useState } from "react";
import { hostCall, feedback } from "./host";
export type BackgroundStatus = { enabled: boolean; running: boolean; start_on_boot: boolean; notifications_allowed: boolean; battery_unrestricted: boolean; problem: string | null };
export function BackgroundSettings() {
  const [status, setStatus] = useState<BackgroundStatus | null>(null);
  const [boot, setBoot] = useState(false), [consent, setConsent] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const read = useCallback(async () => { try { const next = await hostCall<BackgroundStatus>("background_status"); setStatus(next); setBoot(next.start_on_boot); setError(""); } catch (e) { setError(feedback(e)); } }, []);
  useEffect(() => { void read(); const update = () => { if (!document.hidden) void read(); }; window.addEventListener("focus", update); document.addEventListener("visibilitychange", update); return () => { window.removeEventListener("focus", update); document.removeEventListener("visibilitychange", update); }; }, [read]);
  useEffect(() => { if (!status?.enabled || status.running) return; const timer = setTimeout(() => void read(), 750); return () => clearTimeout(timer); }, [status, read]);
  const save = async (enabled: boolean) => {
    if (busy || (enabled && !consent)) return;
    setBusy(true); setError("");
    try {
      if (enabled && !await hostCall<boolean>("request_notifications")) { setError("尚未允许消息通知。请允许通知后再开启后台联系。"); return; }
      setStatus(await hostCall<BackgroundStatus>("configure_background", { enabled, start_on_boot: boot, consent }));
    } catch (e) { setError(feedback(e)); } finally { setBusy(false); }
  };
  return <section className="settings-section"><h2>后台运行与通知</h2><p>退到桌面或锁屏后，已开启的角色活动、主动联系和世界动态可以继续使用 API。消息保存后发送系统通知，点击通知进入原会话。</p><p role="status">{status ? status.running ? "后台运行中" : status.enabled ? "后台尚未运行，请重新开启并核对系统限制" : "后台运行已关闭" : "正在读取…"}</p><p className="inline-hint">开启后保留一条后台状态通知，可直接停止。锁屏只提示角色来信，正文留在应用内。系统强行停止、应用明确停止和关机期间不生成消息。</p>
    <label className="speech-check"><input type="checkbox" checked={boot} disabled={busy} onChange={e => setBoot(e.target.checked)} /><span>开机后恢复已开启的后台运行</span></label>
    <label className="speech-check"><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)} /><span>我同意已开启的后台功能在应用隐藏时调用 API，可能产生费用和额外耗电。此开关不会自动开启各世界的生成权限。</span></label>
    <div className="profile-actions"><button disabled={busy || !status || !consent} onClick={() => void save(true)}>{busy ? "正在处理…" : status?.running ? "保存后台设置" : "开启后台运行"}</button><button disabled={busy || !status?.enabled} onClick={() => void save(false)}>停止后台运行</button></div>
    {status && <p className="inline-hint">通知：{status.notifications_allowed ? "已允许" : "尚未允许"}；电池优化：{status.battery_unrestricted ? "已放宽" : "仍受系统管理，长时间锁屏可能延迟"}。可在系统应用设置中核对后台耗电和自启动权限。</p>}
    <div className="profile-actions"><button onClick={() => void hostCall("notification_settings").catch(e => setError(feedback(e)))}>系统通知设置</button><button onClick={() => void hostCall("battery_settings").catch(e => setError(feedback(e)))}>系统应用与电池设置</button><button onClick={() => void read()}>刷新状态</button></div>{status?.problem && <p role="status">最近的后台状态需要核对，可刷新状态或复制诊断。</p>}{error && <p role="alert" className="app-alert">{error}</p>}</section>;
}
