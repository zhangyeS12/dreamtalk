import { useCallback, useEffect, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
export interface DesktopStatus {
  autostart: boolean;
  close_to_tray: boolean;
  window_visible: boolean;
  app_version: string;
  executable_path: string;
}
function saveError(error: unknown): string {
  switch (error) {
    case "autostart_status_failed": return "未能读取自启动状态，请刷新设置后重试。";
    case "autostart_update_failed": return "未能更新系统自启动设置，请刷新设置后核对，再重新保存。";
    case "background_settings_save_failed": return "未能保存托盘设置，请刷新设置后重试。";
    case "background_settings_partial_update": return "系统自启动设置可能已更新，但托盘设置未保存。请刷新设置核对，再重新保存。";
    default: return "未能完整保存，请刷新设置核对自启动和托盘状态后重试。";
  }
}
export function BackgroundSettings({ onStatusChange, onDirtyChange }: { onStatusChange?: (status: DesktopStatus | null) => void; onDirtyChange?: (dirty: boolean) => void } = {}) {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [autostart, setAutostart] = useState(false);
  const [closeToTray, setCloseToTray] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const generation = useRef(0);
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  const dirty = Boolean(status && (status.autostart !== autostart || status.close_to_tray !== closeToTray));
  useEffect(() => { onStatusChange?.(status); }, [status, onStatusChange]);
  useEffect(() => { onDirtyChange?.(dirty || busy); }, [dirty, busy, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const refresh = useCallback(async () => {
    const job = ++generation.current;
    lock.current = true; setBusy(true); setNotice(""); setFailed(false);
    try {
      const next = await invoke<DesktopStatus>("desktop_background_status");
      if (generation.current !== job) return;
      setStatus(next); setAutostart(next.autostart); setCloseToTray(next.close_to_tray);
    } catch {
      if (generation.current !== job) return;
      setStatus(null); setFailed(true); setNotice("未能读取桌面设置，请点击刷新设置重试。");
    } finally {
      if (generation.current === job) { lock.current = false; setBusy(false); }
    }
  }, []);
  useEffect(() => {
    if (isTauri()) void refresh();
    return () => { generation.current += 1; };
  }, [refresh]);
  async function save() {
    if (!status || lock.current) return;
    const job = ++generation.current;
    lock.current = true; setBusy(true); setNotice(""); setFailed(false);
    try {
      const next = await invoke<DesktopStatus>("configure_desktop_background", { autostart, closeToTray });
      if (generation.current !== job) return;
      setStatus(next); setAutostart(next.autostart); setCloseToTray(next.close_to_tray);
      setNotice(next.autostart ? "后台设置已保存，自启动位置已更新为当前程序。" : "后台设置已保存，自启动已关闭。");
    } catch (error) {
      if (generation.current !== job) return;
      setFailed(true); setNotice(saveError(error));
    } finally {
      if (generation.current === job) { lock.current = false; setBusy(false); }
    }
  }
  return <section className="settings-section">
    <div className="section-heading"><h2>后台运行</h2><p>登录电脑后可在后台启动，从系统托盘打开窗口。</p></div>
    {!isTauri() ? <p className="inline-hint">开机自启动和托盘设置需要使用桌面版。</p> : <>
      {status && <div>
        <p>当前版本：{status.app_version}</p>
        <p className="inline-hint" style={{ overflowWrap: "anywhere" }}>当前程序位置：{status.executable_path}</p>
      </div>}
      <div className="setting-row"><label><input type="checkbox" checked={autostart} disabled={!status || busy} onChange={e => setAutostart(e.target.checked)} /> 登录电脑后自动启动，保持窗口隐藏</label></div>
      <div className="setting-row"><label><input type="checkbox" checked={closeToTray} disabled={!status || busy} onChange={e => setCloseToTray(e.target.checked)} /> 关闭窗口后继续在托盘运行</label></div>
      <p className="inline-hint" role="status">{busy ? "正在处理后台设置…" : !status ? "尚未读取已保存设置。" : dirty ? "有尚未保存的后台选项。" : "选项与已保存配置一致。"}</p>
      <button type="button" className="primary-button" disabled={!status || busy || (!autostart && !status.autostart && status.close_to_tray === closeToTray)} onClick={() => void save()}>{busy ? "处理中……" : autostart ? "保存并更新启动位置" : "保存后台设置"}</button>
      <button type="button" className="secondary-button" disabled={busy} onClick={() => { if (!lock.current) void refresh(); }}>刷新设置</button>
      <p className="inline-hint">更换便携包后，打开新版并在勾选自启动时点击“保存并更新启动位置”，即可登记当前程序，无需先关闭再开启。刷新只读取已保存设置，会恢复上面的选项。</p>
    </>}
    <p className="inline-hint">双击托盘图标可打开窗口；右键选择“退出并停止后台运行”可彻底退出。关机时不会调用模型，重开后才恢复。便携版启用自启动后，请保留当前程序文件夹的位置。</p>
    {notice && <p role={failed ? "alert" : "status"}>{notice}</p>}
  </section>;
}
