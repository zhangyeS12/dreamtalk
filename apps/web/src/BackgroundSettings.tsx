import { useEffect, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
interface DesktopStatus { autostart: boolean; close_to_tray: boolean; window_visible: boolean }
export function BackgroundSettings() {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [autostart, setAutostart] = useState(false);
  const [closeToTray, setCloseToTray] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    if (isTauri()) void invoke<DesktopStatus>("desktop_background_status").then(next => {
      if (active) { setStatus(next); setAutostart(next.autostart); setCloseToTray(next.close_to_tray); }
    }).catch(() => { if (active) setNotice("未能读取桌面设置，请重新打开设置。"); });
    return () => { active = false; };
  }, []);
  async function save() {
    if (!status || lock.current) return;
    lock.current = true; setBusy(true); setNotice("");
    try {
      const next = await invoke<DesktopStatus>("configure_desktop_background", { autostart, closeToTray });
      setStatus(next); setNotice("后台启动设置已保存。");
    } catch { setNotice("未能完整保存。请重新打开设置核对开机自启动状态。"); }
    finally { lock.current = false; setBusy(false); }
  }
  return <section className="settings-section">
    <div className="section-heading"><h2>后台运行</h2><p>登录电脑后可在后台启动，从系统托盘打开窗口。</p></div>
    {!isTauri() ? <p className="inline-hint">开机自启动和托盘设置需要使用桌面版。</p> : <>
      <div className="setting-row"><label><input type="checkbox" checked={autostart} disabled={!status || busy} onChange={e => setAutostart(e.target.checked)} /> 登录电脑后自动启动，保持窗口隐藏</label></div>
      <div className="setting-row"><label><input type="checkbox" checked={closeToTray} disabled={!status || busy} onChange={e => setCloseToTray(e.target.checked)} /> 关闭窗口后继续在托盘运行</label></div>
      <button type="button" disabled={!status || busy || (status.autostart === autostart && status.close_to_tray === closeToTray)} onClick={() => void save()}>{busy ? "保存中……" : "保存后台设置"}</button>
    </>}
    <p className="inline-hint">双击托盘图标可打开窗口；右键选择“退出并停止后台运行”可彻底退出。关机时不会调用模型，重开后才恢复。便携版启用自启动后，请保留当前程序文件夹的位置。</p>
    {notice && <p role="status">{notice}</p>}
  </section>;
}
