import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { CoreClient, CoreRequestError, type ChatExportInfo, type ContentExportFormat, type ContentExportInfo, type FileExportRequest, type WorldContentItem } from "@dreamtalk/api-client";
import { useDesktopUpdateBlock } from "./DesktopUpdates";
import "./file-exports.css";

function failureMessage(failure: unknown): string {
  const code = failure instanceof CoreRequestError ? failure.code : typeof failure === "string" ? failure : "";
  if (code === "export_snapshot_changed" || code === "export_content_changed" || code === "export_transcript_changed") return "资料或会话信息已有变化。请重新读取导出信息后再保存。";
  if (code === "export_write_failed") return "文件未能保存，请检查保存位置、可用空间和文件是否被其他程序占用。";
  if (code === "export_extension_invalid") return "请使用所选格式的文件扩展名（.json 或 .txt），再选择保存位置。";
  if (code === "export_browser_size_limit") return "文件超过浏览器导出的 128 MB 上限，请使用桌面版导出完整记录。";
  if (code === "v3_use_regex_required") return "V3 世界书需要明确关键词的正则规则。可以选择 V2，或核对下方关键词选项。";
  if (failure instanceof CoreRequestError && failure.status === 404 || code === "export_unavailable") return "内容或会话暂时无法导出，请核对当前世界、玩家身份和最新资料。";
  return "此次导出未能完成。请重新读取后再试；已有资料和聊天不会被修改。";
}

function warningMessage(code: string): string {
  const messages: Record<string, string> = {
    dreamtalk_fields_in_extension: "背景、说话方式等补充资料保存在 dreamtalk 扩展中；重新导入 dreamtalk 可恢复，其他应用可能忽略。多段对话示例在标准字段中用空行连接。",
    export_asset_reference_not_packaged: "该资源只导出引用信息，不包含图片文件。",
    v3_field_not_representable_in_v2: "该 V3 专有字段无法保存在 V2 格式中。",
    lore_title_not_representable_in_st_world_info: "此条目的独立标题与备注不同，酒馆标准格式仅保留备注。",
    multiple_lore_collections_require_selection: "存在多份内嵌世界书；不会自动合并，请分别导出所需世界书。",
    v3_use_regex_supplied_by_export_policy: "未明确设置的关键词正则规则使用了本次选择。",
    source_uid_reassigned: "条目编号已转换为导出文件内的稳定编号。",
    source_unsupported_semantic_preserved: "原始格式中不支持的字段已保留，其他应用如何解释取决于其实现。",
  };
  return messages[code] ?? "目标格式不能完整表示此字段，或原始扩展只能在同格式中保留；请核对后决定是否保存。";
}

async function saveExport(client: CoreClient, request: FileExportRequest, filename: string, signal: AbortSignal): Promise<string | null> {
  if (isTauri()) return invoke<string | null>("save_file_export", { request, filename });
  const blob = await client.fileExport(request, signal);
  if (signal.aborted) return null;
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a"); link.href = url; link.download = filename;
    document.body.append(link); link.click(); link.remove();
    return "已交给浏览器下载，请在下载列表查看文件。";
  } finally { window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
}

type Props = { client: CoreClient; worldId: string; onClose: () => void } & (
  { item: WorldContentItem; conversationId?: never } | { conversationId: string; item?: never }
);

export function FileExportDialog({ client, worldId, item, conversationId, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null), headingId = useId();
  const lifetime = useRef<AbortController | null>(null), saveLock = useRef(false);
  const [format, setFormat] = useState<ContentExportFormat | "txt" | "json">(item ? item.kind === "character" ? "character_card_v2" : "sillytavern_world_info" : "txt");
  const choices = item ? item.kind === "character" ? item.characters : item.lorebooks : [];
  const [contentId, setContentId] = useState(choices[0]?.id ?? "");
  const [useRegex, setUseRegex] = useState(false);
  const [info, setInfo] = useState<ContentExportInfo | null>(null);
  const [chat, setChat] = useState<ChatExportInfo | null>(null);
  const [reading, setReading] = useState(true), [saving, setSaving] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  useDesktopUpdateBlock(saving ? "文件正在导出。" : null);
  useEffect(() => {
    const element = dialog.current; element?.showModal();
    return () => { lifetime.current?.abort(); element?.close(); };
  }, []);
  useEffect(() => {
    const request = new AbortController(); lifetime.current = request;
    setReading(true); setInfo(null); setChat(null); setError(""); setNotice("");
    const task = item ? client.contentExportInfo(worldId, item, format as ContentExportFormat, contentId, useRegex, request.signal)
      .then(result => { if (!request.signal.aborted) setInfo(result); })
      : client.chatExportInfo(worldId, conversationId!, request.signal).then(result => { if (!request.signal.aborted) setChat(result); });
    void task.catch(failure => { if (!request.signal.aborted) setError(failureMessage(failure)); })
      .finally(() => { if (!request.signal.aborted) setReading(false); });
    return () => request.abort();
  }, [client, worldId, item, conversationId, contentId, useRegex, revision, format]);
  const save = async () => {
    if (saveLock.current || reading || !lifetime.current || !info && !chat) return;
    const request: FileExportRequest = item && info ? {
      kind: "content", world_id: worldId, item_id: item.import_id, format: format as ContentExportFormat,
      content_id: contentId, reviewed_hash: item.reviewed_hash, expected_digest: info.digest, use_regex: useRegex,
    } : {
      kind: "chat", world_id: worldId, item_id: conversationId!, format: format as "txt" | "json",
      player_id: chat!.player.id, expected_digest: chat!.digest, through_position: chat!.through_position,
    };
    const filename = info?.filename ?? chat!.filenames[format as "txt" | "json"];
    saveLock.current = true; setSaving(true); setError(""); setNotice("");
    try {
      const path = await saveExport(client, request, filename, lifetime.current.signal);
      if (!lifetime.current.signal.aborted) setNotice(path ? isTauri() ? `已保存到：${path}` : path : "已取消保存。可以重新选择位置。");
    } catch (failure) { if (!lifetime.current.signal.aborted) setError(failureMessage(failure)); }
    finally { saveLock.current = false; setSaving(false); }
  };
  return createPortal(<dialog ref={dialog} className="file-export-dialog" aria-labelledby={headingId} onCancel={event => { event.preventDefault(); if (!saveLock.current) onClose(); }}>
    <header className="section-heading export-heading"><div><h2 id={headingId}>{item ? item.kind === "character" ? "导出角色卡" : "导出世界书" : "导出聊天记录"}</h2><p>{item ? "保存当前已确认的资料。" : "保存当前会话的完整历史。"}</p></div><button type="button" className="text-action" disabled={saving} onClick={onClose}>关闭</button></header>
    <label className="field"><span>文件格式</span><select value={format} disabled={saving} onChange={event => setFormat(event.target.value as typeof format)}>{item ? item.kind === "character" ? <><option value="character_card_v2">角色卡 V2 · JSON</option><option value="character_card_v3">角色卡 V3 · JSON</option></> : <option value="sillytavern_world_info">SillyTavern World Info · JSON</option> : <><option value="txt">TXT · 便于阅读</option><option value="json">JSON · 保留身份、原文与时间</option></>}</select></label>
    {choices.length > 1 && <label className="field"><span>选择资料</span><select disabled={saving} value={contentId} onChange={event => setContentId(event.target.value)}>{choices.map(choice => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label>}
    {format === "character_card_v3" && <label className="export-check"><input type="checkbox" disabled={saving} checked={useRegex} onChange={event => setUseRegex(event.target.checked)} /><span>未明确规则的内嵌世界书关键词按正则处理<small>默认不勾选：按普通文本处理；原有明确规则会保留。</small></span></label>}
    {reading ? <p role="status">正在读取导出信息…</p> : chat ? <p className="export-details">{chat.world_name} · {chat.title}<br />共 {chat.message_count.toLocaleString("zh-CN")} 条已保存消息。导出范围固定到本次读取时，尚未保存的回复不包含在内。</p> : info ? <p className="export-details">{info.filename} · {(info.size / 1024).toFixed(1)} KB</p> : null}
    {item ? <p className="inline-hint">只导出资料，不包含聊天、运行状态、阵营或地点配置；JSON 不打包头像图片。世界书会包含本份资料的全部条目，包括设为隐藏的条目。</p> : <p className="inline-hint">按消息顺序导出，保留发言者与时间。JSON 是 dreamtalk 记录格式；当前未提供聊天文件导入。不会附带记忆、提示词或模型密钥。</p>}
    {item?.kind === "lorebook" && <p className="inline-hint">条目的独立标题、备注、优先级和排列顺序通过 dreamtalk 扩展保留；其他应用可能忽略这些补充字段。</p>}
    {!!info?.warnings.length && <section className="export-warnings"><h3>格式转换提示（{info.warnings.length}）</h3><ul>{info.warnings.map((warning, index) => <li key={`${warning.code}:${warning.path}:${index}`}>{warningMessage(warning.code)}{warning.path && <small>{warning.path}</small>}</li>)}</ul></section>}
    {error && <p className="app-alert" role="alert">{error}</p>}{notice && <p className="app-notice export-notice" role="status">{notice}</p>}
    <div className="profile-actions"><button type="button" className="secondary-button" disabled={saving || reading} onClick={() => setRevision(old => old + 1)}>重新读取</button><button type="button" className="primary-button" disabled={saving || reading || !info && !chat} onClick={() => void save()}>{saving ? "正在保存文件…" : info?.warnings.length ? "确认并另存为" : "另存为"}</button></div>
    <p className="inline-hint">只读取本地记录，不调用模型，也不会修改或删除原内容。</p>
  </dialog>, document.body);
}

export function ContentExportButton({ client, worldId, item, disabled = false }: {
  client: CoreClient; worldId: string; item: WorldContentItem; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className="text-action" disabled={disabled} onClick={() => setOpen(true)}>导出{item.kind === "character" ? "角色卡" : "世界书"}</button>{open && <FileExportDialog client={client} worldId={worldId} item={item} onClose={() => setOpen(false)} />}</>;
}
