import { useCallback, useEffect, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { useDesktopUpdateBlock } from "./DesktopUpdates";
import { CoreClient, CoreRequestError, type ChatMediaAttachment, type ChatMediaSettings, type StickerEntry, type StickerLibrary } from "@dreamtalk/api-client";
import "./chat-media.css";

function failureText(error: unknown): string {
  const code = error instanceof CoreRequestError ? error.code ?? "" : typeof error === "string" ? error : "";
  const captionFailures = ({
    media_caption_local_timeout: "本机图片分析等待超时（最长3分钟，包含排队和模型首次加载）。已保留素材和原说明，不会自动重试。",
    media_caption_timeout: "云端图片分析等待超时。已保留素材和原说明；本次可能已计费，不会自动重试。",
    media_caption_queue_timeout: "图片分析排队等待超时。已保留素材和原说明，不会自动重试。",
    media_caption_connection_failed: "未能连接图片分析服务。请在设置中核对服务地址，并检查或启动服务。已保留素材和原说明。",
    media_caption_auth_failed: "图片分析服务拒绝了凭据，请核对API密钥和服务权限。已保留素材和原说明。",
    media_caption_not_found: "图片分析服务未找到请求的模型或接口，请核对服务地址和完整视觉模型名称。已保留素材和原说明。",
    media_caption_provider_busy: "图片分析服务当前繁忙或暂不可用。已保留素材和原说明，不会自动重试。",
    media_caption_request_invalid: "图片分析服务未接受当前请求，请核对服务地址、模型的图片能力及服务兼容性。已保留素材和原说明。",
    media_caption_provider_failed: "图片分析服务返回内部错误，可能涉及模型加载或资源不足；具体原因需服务日志确认。已保留素材和原说明，不会自动重试。",
    media_caption_response_limit: "图片分析服务返回的数据过大。已保留素材和原说明，不会自动重试。",
    media_caption_response_invalid: "图片分析服务返回的格式无法读取。已保留素材和原说明，不会自动重试。",
    media_caption_output_limit: "图片分析已达到设置的输出Token上限，说明尚未完整结束。可调高上限后手动重新分析；素材和原说明已保留。",
    media_caption_incomplete: "图片分析服务没有返回完整结束结果。已保留素材和原说明，不会自动重试。",
    media_caption_invalid: "图片分析服务未返回有效说明。已保留素材和原说明，不会自动重试。",
    media_caption_in_progress: "这张图片仍在分析，请等待完成；不会重复提交。",
    media_reference_invalid: "旧图片密钥引用不兼容，请重新填写API密钥并保存。",
    media_credential_scope_invalid: "图片密钥尚未就绪或不属于当前世界，请在桌面版重新填写并保存。",
    media_caption_endpoint_invalid: "图片分析服务地址格式不正确，请核对设置中的服务地址。",
  } as Record<string, string>)[code];
  if (captionFailures) return captionFailures;
  const known = ({ media_local_folder_required: "请选择已部署的图片模型目录。", media_local_folder_invalid: "请选择图片模型部署目录，其中应包含ollama和models文件夹。", media_local_config_invalid: "图片模型目录未能保存，请重新选择目录。", media_local_port_occupied: "本机图片服务端口被其他程序占用；已有程序已保留。", media_local_start_timeout: "图片服务启动尚未完成，可稍后再检查。", media_local_probe_timeout: "图片服务未及时响应，可稍后再检查。", media_local_start_failed: "图片服务未能启动，请核对模型部署目录。", media_local_unavailable: "本机图片服务未能连接，请检查服务。", update_busy: "程序正在更新，稍后再操作图片服务。", world_not_found: "当前世界已不可用，请返回书架重新选择。", media_asset_unavailable: "这张图片已不可用，请刷新后再试。", media_character_unavailable: "这个角色已不可用，请重新选择角色。", media_sticker_unavailable: "这个表情已不可用，请刷新表情库。", media_image_size_limit: "图片不能超过8 MB。", media_image_format: "请选择PNG、JPG、WebP或GIF。", media_image_invalid: "图片无法读取，请换一份文件。", media_image_dimensions: "图片尺寸过大，请缩小后导入。", media_caption_not_configured: "先在设置中配置图片分析模型。", media_caption_daily_limit: "今天的图片分析次数已用完。", core_read_timeout: "读取超时，请确认程序已连接核心服务后重试。", media_caption_failed: "图片分析未完成；已保留素材和原说明，不会自动重试。", media_caption_local_required: "本地分析仅支持本机Ollama及本地模型。", media_caption_https_required: "云端分析地址需要使用HTTPS。", media_caption_consent_required: "启用云端图片分析前，请确认图片外发和可能的费用。" } as Record<string, string>)[code];
  if (known) return known;
  if (error instanceof CoreRequestError) {
    if (error.status === 404) return "当前程序与核心服务的表情功能接口不匹配，请退出旧程序并使用最新版完整程序重新打开。";
    if (error.status === 401 || error.status === 403) return "与核心服务的连接已失效，请重新打开程序后再试。";
    if (error.status >= 500) return "核心服务未能处理请求，请重试；若持续出现，请反馈此提示。";
  }
  if (error instanceof DOMException && (error.name === "AbortError" || error.name === "TimeoutError")) return "读取超时，请确认程序已连接核心服务后重试。";
  return "操作未完成，请确认核心服务连接后重试。";
}

export function MediaImage({ client, worldId, asset, description, onLoad }: { client: CoreClient; worldId: string; asset: string; description: string; onLoad?: () => void }) {
  const element = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { setVisible(true); observer.disconnect(); } }, { rootMargin: "200px" });
    if (element.current) observer.observe(element.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let active = true, objectUrl: string | null = null;
    const controller = new AbortController();
    setFailed(false); setUrl(null);
    void client.mediaImage(worldId, asset, controller.signal).then(blob => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [client, worldId, asset, visible, retry]);
  return <span className="media-image-frame" ref={element}>{url ? <img src={url} alt={description || "表情图片"} loading="lazy" onLoad={onLoad} /> : failed ? <span role="status">图片暂未读取<button type="button" className="text-action" onClick={() => setRetry(value => value + 1)}>重试</button></span> : <span className="media-placeholder" aria-label="正在读取图片" />}</span>;
}

export function MessageMedia({ client, worldId, media }: { client: CoreClient; worldId: string; media?: ChatMediaAttachment | null }) {
  if (!media) return null;
  return <figure className={`message-media ${media.kind}`}><MediaImage client={client} worldId={worldId} asset={media.asset_id} description={media.description} />{media.source_url && <details className="media-source"><summary>图片来源</summary><a href={media.source_url} target="_blank" rel="noopener noreferrer">查看来源页面</a></details>}</figure>;
}

export function StickerPicker({ client, worldId, selected, onSelect, disabled }: { client: CoreClient; worldId: string; selected: StickerEntry | null; onSelect: (entry: StickerEntry | null) => void; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<StickerEntry[]>([]);
  const [page, setPage] = useState(0), [more, setMore] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false), [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let active = true; const controller = new AbortController();
    setLoading(true); setError("");
    const timer = window.setTimeout(() => { void client.stickers(worldId, "personal", undefined, page * 100, query, controller.signal).then(result => { if (active) { setItems(result.items); setMore(result.has_more); } }).catch(failure => { if (active) setError(failureText(failure)); }).finally(() => { if (active) setLoading(false); }); }, 200);
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [client, worldId, open, query, page]);
  return <div className="sticker-picker"><div className="profile-actions"><button type="button" className="text-action" aria-expanded={open} disabled={disabled} onClick={() => setOpen(value => !value)}>表情</button>{selected && <><span>已选：{selected.description || "表情"}</span><button type="button" className="text-action" disabled={disabled} onClick={() => onSelect(null)}>取消选择</button></>}</div>{open && <div className="sticker-picker-body"><label className="field"><span>我的表情</span><input type="search" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} placeholder="搜索说明…" /></label>{error && <p className="app-alert" role="alert">{error}</p>}{loading ? <p role="status">正在读取…</p> : items.length ? <div className="sticker-grid">{items.map(entry => <button className="sticker-choice" type="button" key={entry.entry_id} disabled={disabled} aria-label={`选择${entry.description || "表情"}`} onClick={() => { onSelect(entry); setOpen(false); }}><MediaImage client={client} worldId={worldId} asset={entry.asset_id} description={entry.description} /><span>{entry.description || "未填写说明"}</span></button>)}</div> : <p className="inline-hint">没有找到表情。在通讯录的“表情包”中导入我的表情。</p>}<div className="profile-actions"><button type="button" disabled={page === 0 || loading} onClick={() => setPage(value => value - 1)}>上一页</button><span>第{page + 1}页</span><button type="button" disabled={!more || loading} onClick={() => setPage(value => value + 1)}>下一页</button></div></div>}</div>;
}

function StickerEditor({ client, worldId, entry, onChanged, disabled, onBusy, onDraft }: { client: CoreClient; worldId: string; entry: StickerEntry; onChanged: () => void; disabled: boolean; onBusy: (busy: boolean) => void; onDraft: (id: string, dirty: boolean) => void }) {
  const [description, setDescription] = useState(entry.description);
  useEffect(() => { onDraft(entry.entry_id, description !== entry.description); return () => onDraft(entry.entry_id, false); }, [entry.entry_id, entry.description, description, onDraft]);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const act = async (operation: () => Promise<unknown>) => {
    if (busy || disabled) return;
    setBusy(true); onBusy(true); setError("");
    try { await operation(); onChanged(); } catch (failure) { setError(failureText(failure)); }
    finally { setBusy(false); onBusy(false); }
  };
  return <li className="sticker-editor"><MediaImage client={client} worldId={worldId} asset={entry.asset_id} description={entry.description} /><label className="field"><span>内容、语气和适用场景</span><textarea value={description} maxLength={200} rows={2} disabled={busy || disabled} onChange={event => setDescription(event.target.value)} /></label><div className="profile-actions"><button type="button" disabled={busy || disabled || description === entry.description} onClick={() => void act(() => client.editSticker(worldId, entry.entry_id, description))}>保存说明</button><button type="button" className="text-action" disabled={busy || disabled || description === entry.description} onClick={() => setDescription(entry.description)}>放弃修改</button><button type="button" disabled={busy || disabled || (entry.caption_state === "running" || entry.caption_state === "done")} onClick={() => void act(() => client.captionMedia(worldId, entry.asset_id, entry.entry_id))}>{entry.caption_state === "failed" ? "重新分析" : "分析图片"}</button><button type="button" className="text-action destructive-action" disabled={busy || disabled} onClick={() => { if (window.confirm("从这个库中移除？聊天历史中的图片会保留。")) void act(() => client.removeSticker(worldId, entry.entry_id)); }}>移除</button></div>{error && <p className="app-alert" role="alert">{error}</p>}{entry.caption_state === "failed" && <small>上次分析未完成，可手动填写说明。</small>}</li>;
}

export function StickerLibraries({ client, worldId, people, selectedRoot, onDirtyChange }: { client: CoreClient; worldId: string; people: { root_import_id: string; name: string }[]; selectedRoot?: string | null; onDirtyChange?: (dirty: boolean) => void }) {
  const [library, setLibrary] = useState<StickerLibrary>("public");
  const [dirtyEntries, setDirtyEntries] = useState<Set<string>>(new Set());
  const onDraft = useCallback((id: string, dirty: boolean) => setDirtyEntries(current => {
    if (current.has(id) === dirty) return current;
    const next = new Set(current); if (dirty) next.add(id); else next.delete(id); return next;
  }), []);
  const [root, setRoot] = useState(selectedRoot ?? people[0]?.root_import_id ?? "");
  const [items, setItems] = useState<StickerEntry[]>([]), [more, setMore] = useState(false);
  const [page, setPage] = useState(0), [refresh, setRefresh] = useState(0);
  const [query, setQuery] = useState(""), [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(false), [error, setError] = useState("");
  useEffect(() => { onDirtyChange?.(busy || Boolean(description) || dirtyEntries.size > 0); return () => onDirtyChange?.(false); }, [busy, description, dirtyEntries, onDirtyChange]);
  useEffect(() => {
    if (library === "character" && !root) { setItems([]); return; }
    let active = true; const controller = new AbortController();
    setLoading(true); setError("");
    const timer = window.setTimeout(() => { void client.stickers(worldId, library, library === "character" ? root : undefined, page * 100, query, controller.signal).then(result => { if (active) { setItems(result.items); setMore(result.has_more); } }).catch(failure => { if (active) setError(failureText(failure)); }).finally(() => { if (active) setLoading(false); }); }, 200);
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [client, worldId, library, root, page, query, refresh]);
  const upload = async (files: FileList | null) => {
    if (!files?.length || busy) return;
    setBusy(true); setError("");
    try { for (const file of Array.from(files)) await client.importSticker(worldId, library, file, description.trim() || file.name.replace(/\.[^.]+$/, "").slice(0, 200), library === "character" ? root : undefined); setDescription(""); }
    catch (failure) { setError(failureText(failure)); }
    finally { setBusy(false); setRefresh(value => value + 1); }
  };
  return <section className="sticker-libraries"><div className="section-heading"><h2>表情包</h2><p>公共和角色专属库只在当前世界使用。我的表情可跨世界使用，发给角色后会加入其专属库。</p></div><div className="profile-actions">{([ ["public", "公共表情"], ["character", "角色专属"], ["personal", "我的表情"] ] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={library === value} disabled={busy || dirtyEntries.size > 0} onClick={() => { setLibrary(value); setPage(0); }}>{label}</button>)}</div>{library === "character" && <label className="field"><span>绑定角色</span><select value={root} disabled={busy || dirtyEntries.size > 0} onChange={event => { setRoot(event.target.value); setPage(0); }}><option value="">选择角色</option>{people.map(person => <option key={person.root_import_id} value={person.root_import_id}>{person.name}</option>)}</select></label>}<div className="sticker-import"><label className="field"><span>导入说明（批量导入时共用，可稍后逐张修改）</span><input value={description} maxLength={200} disabled={busy} onChange={event => setDescription(event.target.value)} placeholder="例如：胡桃害羞，捂脸，适合被夸奖时使用" /></label><label className="field"><span>{busy ? "正在处理素材…" : "导入PNG、JPG、WebP或GIF，每张最多8 MB"}</span><input type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif" disabled={busy || (library === "character" && !root)} onChange={event => { void upload(event.target.files); event.target.value = ""; }} /></label></div><p className="inline-hint">图片分析需先在设置中配置。分析只使用图片，不附带聊天记录；已分析素材复用说明。</p><label className="field"><span>搜索这个库</span><input type="search" value={query} disabled={busy || dirtyEntries.size > 0} onChange={event => { setQuery(event.target.value); setPage(0); }} /></label>{error && <p className="app-alert" role="alert">{error}</p>}{loading ? <p role="status">正在读取表情库…</p> : items.length ? <ul className="sticker-management-grid">{items.map(entry => <StickerEditor key={`${entry.entry_id}:${entry.description}:${entry.caption_state}`} client={client} worldId={worldId} entry={entry} onChanged={() => setRefresh(value => value + 1)} disabled={busy} onBusy={setBusy} onDraft={onDraft} />)}</ul> : <p className="inline-hint">这个库中还没有匹配的表情。导入图片并填写说明后，角色才能按场景选择。</p>}<div className="profile-actions"><button type="button" disabled={page === 0 || busy || dirtyEntries.size > 0} onClick={() => setPage(value => value - 1)}>上一页</button><span>第{page + 1}页</span><button type="button" disabled={!more || busy || dirtyEntries.size > 0} onClick={() => setPage(value => value + 1)}>下一页</button><button type="button" disabled={busy || dirtyEntries.size > 0} onClick={() => setRefresh(value => value + 1)}>刷新库</button></div></section>;
}

type LocalImageStatus = { model_root: string | null; state: string };

export function ChatMediaSettingsPanel({ client, worldId, onDirtyChange }: { client: CoreClient; worldId: string; onDirtyChange: (dirty: boolean) => void }) {
  const [value, setValue] = useState<ChatMediaSettings | null>(null), [saved, setSaved] = useState<ChatMediaSettings | null>(null);
  const [key, setKey] = useState(""), [busy, setBusy] = useState(false), [feedback, setFeedback] = useState("");
  const [usage, setUsage] = useState<number | null>(null), [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [local, setLocal] = useState<LocalImageStatus | null>(null);
  const pendingReference = useRef<string | null>(null), saving = useRef(false);
  const dirty = JSON.stringify(value) !== JSON.stringify(saved) || Boolean(key) || Boolean(pendingReference.current) || busy;
  useDesktopUpdateBlock(busy ? "正在处理图片设置或本机服务。" : dirty ? "图片设置尚未保存。" : null);
  useEffect(() => { onDirtyChange(dirty); return () => onDirtyChange(false); }, [dirty, onDirtyChange]);
  useEffect(() => {
    let active = true; const controller = new AbortController();
    setLoading(true); setFeedback(""); setValue(null); setSaved(null); setUsage(null);
    pendingReference.current = null; setKey("");
    void client.mediaSettings(worldId, controller.signal).then(settings => { if (active) { setValue(settings); setSaved(settings); } }).catch(failure => { if (active) setFeedback(`未能读取设置。${failureText(failure)}`); }).finally(() => { if (active) setLoading(false); });
    void client.mediaUsage(worldId).then(result => { if (active) setUsage(result.caption_calls); }).catch(() => undefined);
    return () => { active = false; controller.abort(); };
  }, [client, worldId, refresh]);
  useEffect(() => {
    if (!isTauri() || value?.caption_route !== "ollama") return;
    let active = true;
    void invoke<LocalImageStatus>("local_image_status").then(status => { if (active) setLocal(status); }).catch(() => { if (active) setLocal(null); });
    return () => { active = false; };
  }, [value?.caption_route, refresh]);
  const prepareLocal = async (choose: boolean) => {
    if (busy) return;
    setBusy(true); setFeedback("");
    try {
      let modelRoot: string | null = null;
      if (choose) { modelRoot = await invoke<string | null>("choose_local_image_folder"); if (!modelRoot) return; }
      const status = await invoke<LocalImageStatus>("prepare_local_image", { modelRoot });
      setLocal(status); setFeedback("图片服务已启动。检查服务不会分析图片；保存模型设置后，服务会随dreamtalk启动。");
    } catch (failure) { setFeedback(failureText(failure)); }
    finally { setBusy(false); }
  };
  const update = (patch: Partial<ChatMediaSettings>) => setValue(current => current ? { ...current, ...patch } : current);
  const save = async () => {
    if (!value || busy || saving.current) return;
    saving.current = true;
    setBusy(true); setFeedback("");
    try {
      const next = { ...value };
      if (isTauri() && next.caption_route === "ollama" && next.caption_model.trim() && ["http://127.0.0.1:11434", "http://localhost:11434"].includes(next.caption_endpoint.replace(/\/$/, ""))) {
        setLocal(await invoke<LocalImageStatus>("prepare_local_image", { modelRoot: null }));
      }
      if (key) {
        if (!isTauri()) throw new Error("desktop_credentials_required");
        // Read the persisted reference before pruning, including an uncertain
        // previous save whose response may have been lost. Keep the active key.
        const current = await client.mediaSettings(worldId);
        await invoke("forget_media_credentials", { worldId, secretRef: null, keepSecretRef: current.secret_ref && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(current.secret_ref) ? current.secret_ref : null });
        next.secret_ref = pendingReference.current ?? crypto.randomUUID();
        pendingReference.current = next.secret_ref;
        await invoke("media_credential_put", { worldId, secretRef: next.secret_ref, secret: key });
      } else if (pendingReference.current) next.secret_ref = pendingReference.current;
      const result = await client.saveMediaSettings(worldId, next);
      setSaved(result); setValue(result); setKey(""); pendingReference.current = null;
      setFeedback("已保存。保存设置不会发起搜索或图片分析。");
      if (isTauri()) {
        try { await invoke("forget_media_credentials", { worldId, secretRef: null, keepSecretRef: result.secret_ref }); }
        catch { setFeedback("设置已保存；旧密钥清理未完成，下次保存会再次清理。"); }
      }
    } catch (failure) { setFeedback(key && !(failure instanceof CoreRequestError) ? (isTauri() ? "密钥未能安全保存，原设置已保留。请稍后重试；若持续失败，请反馈此提示。" : "云端密钥需要在桌面版配置。") : failureText(failure)); }
    finally { saving.current = false; setBusy(false); }
  };
  return <section className="chat-media-settings">{value ? <><label className="speech-check"><input type="checkbox" checked={value.enabled} disabled={busy} onChange={event => update({ enabled: event.target.checked })} /><span>允许角色按聊天环境发送表情或图片</span></label><label className="speech-check"><input type="checkbox" checked={Boolean(value.unlimited_stickers)} disabled={busy} onChange={event => update({ unlimited_stickers: event.target.checked })} /><span>不限制角色发送表情包的频率<small>开启后每轮都可以发表情，仍由角色按聊天需要选择；每轮最多一张，群聊所有角色合计。</small></span></label><label className="field"><span>{value.unlimited_stickers ? "普通图片发送频率" : "发送频率"}</span><input type="number" min={1} max={1000} value={value.frequency} disabled={busy} onChange={event => update({ frequency: Number(event.target.value) })} /><small>任意连续{value.frequency || "N"}轮聊天，角色合计最多发送一张{value.unlimited_stickers ? "普通图片；表情包不受这个间隔限制" : "表情或图片"}。达到间隔也不必发送；群聊所有角色共用每轮限额。</small></label><label className="speech-check"><input type="checkbox" checked={value.online_enabled} disabled={busy} onChange={event => update({ online_enabled: event.target.checked })} /><span>允许联网找图<small>表情仅在需要发送且公共与专属库没有匹配时搜索。普通图片按聊天主题搜索；每轮最多一次搜索，失败保留文字。</small></span></label><details><summary>图片分析与用量</summary><div className="media-analysis-fields"><label className="speech-check"><input type="checkbox" checked={value.auto_caption} disabled={busy} onChange={event => update({ auto_caption: event.target.checked })} /><span>自动分析新导入或联网获取的素材<small>仅处理新图；已有分析结果不会重复调用。GIF分析首帧，播放保留动画。</small></span></label><label className="field"><span>分析方式</span><select value={value.caption_route} disabled={busy} onChange={event => update({ caption_route: event.target.value as "ollama" | "compatible", caption_endpoint: event.target.value === "ollama" ? "http://127.0.0.1:11434" : "", secret_ref: null, remote_caption_consent: false })}><option value="ollama">本机Ollama视觉模型</option><option value="compatible">云端视觉模型（Chat Completions兼容）</option></select></label>{value.caption_route === "ollama" && isTauri() && ["http://127.0.0.1:11434", "http://localhost:11434"].includes(value.caption_endpoint.replace(/\/$/, "")) && <div className="speech-local-service"><p role="status">{local?.state === "ready" ? "本机图片服务已启动" : "本机图片服务尚未就绪"}</p><div className="profile-actions"><button type="button" disabled={busy} onClick={() => void prepareLocal(false)}>检查并启动图片服务</button><button type="button" className="text-action" disabled={busy} onClick={() => void prepareLocal(true)}>选择模型目录</button></div>{local?.model_root && <details><summary>查看模型目录</summary><p className="inline-hint">{local.model_root}</p></details>}</div>}<label className="field"><span>服务地址{value.caption_route === "compatible" ? "（填至/v1，不含/chat/completions）" : ""}</span><input value={value.caption_endpoint} disabled={busy} onChange={event => update({ caption_endpoint: event.target.value })} /></label><label className="field"><span>完整视觉模型名称</span><input value={value.caption_model} disabled={busy} onChange={event => update({ caption_model: event.target.value })} /></label>{value.caption_route === "compatible" && <><label className="field"><span>API密钥{value.secret_ref ? "（已保存，留空保留）" : ""}</span><input type="password" autoComplete="new-password" value={key} disabled={busy} onChange={event => setKey(event.target.value)} /></label><label className="speech-check"><input type="checkbox" checked={value.remote_caption_consent} disabled={busy} onChange={event => update({ remote_caption_consent: event.target.checked })} /><span>我同意将待分析图片发送至上述服务，并承担其可能产生的费用。聊天正文与角色资料不附带发送。</span></label></>}{value.caption_route === "compatible" && <label className="field"><span>全机每日云端图片分析次数上限（UTC日期，0表示禁止）</span><input type="number" min={0} max={1000} value={value.daily_caption_limit} disabled={busy} onChange={event => update({ daily_caption_limit: Number(event.target.value) })} /></label>}<label className="field"><span>每次分析输出Token上限</span><input type="number" min={32} max={1024} value={value.caption_output_tokens} disabled={busy} onChange={event => update({ caption_output_tokens: Number(event.target.value) })} /></label><p className="inline-hint">{value.caption_route === "ollama" ? "本机图片分析不限次数。服务随dreamtalk启动；开启程序的开机后台启动后，也会随登录启动。模型首次分析时加载，空闲后释放显存。" : <>今天已提交{usage ?? "…"}次云端分析。失败与未知结果也计次；输入图片也可能收费，次数与输出上限不等于账单金额上限。</>}</p></div></details><button type="button" className="primary-button" disabled={busy || !dirty} onClick={() => void save()}>{busy ? "正在保存…" : "保存设置"}</button></> : loading ? <p role="status">正在读取设置…</p> : <button type="button" onClick={() => setRefresh(old => old + 1)}>重新读取设置</button>}{feedback && <p className="app-alert" role="status">{feedback}</p>}</section>;
}
