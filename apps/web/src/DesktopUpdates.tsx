import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Brand } from "./Brand";
import "./desktop-updates.css";

type Release = { version: string; notes: string; date: string | null };
type Status = { current_version: string; suppress_popup: boolean; signing_ready: boolean; installed: boolean; release: Release | null; cleanup_notice: string | null };
type Progress = { phase: "downloading" | "waiting" | "preparing" | "installing"; downloaded: number; total: number | null };
type Updates = { status: Status | null; checking: boolean; open: () => void; block: (id: symbol, reason: string | null) => void };
const Context = createContext<Updates | null>(null);

function updateError(error: unknown): string {
  const code = String(error);
  const errors: Record<string, string> = {
    update_check_failed: "暂时无法读取更新。请检查网络，稍后重试。更新频道尚未发布时也会显示此提示。",
    update_check_timeout: "检查更新超时，请稍后重试。",
    update_signing_not_configured: "此构建尚未配置发布签名，请使用正式安装包。",
    update_download_or_signature_failed: "下载或签名校验失败，当前版本保持可用。请重新检查更新。",
    update_download_timeout: "下载超时，当前版本保持可用。请稍后重试。",
    update_package_too_large: "安装包超过允许大小，请从 GitHub 下载正式安装包。",
    update_tasks_still_running: "当前任务尚未结束，已取消本次安装。请等待任务完成后重试。",
    update_backup_failed: "无法完成更新前备份，已停止安装并尝试恢复当前版本。请检查磁盘空间。",
    update_package_manifest_missing: "此程序包缺少文件清单。请先手动安装新版，之后即可在应用中更新。",
    update_package_modified: "程序文件与交付清单不符。请手动安装完整新版。",
    update_recovery_pending: "上次安装尚未完成确认。请完成安装或按更新说明处理恢复记录，再进行更新。",
    update_installer_failed: "安装程序未能启动，已尝试恢复当前版本。恢复备份仍保留。",
    update_core_shutdown_timeout: "Core 未能正常退出，未启动安装程序。请正常退出应用后手动安装。",
    update_core_unavailable: "无法确认当前任务状态，未启动安装。请稍后重试。",
    update_busy: "另一项设置或更新操作正在进行，请稍后重试。",
  };
  return errors[code] ?? "更新未能完成。当前程序与恢复备份不会因该错误被自动清除，请稍后重试或手动安装。";
}

export function DesktopUpdateProvider({ ready, children }: { ready: boolean; children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [checking, setChecking] = useState(false);
  const [open, setOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState<Progress | null>(null);
  const [blockReason, setBlockReason] = useState("");
  const blocks = useRef(new Map<symbol, string>());
  const prompted = useRef(false);
  const acknowledged = useRef(false);
  const checkingLock = useRef(false);
  const installLock = useRef(false);
  const live = useRef(true);
  const readyRef = useRef(ready);
  readyRef.current = ready;
  const dialog = useRef<HTMLDialogElement>(null);
  const enabled = isTauri();
  const block = useCallback((id: symbol, reason: string | null) => {
    if (reason) blocks.current.set(id, reason); else blocks.current.delete(id);
    setBlockReason([...blocks.current.values()][0] ?? "");
  }, []);
  const refreshStatus = useCallback(async () => {
    const result = await invoke<Status>("desktop_update_status");
    if (live.current) setStatus(result);
    return result;
  }, []);
  const check = useCallback(async (manual: boolean) => {
    if (!enabled || checkingLock.current || installLock.current) return;
    checkingLock.current = true;
    setChecking(true);
    if (manual) { setError(""); setMessage(""); }
    try {
      await invoke<Release | null>("check_desktop_update");
      const result = await refreshStatus();
      if (!live.current) return;
      if (manual && !result.release) setMessage("你正在使用最新版本。");
      const visible = await getCurrentWindow().isVisible();
      if (result.release && readyRef.current && visible && !result.suppress_popup && !prompted.current) {
        if (await invoke<boolean>("claim_desktop_update_popup")) { prompted.current = true; setOpen(true); }
      }
    } catch (failure) { if (live.current && manual) setError(updateError(failure)); }
    finally { checkingLock.current = false; if (live.current) setChecking(false); }
  }, [enabled, refreshStatus]);
  useEffect(() => {
    live.current = true;
    if (!enabled) return;
    void refreshStatus().then(() => check(false)).catch(() => {});
    const timer = window.setInterval(() => void check(false), 24 * 60 * 60 * 1000);
    const off = listen<Progress>("desktop-update-progress", event => { if (live.current) setProgress(event.payload); });
    return () => { live.current = false; window.clearInterval(timer); void off.then(unlisten => unlisten()); };
  }, [check, enabled, refreshStatus]);
  useEffect(() => {
    if (!enabled || !ready) return;
    let active = true;
    const showAvailable = async () => {
      const result = await refreshStatus();
      if (active && result.release && !result.suppress_popup && !prompted.current && await getCurrentWindow().isVisible()) {
        if (await invoke<boolean>("claim_desktop_update_popup")) { prompted.current = true; setOpen(true); }
      }
      if (!acknowledged.current) {
        acknowledged.current = true;
        try { await invoke("acknowledge_desktop_update"); if (active) await refreshStatus(); }
        catch { acknowledged.current = false; }
      }
    };
    void showAvailable().catch(() => {});
    const off = getCurrentWindow().onFocusChanged(event => { if (event.payload) void showAvailable().catch(() => {}); });
    return () => { active = false; void off.then(unlisten => unlisten()); };
  }, [checking, enabled, ready, refreshStatus]);
  useEffect(() => {
    const element = dialog.current;
    if (open && element && !element.open) element.showModal();
    else if (!open && element?.open) element.close();
  }, [open]);
  const show = useCallback(() => { setOpen(true); setError(""); setMessage(""); void check(true); }, [check]);
  const close = () => { if (!installLock.current && !saving) { prompted.current = true; setOpen(false); void invoke("dismiss_desktop_update_popup").catch(() => {}); } };
  const changeReminder = async (suppressed: boolean) => {
    setSaving(true); setError("");
    try { await invoke("configure_desktop_updates", { suppressPopup: suppressed }); await refreshStatus(); }
    catch { setError("提醒偏好未能保存，请重试。"); }
    finally { if (live.current) setSaving(false); }
  };
  const install = async () => {
    const release = status?.release;
    if (!release || installLock.current || checkingLock.current || blocks.current.size) return;
    installLock.current = true; setWorking(true); setError(""); setMessage("");
    try {
      await invoke("install_desktop_update", { version: release.version });
    } catch (failure) {
      if (live.current) {
        setError(updateError(failure));
        if (["update_backup_failed", "update_handoff_failed", "update_installer_failed"].includes(String(failure))) {
          setMessage("当前 Core 已重新启动，请重新打开应用后继续使用。");
        }
      }
    }
    finally { installLock.current = false; if (live.current) { setWorking(false); setProgress(null); } }
  };
  const phase = progress?.phase;
  const phaseLabel = phase === "waiting" ? "正在等待当前任务结束…" : phase === "preparing" ? "正在关闭 Core 并保存恢复备份…" : phase === "installing" ? "正在启动安装程序，应用将自动重启…" : "正在下载并验证安装包…";
  return <Context.Provider value={{ status, checking, open: show, block }}>
    {children}
    {enabled && <dialog ref={dialog} className="desktop-update-dialog" aria-labelledby="desktop-update-title" onCancel={event => { event.preventDefault(); close(); }}>
      <div className="update-dialog-heading"><Brand /><button type="button" className="update-close" aria-label="稍后更新并关闭" disabled={working || saving} onClick={close}>×</button></div>
      <div className="update-dialog-body">
        <p className="update-version">当前 {status?.current_version ?? "…"}{status?.release && <> <span aria-hidden="true">→</span> {status.release.version}</>}</p>
        <h2 id="desktop-update-title">{status?.release ? "dreamtalk 有新更新" : "应用更新"}</h2>
        {status?.release ? <><p className="update-intro">{status.installed ? "更新将在安装完成后重新打开应用，你的世界与聊天记录会保留。" : "此次更新将迁入固定安装目录，之后可直接在应用内升级。"}</p>
          <div className="update-release-notes" tabIndex={0} aria-label="新版更新说明">{status.release.notes || "此版本未附更新说明。"}</div></>
          : <p className="update-intro">{checking ? "正在检查 GitHub 更新频道…" : message || "检查更新，查看最新修复与改进。"}</p>}
        {status?.cleanup_notice && <p role="status" className="update-warning">新版已启动，但旧文件或系统入口尚未全部处理。恢复记录已保留。<button type="button" disabled={working || checking} onClick={() => {
          void invoke("acknowledge_desktop_update").then(refreshStatus).catch(() => setError("旧文件处理仍未完成，请重启后再试或查看更新说明。"));
        }}>重试处理</button></p>}
        {error && <p role="alert" className="update-error">{error}</p>}
        {error && message && status?.release && <p role="status" className="update-warning">{message}<button type="button" onClick={() => window.location.reload()}>重新连接</button></p>}
        {blockReason && status?.release && !working && <p className="update-warning">{blockReason} 保存或结束后即可更新。</p>}
        {working && <div className="update-progress" role="status"><p>{phaseLabel}</p>{phase === "downloading" && <><progress max={progress?.total || undefined} value={progress?.total ? progress.downloaded : undefined} /><small>{((progress?.downloaded ?? 0) / 1048576).toFixed(1)} MB{progress?.total ? ` / ${(progress.total / 1048576).toFixed(1)} MB` : ""}</small></>}</div>}
      </div>
      <div className="update-dialog-actions"><button type="button" disabled={working || saving} onClick={close}>稍后</button>
        {status?.release ? <button type="button" className="update-primary" disabled={working || saving || checking || Boolean(blockReason)} onClick={() => void install()}>{working ? "正在更新…" : "更新"}</button>
          : <button type="button" className="update-primary" disabled={working || checking || saving} onClick={() => void check(true)}>{checking ? "正在检查…" : "检查更新"}</button>}</div>
      <label className="update-reminder"><input type="checkbox" checked={status?.suppress_popup ?? false} disabled={!status || working || saving} onChange={event => void changeReminder(event.target.checked)} />不再自动弹窗<span>仍会检查更新，并保留书架入口</span></label>
    </dialog>}
  </Context.Provider>;
}

export function useDesktopUpdateBlock(reason: string | null) {
  const updates = useContext(Context);
  const id = useRef(Symbol("update-block"));
  const register = updates?.block;
  useEffect(() => {
    register?.(id.current, reason);
    const token = id.current;
    return () => register?.(token, null);
  }, [register, reason]);
}

export function DesktopUpdateEntry({ settings = false }: { settings?: boolean }) {
  const updates = useContext(Context);
  if (!isTauri() || !updates) return null;
  const release = updates.status?.release;
  return <button type="button" className={release ? "desktop-update-entry has-update" : "desktop-update-entry"} onClick={updates.open}>
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M10 14V3m-4 4 4-4 4 4M4 12v5h12v-5" /></svg>
    {release ? "新更新" : settings ? "检查应用更新" : "检查更新"}{release && settings && <span>{release.version}</span>}
  </button>;
}
