import { useCallback, useEffect, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useDesktopSaveBlock, useDesktopUpdateBlock } from "./DesktopUpdates";
import "./save-slots.css";

type Entry = { name: string; saved_at: string; available: boolean; counts: { worlds: number; chat_messages: number } };
type Catalog = { directory: string | null; revision: number; slots: (Entry | null)[]; startup_error?: string | null; cancelled?: boolean };
type Action = "save" | "import" | "copy_auto" | "rename" | "export" | "load" | "retry_auto";
const warning = "加载手动存档会立即切换全部世界、角色和聊天等数据，同时覆盖自动存档。若要保留原自动存档，请先将它另存到一个手动位置。";

function failure(value: unknown): string {
  const messages: Record<string, string> = {
    save_busy: "另一项存档、设置或更新正在进行，请稍后重试。",
    save_tasks_running: "当前任务尚未结束，数据没有切换。请等待任务完成后再试。",
    save_slot_changed: "存档列表已变化，请重新读取后再操作。",
    save_slot_empty: "这个位置还没有存档。",
    save_slot_folder_required: "请先选择专用存档文件夹。",
    save_slot_name_invalid: "请填写1至80个字符的存档名称。",
    save_slot_catalog_invalid: "存档目录信息无法确认，已有文件保留。请重新选择存档文件夹。",
    save_snapshot_damaged: "存档校验未通过，已停止操作。原数据和已有存档保留。",
    save_import_invalid: "文件不是完整的 dreamtalk 存档，未导入或加载。",
    save_newer_application_required: "这份存档需要更新版本，请先检查应用更新。",
    save_backup_location_invalid: "请选择程序和当前数据目录之外的专用文件夹。",
    save_export_target_invalid: "请选择新的 .dreamsave 文件名，已有文件不会被覆盖。",
    save_update_verification_pending: "更新仍在核对存档，请完成更新后再操作。",
    save_financial_schema_incompatible: "存档的费用保护结构尚不兼容，已停止加载并保留当前数据。",
    save_restore_interrupted: "上次加载尚未完成，数据和恢复材料已保留。请重新打开应用，让程序恢复检查。",
    save_operation_timeout: "操作超时，完成状态尚未确认。请重新读取存档；加载期间请重新连接应用。",
    save_recovery_required: "当前数据仍在保护检查中，请完成检查后再保存。",
    save_tool_shutdown_unconfirmed: "加载工具尚未确认停止，当前已暂停进入世界以保护数据。请重新打开应用后检查。",
    save_core_shutdown_unconfirmed: "尚未确认当前数据已停止使用，已停止加载。请重新打开应用后检查。",
    save_financial_metadata_unavailable: "当前费用保护记录无法读取，原数据已保留。请检查修复更新或使用完整的本机恢复材料。",
  };
  return messages[String(value)] ?? "存档操作未能完成，已有文件和恢复材料保留。请重新读取后再试。";
}

export function SaveSlotsPanel({ recovery = false }: { recovery?: boolean }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [names, setNames] = useState<string[]>(["自动存档", ...[1, 2, 3, 4].map(index => `手动存档 ${index}`)]);
  const [paths, setPaths] = useState<Record<number, string>>({});
  const [working, setWorking] = useState(false), [reading, setReading] = useState(true);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [reconnect, setReconnect] = useState(false);
  const live = useRef(false), lock = useRef(false);
  const blockReason = useDesktopSaveBlock();
  useDesktopUpdateBlock(working ? "存档操作正在进行。" : null);
  const accept = useCallback((value: Catalog) => {
    if (!live.current) return;
    setCatalog(value);
    setNames(Array.from({ length: 5 }, (_, index) => value.slots[index]?.name ?? (index ? `手动存档 ${index}` : "自动存档")));
  }, []);
  const refresh = useCallback(async () => {
    setReading(true);
    try { accept(await invoke<Catalog>("save_slots_status")); }
    finally { if (live.current) setReading(false); }
  }, [accept]);
  useEffect(() => {
    live.current = true;
    if (!isTauri()) { setReading(false); return () => { live.current = false; }; }
    void refresh().catch(value => { if (live.current) setError(failure(value)); });
    const off = listen<string>("save-backup-warning", event => { if (live.current) setError(failure(event.payload)); });
    return () => { live.current = false; void off.then(remove => remove()); };
  }, [refresh]);
  const operate = async (action: Action, slot: number, source?: string) => {
    if (lock.current || !catalog || reading) return;
    const entry = catalog.slots[slot];
    if (action === "load" && !window.confirm(`${warning}\n\n现在加载“${entry?.name ?? names[slot]}”？`)) return;
    if (["save", "import", "copy_auto"].includes(action) && entry && !window.confirm(`替换“${entry.name}”？原位置将由新的存档替换。`)) return;
    lock.current = true; setWorking(true); setError(""); setNotice("");
    try {
      const result = await invoke<Catalog>("operate_save_slot", { request: { action, slot, revision: catalog.revision, name: names[slot].trim(), source: source ?? null, confirmed: true } });
      if (action === "load") {
        try {
          window.localStorage.removeItem("livingworld.lastWorldId");
          window.localStorage.removeItem("livingworld.pendingWorldDeletion");
          window.sessionStorage.removeItem("livingworld.worldDeletionNotice");
        } catch { /* Optional UI selection; the loaded database is authoritative. */ }
        window.location.reload();
      } else {
        accept(result);
        if (!result.cancelled) setNotice(action === "import" ? "存档已导入到这个位置，尚未加载。" : action === "copy_auto" ? "原自动存档已另存到手动位置，当前数据没有切换。" : action === "export" ? "存档已导出。" : "存档已保存。");
      }
    } catch (value) { if (live.current) { setError(failure(value)); if (action === "load") setReconnect(true); } }
    finally { lock.current = false; if (live.current) setWorking(false); }
  };
  const choose = async () => {
    if (lock.current) return;
    lock.current = true; setWorking(true); setError(""); setNotice("");
    try { const value = await invoke<Catalog | null>("choose_save_slots_folder"); if (value) { accept(value); setNotice("存档文件夹已设置，其他位置的旧文件仍保留。"); } }
    catch (value) { if (live.current) setError(failure(value)); }
    finally { lock.current = false; if (live.current) setWorking(false); }
  };
  if (!isTauri()) return <p className="inline-hint">请在桌面应用中管理完整存档。</p>;
  const blocked = working || reading;
  return <section className="save-slots" aria-labelledby="save-slots-title" aria-busy={blocked}>
    <div className="save-slots-heading"><div><h2 id="save-slots-title">存档</h2><p>平时继续游玩，数据会正常保存。需要保留一个时间点或游玩其他存档时，再来这里。</p></div><div className="save-slots-tools"><button type="button" className="secondary-button" disabled={blocked} onClick={() => void choose()}>{catalog?.directory ? "更换文件夹" : "选择存档文件夹"}</button><button type="button" className="text-action" disabled={blocked} onClick={() => void refresh().then(() => setError("")).catch(value => setError(failure(value)))}>重新读取</button></div></div>
    <p className="save-slots-warning" role="note">{warning}</p>
    {catalog?.directory ? <p className="save-slots-directory">存档文件夹：{catalog.directory}</p> : <p className="inline-hint">先选择一个专用文件夹。设置后，本次启动会保存一份自动存档；之后每次启动保存一次。</p>}
    {error && <p role="alert" className="app-alert">{error}{reconnect && <button type="button" className="text-action" onClick={() => window.location.reload()}>重新连接</button>}</p>}
    {notice && <p role="status" className="inline-hint">{notice}</p>}
    {catalog?.startup_error && !recovery && <p role="alert" className="app-alert">本次启动的自动存档尚未完成：{failure(catalog.startup_error)}<button type="button" className="text-action" disabled={blocked} onClick={() => void operate("retry_auto", 0)}>重试自动保存</button></p>}
    {blockReason && !working && <p className="inline-hint">{blockReason} 完成后才能加载存档。</p>}
    {reading && !catalog && <p role="status" className="inline-hint">正在读取五个存档位置…</p>}
    <ol className="save-slots-list">{Array.from({ length: 5 }, (_, index) => {
      const entry = catalog?.slots[index] ?? null;
      return <li key={index} className={`save-slot${index === 0 ? " save-slot-automatic" : ""}`}>
        <div className="save-slot-body"><span className="save-slot-kind">{index === 0 ? "自动存档" : `手动位置 ${index}`}</span><label className="save-slot-name"><span className="sr-only">{index === 0 ? "自动存档" : `手动位置 ${index}`}名称</span><input maxLength={80} value={names[index]} disabled={blocked || !catalog?.directory} onChange={event => setNames(current => current.map((name, position) => position === index ? event.target.value : name))} /></label>
          <p>{entry ? entry.available ? `${entry.counts.worlds} 个世界 · ${entry.counts.chat_messages} 条消息` : "文件暂不可用，已有登记保留" : "空存档位"}</p>
          {index === 0 && <p className="save-slot-hint">每次启动保存一次，加载手动存档后同步替换。</p>}
        </div>
        <div className="save-slot-actions">
          {index > 0 && <>{!recovery && <button type="button" className="secondary-button" disabled={blocked || !catalog?.directory || !names[index].trim() || Boolean(blockReason)} onClick={() => void operate("save", index)}>{entry ? "保存当前数据并替换" : "保存当前数据"}</button>}<button type="button" className="text-action" disabled={blocked || !catalog?.directory || !names[index].trim()} onClick={() => void operate("import", index)}>导入文件</button><button type="button" className="text-action" disabled={blocked || !catalog?.slots[0]?.available || !names[index].trim()} onClick={() => void operate("copy_auto", index)}>另存自动存档到此处</button></>}
          {entry && <><button type="button" className="secondary-button" disabled={blocked || !entry.available || Boolean(blockReason)} onClick={() => void operate("load", index)}>加载</button><button type="button" className="text-action" disabled={blocked || !names[index].trim() || names[index] === entry.name} onClick={() => void operate("rename", index)}>保存名称</button><button type="button" className="text-action" disabled={blocked || !entry.available} onClick={() => void operate("export", index)}>导出</button></>}
        </div>
        {index > 0 && <details className="save-slot-path"><summary>指定存档文件路径</summary><label className="field"><span className="sr-only">手动位置 {index} 的导入路径</span><input value={paths[index] ?? ""} disabled={blocked} placeholder="选择文件，或填写 .dreamsave 文件的完整路径" onChange={event => setPaths(current => ({ ...current, [index]: event.target.value }))} /></label><button type="button" className="text-action" disabled={blocked || !catalog?.directory || !paths[index]?.trim() || !names[index].trim()} onClick={() => void operate("import", index, paths[index].trim())}>从此路径导入</button></details>}
        <time className="save-slot-time" dateTime={entry?.saved_at}>{entry ? new Date(entry.saved_at).toLocaleString("zh-CN") : "尚未保存"}</time>
      </li>;
    })}</ol>
    <p className="inline-hint">仅使用上面的五个位置；导入会替换所选手动位置，不会立即加载。更新保护独立处理，不占用手动位置。本机 API 配置和密钥不随他人存档切换。</p>
  </section>;
}
