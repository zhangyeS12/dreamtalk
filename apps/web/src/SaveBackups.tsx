import { useCallback, useEffect, useState, type ReactNode } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Brand } from "./Brand";
import { useDesktopSaveBlock } from "./DesktopUpdates";

type Counts = { worlds: number; chat_messages: number; characters: number };
type Snapshot = { id: string; created_at: string; reason: string; version: string; counts: Counts; bytes: number };
type Safety = { recovery_required: boolean; problem: string | null; current: { counts: Counts } | null; snapshots: Snapshot[]; backup_directory: string; automatic_minutes: number; can_rollback?: boolean; update_verifying?: boolean; credential_cleanup_incomplete?: boolean };
const reasons: Record<string, string> = { automatic: "自动备份", manual: "手动备份", pre_update: "升级前", pre_migration: "存档升级前", pre_restore: "恢复前", pre_install: "安装前" };
const date = (value: string) => new Date(value).toLocaleString("zh-CN");
function message(error: unknown) {
  const values: Record<string, string> = {
    save_busy: "另一项设置、备份或更新正在进行，请稍后重试。",
    save_tasks_running: "当前生成任务尚未结束，存档没有被替换，请等待完成后重试。",
    save_snapshot_damaged: "这份备份校验未通过，当前存档没有被替换。请选择另一份备份。",
    save_database_corrupt: "当前存档校验未通过，请选择完整备份恢复。原文件仍保留。",
    save_newer_application_required: "这份存档来自更新版本，请先更新应用，再恢复。",
    save_backup_location_invalid: "请选择程序和当前存档目录之外的备份位置。",
    save_storage_context_mismatch: "未能确认正在使用的存档位置，已停止操作以保护数据。",
    save_recovery_required: "请先完成存档恢复确认。",
    save_export_target_invalid: "请选择新的 .dreamsave 文件名，已有文件不会被覆盖。",
    save_operation_timeout: "操作超时，结果尚未确认。请重新确认存档与备份状态，避免重复操作。",
    save_cleanup_record_failed: "未能保存密钥清理记录。请重新确认存档状态后重试。",
    save_update_verification_pending: "升级后的存档仍在核对，完成后才能备份。",
    save_credential_registry_unavailable: "未能完整读取已登记的密钥引用，已停止清空，请检查配置后重试。",
    save_financial_metadata_unavailable: "当前费用保护记录无法读取，已停止恢复并保留原文件，避免丢失已知用量。",
    save_financial_schema_incompatible: "两份存档的费用保护结构不兼容，已停止恢复并保留原文件。",
  };
  return values[String(error)] ?? "存档操作未完成，请查看存档与备份状态后重试。系统不会自动调用模型。";
}

export function SaveBackupPanel({ recovery = false, initial }: { recovery?: boolean; initial?: Safety }) {
  const [status, setStatus] = useState<Safety | null>(initial ?? null);
  const [selected, setSelected] = useState(initial?.snapshots[0]?.id ?? "");
  const [confirmed, setConfirmed] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [erasure, setErasure] = useState("");
  const [eraseBackups, setEraseBackups] = useState(false);
  const blockReason = useDesktopSaveBlock();
  const refresh = useCallback(async () => {
    const value = await invoke<Safety>("save_safety_status");
    setStatus(value);
    setSelected(current => value.snapshots.some(item => item.id === current) ? current : value.snapshots[0]?.id ?? "");
  }, []);
  useEffect(() => {
    if (!isTauri()) return;
    let active = true;
    void refresh().catch(error => { if (active) setError(message(error)); });
    const off = listen<string>("save-backup-warning", event => { if (active) setError(message(event.payload)); });
    return () => { active = false; void off.then(remove => remove()); };
  }, [refresh]);
  const act = async (command: string, args: Record<string, unknown> = {}, success = "") => {
    if (working) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const result = await invoke(command, args);
      if (result !== null && success) setNotice(success);
      if (command === "clear_saved_data") {
        for (const store of [window.localStorage, window.sessionStorage]) for (const key of Object.keys(store)) if (key.startsWith("livingworld.") || key.startsWith("dreamtalk.")) store.removeItem(key);
      }
      if (["restore_save_backup", "resume_restored_save", "clear_saved_data"].includes(command)) window.location.reload();
      else await refresh();
    } catch (error) { setError(message(error)); }
    finally { setWorking(false); }
  };
  const snapshot = status?.snapshots.find(item => item.id === selected);
  if (!isTauri()) return <p className="inline-hint">完整存档备份与恢复在桌面应用中提供。</p>;
  return <section className="settings-section" aria-busy={working}>
    <div className="section-heading"><h2>{recovery ? "保护并恢复你的存档" : "数据与备份"}</h2><p>备份包含所有世界、聊天、角色资料、素材和配置。保存在独立位置，卸载程序会保留。</p></div>
    {status?.problem === "save_restored_review_required" ? <p className="app-alert" role="status">{status.current ? `存档已经恢复。核对到 ${status.current.counts.worlds} 个世界、${status.current.counts.chat_messages} 条消息。` : "恢复结果暂未读取，请刷新备份状态后确认。"}确认继续后将重新打开应用；自动活动、主动联系和世界动态保持关闭，可在设置中重新开启。旧生成任务不会自动重发。</p>
      : recovery && <p className="app-alert" role="status">当前存档无法正常确认，已暂停进入世界。请选择下面的完整备份恢复；原文件会另外保留。</p>}
    {error && <p className="app-alert" role="alert">{error}</p>}
    {notice && <p className="inline-hint" role="status">{notice}</p>}
    {status?.credential_cleanup_incomplete && <p className="app-alert" role="alert">仍有已登记的旧API密钥等待清理。清理记录已保留；可在下方再次确认清空，以重试移除。</p>}
    {status && <><p className="inline-hint">{status.current ? `当前存档：${status.current.counts.worlds} 个世界、${status.current.counts.chat_messages} 条消息。` : "当前存档暂未读取。"}有变化时每 {status.automatic_minutes} 分钟自动备份，保留近7日每日备份和最近3次升级前备份。</p>{status.backup_directory && <p className="inline-hint">备份位置：{status.backup_directory}</p>}</>}
    <div className="setting-row"><button type="button" className="secondary-button" disabled={working || recovery || !status} onClick={() => void act("create_save_backup", {}, "完整存档备份已保存并通过校验。")}>立即备份</button>
      <button type="button" className="secondary-button" disabled={working} onClick={() => void act("configure_save_backup_location", {}, "备份位置已更新，旧备份仍保留。")}>选择备份位置</button>
      <button type="button" className="secondary-button" disabled={working} onClick={() => void act("import_save_backup", {}, "备份已读取，可以选择后恢复。")}>读取备份文件</button>
      <button type="button" className="text-action" disabled={working} onClick={() => void refresh().catch(error => setError(message(error)))}>刷新备份</button></div>
    <label className="field"><span>选择备份</span><select value={selected} disabled={working} onChange={event => { setSelected(event.target.value); setConfirmed(false); }}><option value="">{status?.snapshots.length ? "请选择备份" : "尚未找到完整备份"}</option>{status?.snapshots.map(item => <option key={item.id} value={item.id}>{date(item.created_at)} · {reasons[item.reason] ?? "存档备份"} · {item.counts.worlds}个世界 / {item.counts.chat_messages}条消息</option>)}</select></label>
    {snapshot && <><p className="inline-hint">将恢复到 {date(snapshot.created_at)} 的状态。此后的新增内容不会出现在这份备份中；恢复前会另外保留当前数据。</p>
      <label className="field"><span><input type="checkbox" checked={confirmed} disabled={working} onChange={event => setConfirmed(event.target.checked)} />我确认恢复这份备份，替换当前存档</span></label>
      {blockReason && <p className="inline-hint">{blockReason} 完成编辑后才能恢复存档。</p>}
      <div className="setting-row"><button type="button" className="secondary-button" disabled={working || !confirmed || Boolean(blockReason)} onClick={() => void act("restore_save_backup", { snapshotId: selected, confirmed: true })}>{working ? "正在处理…" : "恢复所选备份"}</button><button type="button" className="secondary-button" disabled={working} onClick={() => void act("export_save_backup", { snapshotId: selected }, "完整备份文件已导出。")}>导出所选备份</button></div></>}
    {status?.problem === "save_restored_review_required" && <button type="button" className="secondary-button" disabled={working || !status.current} onClick={() => void act("resume_restored_save")}>确认并继续使用</button>}
    {status?.can_rollback && <div className="setting-row"><p className="inline-hint">本次升级尚未完成存档核对，可以恢复匹配的旧程序与升级前存档。当前文件会另行保留；应用将关闭并重新打开。</p><button type="button" className="secondary-button" disabled={working} onClick={() => void act("rollback_desktop_update")}>回退本次未完成的升级</button></div>}
    <p className="inline-hint">备份只在本机保存，不调用模型或自动上传。导出文件包含私人聊天和素材，请妥善保存；换机后需要重新填写API密钥。</p>
    {!recovery && <details className="handbook-fold"><summary><strong>清空本机数据</strong><span>独立确认，卸载程序不会执行</span></summary><p className="app-alert">这会清空全部世界、聊天、素材、身份和配置，移除已登记的API密钥。无正文的费用、预算和调用回执保留，避免重置额度。你另存的导出文件不在清理范围内。</p><label className="field"><span>输入“删除全部数据”确认</span><input value={erasure} disabled={working} onChange={event => setErasure(event.target.value)} autoComplete="off" /></label><label className="field"><span><input type="checkbox" checked={eraseBackups} disabled={working} onChange={event => setEraseBackups(event.target.checked)} />同时删除该应用已登记的独立备份，无法通过应用恢复</span></label><button type="button" className="text-action destructive-action" disabled={working || erasure !== "删除全部数据" || Boolean(blockReason)} onClick={() => void act("clear_saved_data", { confirmation: erasure, includeBackups: eraseBackups })}>确认清空</button></details>}
  </section>;
}

export function SaveSafetyGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Safety | null>(null);
  const [allowed, setAllowed] = useState(!isTauri());
  const [error, setError] = useState("");
  const check = useCallback(async () => {
    try {
      const value = await invoke<Safety>("save_safety_status");
      setState(value); setError(""); setAllowed(!value.recovery_required && !value.update_verifying);
    } catch (error) { if (String(error) !== "save_busy") setError(message(error)); }
  }, []);
  useEffect(() => {
    if (!isTauri() || allowed) return;
    void check();
    const timer = window.setInterval(() => void check(), 5000);
    return () => window.clearInterval(timer);
  }, [check, allowed]);
  if (allowed) return children;
  return <main className="product-shell"><div className="page-section"><Brand />{state?.recovery_required || error ? <SaveBackupPanel recovery initial={state ?? undefined} /> : <section className="settings-section"><h2>{state?.update_verifying ? "正在核对升级后的存档" : "正在确认存档"}</h2></section>}</div></main>;
}
