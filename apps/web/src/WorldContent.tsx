import { UnplacedCharactersEditor } from "./UnplacedCharactersEditor";
import { ContentExportButton } from "./FileExportDialog";
import { InitialLocationChoice } from "./InitialLocationChoice";
import { useCallback, useEffect, useRef, useState } from "react";
import { CharacterLocationEditor, LocationManager, LocationMap, useLocationDirectory } from "./LocationWorkspace";
import { ContentEditor, ResearchDetails } from "./ContentEditor";
import { CoreClient, CoreRequestError, type WorldContentItem } from "@dreamtalk/api-client";
import { ContactAvatar, FactionManager, SocialGraph } from "./ContactSocial";
import type { SocialSnapshot } from "@dreamtalk/api-client";
import { CelestialEmpty, DirectorySearch, WorkspaceIcon } from "./WorkspacePrimitives";
import { useDesktopUpdateBlock } from "./DesktopUpdates";

function originalCardGreeting(authored: Record<string, unknown>): string | null {
  const card = authored.character_card;
  if (!card || typeof card !== "object" || Array.isArray(card)) return null;
  const greeting = (card as Record<string, unknown>).first_mes;
  return typeof greeting === "string" && greeting.trim() ? greeting : null;
}

type ExposureFeedback = { entryId: string; message: string; error: boolean };

export function ContentDetails({ item, onCommonChange, changingEntry, commonDisabled = false, exposureFeedback, onCommonRefresh, hideCharacterTitle = false }: {
  item: WorldContentItem;
  hideCharacterTitle?: boolean;
  onCommonChange?: (entryId: string, common: boolean) => void;
  changingEntry?: string | null;
  commonDisabled?: boolean; exposureFeedback?: ExposureFeedback | null; onCommonRefresh?: () => void;
}) {
  return <div className="content-details">
    {item.characters.map(character => {
      const greeting = originalCardGreeting(character.authored_instructions);
      return <section key={character.id}>{!hideCharacterTitle && <h2>{character.name}</h2>}{([
      ["角色描述", character.description], ["性格", character.personality],
      ["背景", character.background], ["情境", character.scenario],
      ["说话方式", character.speech_guidance], ["创作者备注", character.creator_notes],
      ["标签", character.tags.join("、")], ["对话示例", character.example_dialogue.join("\n")],
    ] as const).filter(([, value]) => value).map(([label, value]) => <div key={label}><h3>{label}</h3><p>{value}</p></div>)}
      {greeting && <div><h3>角色卡开场白（原文）</h3><p>{greeting}</p><small>回复可参考其语气；不会自动作为消息发送。</small></div>}
    </section>;
    })}
    {item.characters.some(character => Object.keys(character.authored_instructions).length > 0) && <details><summary>角色卡附加设定</summary>{item.characters.map(character => <pre key={character.id}>{JSON.stringify(character.authored_instructions, null, 2)}</pre>)}</details>}
    {item.research && <ResearchDetails research={item.research} />}
    {item.lorebooks.map(book => <section key={book.id}><h2>{book.name}</h2><p>{book.description}</p></section>)}
    {item.entries.length > 0 && <details><summary>世界书条目（{item.entries.length}）</summary><p className="inline-hint">设为公共背景后，条目按来源的常驻或关键词条件参与聊天和已开启的自动活动规划。规划匹配角色名和当前地点名，遵守后台生成类型限制。未触发的条目不会占用背景。</p>{item.entries.map((entry, index) => <div key={entry.id}><h3>{entry.title || `条目 ${index + 1}`}</h3>{entry.keywords.length > 0 && <p>关键词：{entry.keywords.join("、")}</p>}<p>{entry.content}</p>{!!entry.secondary_keywords?.length && <p>次级关键词：{entry.secondary_keywords.join("、")}</p>}{entry.activation_summary && <p className="inline-hint">{entry.activation_summary}</p>}{entry.planning_activation_summary && <p className="inline-hint">日常规划：{entry.planning_activation_summary}</p>}{!entry.enabled && <small>来源中已禁用；不会进入角色聊天。</small>}{onCommonChange && <label className="field"><span>角色可见范围</span><select value={entry.common ? "common" : "hidden"} disabled={!entry.enabled || commonDisabled || !!changingEntry} onChange={event => onCommonChange(entry.id, event.target.value === "common")}><option value="hidden">隐藏（默认）</option><option value="common">公共背景（所有角色可见）</option></select><small>选择后立即保存并核对，无需再次编辑或保存世界书。</small></label>}{exposureFeedback?.entryId === entry.id && <p className={exposureFeedback.error ? "app-alert" : "inline-hint"} role={exposureFeedback.error ? "alert" : "status"}>{exposureFeedback.message}{exposureFeedback.error && onCommonRefresh && <button type="button" className="text-action" disabled={commonDisabled || !!changingEntry} onClick={onCommonRefresh}>刷新可见范围</button>}</p>}</div>)}</details>}
  </div>;
}

const ignoreDirty = () => undefined;

function cardRemovalError(failure: unknown): string {
  return failure instanceof CoreRequestError && failure.code === "character_card_reply_running"
    ? "该角色参与的会话仍在生成回复。请等本轮结束，或停止生成后再删除。"
    : failure instanceof CoreRequestError && failure.code === "character_card_changed"
      ? "角色卡已有更新，请刷新并选择最新版本后删除。"
      : "删除结果尚未确认。请刷新列表核对；可以再次删除同一张卡，历史聊天会保留。";
}
function confirmCardRemoval(item: WorldContentItem) {
  return window.confirm(`删除角色卡“${item.characters[0]?.name ?? "此角色"}”？\n角色将从通讯录及后续活动中移除。历史消息和事件保留，已有私聊及包含该角色的群聊变为只读。重新导入会创建新的角色身份。`);
}

export function WorldImports({ client, worldId, onlyKind, onSaved, onDirtyChange = ignoreDirty, refreshKey = 0 }: {
  client: CoreClient; worldId: string; onlyKind?: "character" | "lorebook";
  onSaved?: () => void; onDirtyChange?: (dirty: boolean) => void;
  refreshKey?: number;
}) {
  const [editor, setEditor] = useState<{ kind: "character" | "lorebook"; item?: WorldContentItem } | null>(null);
  const active = useRef(true);
  const epoch = useRef(0);
  const commonWrite = useRef<symbol | null>(null);
  const contentRead = useRef(0);
  const pendingId = useRef<string | null>(null);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false; ++epoch.current; ++contentRead.current; commonWrite.current = null;
      if (pendingId.current) void client.discardWorldContent(worldId, pendingId.current).catch(() => undefined);
    };
  }, [client, worldId]);
  const [kind, setKind] = useState<"character" | "lorebook">(onlyKind ?? "character");
  const [replacement, setReplacement] = useState<WorldContentItem | null>(null);
  const [preview, setPreview] = useState<WorldContentItem | null>(null);
  const [initialLocation, setInitialLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const savedNotice = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (message && savedNotice.current) {
      savedNotice.current.scrollIntoView({ block: "center" });
      savedNotice.current.focus({ preventScroll: true });
    }
  }, [message]);
  const [error, setError] = useState("");
  const [accepted, setAccepted] = useState<WorldContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [changingEntry, setChangingEntry] = useState<string | null>(null);
  const [exposureFeedback, setExposureFeedback] = useState<ExposureFeedback | null>(null);
  useEffect(() => {
    let mounted = true; const read = ++contentRead.current; setLoading(true); setLoadFailed(false);
    void client.worldContent(worldId).then(items => { if (mounted && read === contentRead.current) { setAccepted(items); setExposureFeedback(null); setChangingEntry(null); } })
      .catch(() => { if (mounted && read === contentRead.current) { setLoadFailed(true); setError("无法读取当前世界的已保存内容，请点击“重新读取已保存内容”后再试。"); } })
      .finally(() => { if (mounted && read === contentRead.current) setLoading(false); });
    return () => { mounted = false; };
  }, [client, worldId, reload, refreshKey]);
  useEffect(() => { onDirtyChange(!!editor || !!preview || !!replacement || busy || !!changingEntry); }, [editor, preview, replacement, busy, changingEntry, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const upload = async (file: File) => {
    setError(""); setMessage("");
    if (file.size > 32 * 1024 * 1024) { setError("文件不能超过 32 MB。"); return; }
    setBusy(true);
    try {
      if (preview) { await client.discardWorldContent(worldId, preview.import_id); setPreview(null); }
      const result = await client.previewWorldContent(worldId, kind, file, replacement?.import_id);
      if (!active.current) { await client.discardWorldContent(worldId, result.import_id); return; }
      pendingId.current = result.import_id;
      setPreview(result);
    } catch (failure) { setError(failure instanceof CoreRequestError && failure.status === 409
      ? "该内容已更新，请重新打开管理页面并选择最新版本。"
      : "无法读取文件。请选择有效的角色卡或世界书；文件内容尚未保存。"); }
    finally { setBusy(false); }
  };
  const commit = async () => {
    if (!preview || (preview.kind === "character" && !replacement && !initialLocation)) return;
    setBusy(true); setError("");
    try {
      const saved = await client.commitWorldContent(worldId, preview, preview.kind === "character" && !replacement ? initialLocation : undefined);
      if (!active.current) return;
      onSaved?.();
      setAccepted(items => items.some(item => item.import_id === saved.import_id)
        ? items : [...items.filter(item => item.import_id !== saved.replaces_import_id), saved]);
      pendingId.current = null; setPreview(null); setReplacement(null);
      setMessage(saved.replaces_import_id ? "当前世界的内容已更新。" : preview.kind === "character" ? "已加入当前世界，可在通讯录查看角色。" : "世界书已加入当前世界。");
    } catch (failure) {
      setError(failure instanceof CoreRequestError && failure.code === "character_initial_location_pending"
        ? "角色卡已保存，但初始地点尚未确认。请核对世界身份和地点后再次确认；不会重复创建角色。" : failure instanceof CoreRequestError && failure.status === 422
        ? "预览已过期，请重新选择文件。" : failure instanceof CoreRequestError && failure.status === 409
          ? "该内容已有更新，当前预览无法覆盖。请重新选择最新版本。"
          : "未能确认保存结果。可以再次确认，同一次导入不会重复保存。");
    } finally { setBusy(false); }
  };
  const refreshAccepted = () => {
    if (commonWrite.current || busy || loading || editor || preview || replacement) return;
    setError(""); setMessage(""); setReload(value => value + 1);
  };
  const setCommon = async (importId: string, entryId: string, common: boolean) => {
    if (commonWrite.current || busy || loading || loadFailed || editor || preview || replacement) return;
    const job = Symbol(); const owner = epoch.current; commonWrite.current = job; ++contentRead.current;
    const valid = () => active.current && owner === epoch.current && commonWrite.current === job;
    setChangingEntry(entryId); setError(""); setMessage("");
    setExposureFeedback({ entryId, message: "正在保存并核对可见范围……", error: false });
    let writeFailed = false;
    try { await client.setCommonLore(worldId, importId, entryId, common); }
    catch { writeFailed = true; }
    try {
      if (!valid()) return;
      // A read reconciles a lost write response; it never repeats the mutation.
      const items = await client.worldContent(worldId);
      if (!valid()) return;
      setAccepted(items);
      const confirmed = items.find(item => item.import_id === importId)?.entries.find(entry => entry.id === entryId);
      if (!confirmed) {
        setError("世界书已有更新，请在当前版本重新选择可见范围。没有自动重写公开设置。");
        setExposureFeedback(null);
      } else if (confirmed.common === common) {
        setExposureFeedback({ entryId, error: false, message: common ? "已保存并核对：公共背景。无需再保存世界书。" : "已保存并核对：隐藏内容。" });
        onSaved?.();
      } else setExposureFeedback({ entryId, error: true, message: writeFailed ? "此次可见范围未保存，下面显示的是已保存状态，请重新选择后再核对。" : "读回的可见范围与本次选择不一致，可能已被其他操作修改。下面显示已保存状态，没有自动重写。" });
    } catch {
      if (valid()) setExposureFeedback({ entryId, error: true, message: "未能核对保存结果。请刷新可见范围；系统不会自动重复提交。" });
    } finally {
      if (valid()) setChangingEntry(null);
      if (commonWrite.current === job) commonWrite.current = null;
    }
  };
  const commonDisabled = loading || loadFailed || busy || !!editor || !!preview || !!replacement;
  const removeCard = async (item: WorldContentItem) => {
    if (commonDisabled || changingEntry || commonWrite.current || !confirmCardRemoval(item)) return;
    const owner = epoch.current, job = Symbol(); commonWrite.current = job; ++contentRead.current;
    setBusy(true); setError(""); setMessage("");
    try {
      await client.removeCharacterCard(worldId, item.import_id);
      if (!active.current || owner !== epoch.current) return;
      setAccepted(items => items.filter(value => value.import_id !== item.import_id));
      setMessage("角色卡已删除，历史消息与事件保留。相关会话可继续查看。"); onSaved?.();
    } catch (failure) { if (active.current && owner === epoch.current) setError(cardRemovalError(failure)); }
    finally { if (commonWrite.current === job) commonWrite.current = null; if (active.current && owner === epoch.current) setBusy(false); }
  };
  const visibleItems = accepted.filter(item => !onlyKind || item.kind === onlyKind);
  return <section className="settings-section import-section"><div className="section-heading"><h2>{onlyKind === "lorebook" ? "创建与导入世界书" : onlyKind === "character" ? "角色卡" : "角色卡与世界书"}</h2><p>直接创建、联网生成，或导入已有内容。确认后加入当前世界。</p></div>
    <div className="profile-actions">{onlyKind !== "lorebook" && <button type="button" className="secondary-button" disabled={loading || loadFailed || busy || !!changingEntry || !!preview || !!editor} onClick={() => { setEditor({ kind: "character" }); setError(""); setMessage(""); }}>新建角色卡</button>}{onlyKind !== "character" && <button type="button" className="secondary-button" disabled={loading || loadFailed || busy || !!changingEntry || !!preview || !!editor} onClick={() => { setEditor({ kind: "lorebook" }); setError(""); setMessage(""); }}>新建世界书</button>}</div>
    {editor && <ContentEditor key={editor.item?.import_id ?? editor.kind} client={client} worldId={worldId} kind={editor.kind} editing={editor.item} onCancel={() => setEditor(null)} onSaved={saved => { if (!active.current) return; onSaved?.(); setAccepted(items => [...items.filter(item => item.import_id !== saved.replaces_import_id && item.import_id !== saved.import_id), saved]); setEditor(null); setMessage(saved.kind === "character" ? "角色卡已保存，可在通讯录中打开会话。" : "世界书已保存，下方显示实际保存的可见范围；新增或修改条目请重新确认公开。"); }} />}
    <details className="file-import-options" open={onlyKind === "lorebook" ? true : undefined}><summary>{onlyKind === "lorebook" ? "导入世界书（JSON）" : "从文件导入"}</summary>
    {(kind === "lorebook" || visibleItems.some(item => item.kind === "lorebook")) && <p className="inline-hint">世界书条目默认隐藏。确认导入后，可逐条设为公共背景，供当前世界角色聊天和已开启的自动活动规划参考；暗线请保持隐藏。素材不会因此变成世界事实，也不会创建新地点。</p>}
    {replacement && <p className="inline-hint">正在更新：{replacement.characters[0]?.name ?? replacement.lorebooks[0]?.name} <button type="button" className="text-action" disabled={busy || !!preview} onClick={() => setReplacement(null)}>取消更新</button></p>}
    {!onlyKind && <label className="field"><span>内容类型</span><select value={kind} disabled={busy || !!preview || !!replacement || !!editor} onChange={event => setKind(event.target.value as typeof kind)}><option value="character">角色卡（PNG / JSON）</option><option value="lorebook">世界书（JSON）</option></select></label>}
    <label className="field import-file"><span>选择文件</span><input type="file" disabled={loading || loadFailed || busy || !!changingEntry || !!editor} accept={kind === "character" ? ".png,.json" : ".json"} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file); }} /></label>
    </details>{loading && <p role="status">正在读取已保存的内容…</p>}{busy && <p role="status">正在处理…</p>}{error && <p role="alert" className="app-alert">{error}</p>}{loadFailed && <button type="button" className="secondary-button" disabled={loading || busy || !!editor || !!preview} onClick={() => { setError(""); setReload(value => value + 1); }}>重新读取已保存内容</button>}{message && <p ref={savedNotice} tabIndex={-1} role="status" className="app-notice editor-feedback">{message}</p>}
    {preview && <div className="import-preview"><h3>导入预览</h3>{preview.kind === "character" && !replacement && <InitialLocationChoice client={client} worldId={worldId} value={initialLocation} onChange={setInitialLocation} disabled={busy} />}<ContentDetails item={preview} />
      {!!preview.warnings?.length && <div className="compatibility-notice"><p>部分来源内容无法完整映射，原始数据仍会保留。确认前请检查以下提示。</p><ul>{preview.warnings.map((warning, index) => <li key={index}>{warning.code === "lore_activation_metadata_preserved_inert" ? "导入不会执行触发设定；聊天支持范围见各条目说明。" : warning.code.includes("blank_tags") ? "空白标签已从角色标签中省略。" : warning.code.includes("empty_content") ? "空白条目已从世界书中省略。" : warning.code.includes("secondary_keys") ? "存在含义不明确的次级关键词，未作猜测转换。" : "存在兼容性差异，请核对预览内容。"}</li>)}</ul></div>}
      <div className="profile-actions"><button className="primary-button" type="button" disabled={busy || (preview.kind === "character" && !replacement && !initialLocation)} onClick={() => void commit()}>{replacement ? "确认更新当前世界" : "确认加入当前世界"}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => { pendingId.current = null; void client.discardWorldContent(worldId, preview.import_id).catch(() => undefined); setPreview(null); }}>取消</button></div>
    </div>}
    {visibleItems.length > 0 && <div className="accepted-content"><h3>当前世界已保存</h3><button type="button" className="text-action" disabled={commonDisabled || !!changingEntry} onClick={refreshAccepted}>刷新已保存内容与范围</button>{onlyKind === "lorebook" && <p className="inline-hint">公开范围选择后立即保存。通过界面编辑世界书时，完全未变且有原条目对应的内容保留原范围；新增、修改正文或触发条件、从文件替换的条目需要重新确认公开。编辑或预览期间，请先完成内容保存，再设置范围。</p>}{visibleItems.map(item => <div key={item.import_id} className="accepted-item"><details><summary>{item.characters[0]?.name ?? item.lorebooks[0]?.name ?? "导入内容"} · {item.kind === "character" ? "角色卡" : "世界书"}</summary><ContentDetails item={item} onCommonChange={item.kind === "lorebook" ? (entryId, common) => void setCommon(item.import_id, entryId, common) : undefined} changingEntry={changingEntry} commonDisabled={commonDisabled} exposureFeedback={exposureFeedback} onCommonRefresh={refreshAccepted} /></details><button type="button" className="text-action" disabled={loading || loadFailed || busy || !!changingEntry || !!preview || !!editor} onClick={() => { setEditor({ kind: item.kind, item }); setError(""); setMessage(""); }}>编辑</button><button type="button" className="text-action" disabled={loading || loadFailed || busy || !!changingEntry || !!preview || !!editor} onClick={() => { setReplacement(item); setKind(item.kind); setMessage(""); }}>从文件更新</button><ContentExportButton client={client} worldId={worldId} item={item} disabled={commonDisabled || !!changingEntry} />{item.kind === "character" && <button type="button" className="text-action destructive-action" disabled={commonDisabled || !!changingEntry} onClick={() => void removeCard(item)}>删除角色卡</button>}</div>)}</div>}
  </section>;
}

export function WorldContacts({ client, worldId, onSettings, onIdentity, onOpenChat, canOpenChat, openingChat, refreshKey = 0, visible = true, onLocationDirty = ignoreDirty, onCharacterLocationDirty = ignoreDirty, onRemoved, removalDisabled = false, identityKey = null }: {
  client: CoreClient;
  worldId: string;
  onSettings: () => void;
  onIdentity: () => void;
  onOpenChat: (importId: string) => Promise<void>;
  canOpenChat: boolean;
  openingChat: boolean;
  refreshKey?: number;
  visible?: boolean;
  onLocationDirty?: (dirty: boolean) => void;
  onCharacterLocationDirty?: (dirty: boolean) => void;
  identityKey?: string | null;
  onRemoved?: () => void;
  removalDisabled?: boolean;
}) {
  const [items, setItems] = useState<WorldContentItem[]>([]);
  const [selected, setSelected] = useState<WorldContentItem | null>(null);
  const [social, setSocial] = useState<SocialSnapshot | null>(null);
  const [mode, setMode] = useState<"profile" | "factions" | "graph" | "locations">("profile");
  const [locationOpen, setLocationOpen] = useState(false), [positionDirty, setPositionDirty] = useState(false);
  const locationEditor = useRef<HTMLDetailsElement>(null);
  const places = useLocationDirectory(client, worldId, visible);
  const [catalogDirty, setCatalogDirty] = useState(false), [bulkDirty, setBulkDirty] = useState(false);
  useEffect(() => { onLocationDirty(catalogDirty || bulkDirty); return () => onLocationDirty(false); }, [catalogDirty, bulkDirty, onLocationDirty]);
  const reportPositionDirty = useCallback((dirty: boolean) => { setPositionDirty(dirty); onCharacterLocationDirty(dirty); }, [onCharacterLocationDirty]);
  const selectMode = (next: typeof mode) => { if (next !== mode && positionDirty && !window.confirm("角色位置规则尚未保存或结果未确认，确定离开并放弃本次编辑吗？")) return; setMode(next); };
  const editLocations = () => { setLocationOpen(true); window.requestAnimationFrame(() => locationEditor.current?.scrollIntoView({ block: "start" })); };
  const [search, setSearch] = useState("");
  const [peoplePage, setPeoplePage] = useState(0);
  useEffect(() => setPeoplePage(0), [search, worldId]);
  const [graphRoot, setGraphRoot] = useState<string | null>(null);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [socialBusy, setSocialBusy] = useState(false);
  const [socialError, setSocialError] = useState("");
  const [removing, setRemoving] = useState(false);
  const removalBusy = useRef(false);
  useDesktopUpdateBlock(removing ? "角色卡正在删除，请等结果确认。" : null);
  const removeSelected = async () => {
    if (!selected || socialBusy || loading || removalDisabled || removalBusy.current) return;
    if (positionDirty && !window.confirm("位置规则尚未保存。删除角色卡将放弃这份编辑，确定继续吗？")) return;
    if (!confirmCardRemoval(selected)) return;
    removalBusy.current = true; setRemoving(true); setSocialError("");
    try {
      await client.removeCharacterCard(worldId, selected.import_id);
      setItems(values => values.filter(item => item.import_id !== selected.import_id));
      setSelected(null); setGraphRoot(null); setReload(value => value + 1);
      onRemoved?.(); void places.refresh();
    } catch (failure) { setSocialError(cardRemovalError(failure)); }
    finally { removalBusy.current = false; setRemoving(false); }
  };
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!visible) return;
    let active = true;
    setLoading(true); setFailed(false);
    void Promise.all([client.worldContent(worldId), client.socialSnapshot(worldId)]).then(([result, people]) => { if (active) { setItems(result); setSocial(people); setSelected(current => current ? result.find(item => item.import_id === current.import_id) ?? null : null); } }).catch(() => { if (active) setFailed(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [client, worldId, refreshKey, reload, visible]);
  const characters = items.filter(item => item.characters.length > 0);
  const matchingCharacters = characters.filter(item => item.characters[0].name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const current = social?.characters.find(person => person.current_import_id === selected?.import_id);
  const [mapAvatarDigests, setMapAvatarDigests] = useState("");
  const visibleImports = new Set(matchingCharacters.slice(Math.min(peoplePage, Math.max(0, Math.ceil(matchingCharacters.length / 50) - 1)) * 50, (Math.min(peoplePage, Math.max(0, Math.ceil(matchingCharacters.length / 50) - 1)) + 1) * 50).map(item => item.import_id));
  const avatarDigests = [...new Set([...(social?.characters.filter(person => mode === "graph" || visibleImports.has(person.current_import_id) || person.root_import_id === current?.root_import_id).map(person => person.avatar_digest).filter((digest): digest is string => !!digest) ?? []), ...(mode === "locations" && mapAvatarDigests ? mapAvatarDigests.split(",") : [])])].sort().join(",");
  useEffect(() => {
    if (!visible) return;
    let active = true;
    const created: string[] = [];
    void Promise.all((avatarDigests ? avatarDigests.split(",") : []).map(async digest => {
      try { const blob = await client.coverImage(worldId, digest); return [digest, URL.createObjectURL(blob)] as const; }
      catch { return null; }
    })).then(found => { for (const entry of found) if (entry) created.push(entry[1]); if (active) setUrls(Object.fromEntries(found.filter((entry): entry is readonly [string, string] => !!entry))); else created.forEach(URL.revokeObjectURL); });
    return () => { active = false; created.forEach(URL.revokeObjectURL); };
  }, [client, avatarDigests, visible, worldId]);
  const selectedRoot = current?.root_import_id ?? null;
  const selectedFactions = social?.memberships.filter(item => item.root_import_id === selectedRoot).map(item => social.factions.find(faction => faction.faction_id === item.faction_id)?.name).filter((name): name is string => !!name) ?? [];
  const change = async (operation: () => Promise<unknown>) => {
    if (socialBusy || removalBusy.current) return false;
    setSocialBusy(true); setSocialError("");
    try { await operation(); setSocial(await client.socialSnapshot(worldId)); return true; }
    catch (failure) { setSocialError(failure instanceof CoreRequestError ? ({ faction_name_taken: "同层已有这个阵营名称。", faction_cycle: "不能把阵营移动到自己的子阵营。", faction_not_empty: "先移除成员和子阵营，再删除此阵营。", faction_character_not_found: "角色卡已更新，请刷新通讯录。", cover_image_size_limit: "头像不能超过 10 MB。", cover_image_format: "请选择 JPG、PNG 或 WebP 静态图片。", cover_image_invalid: "无法读取这张图片，请换一张图片。", cover_image_dimensions_limit: "图片尺寸超出允许范围，请缩小后上传。" } as Record<string, string>)[failure.code ?? ""] ?? "保存未完成，请检查核心连接后刷新。" : "保存未完成，请检查核心连接后刷新。"); return false; }
    finally { setSocialBusy(false); }
  };
  const uploadAvatar = async (file?: File) => {
    if (!file || !selectedRoot) return;
    if (file.size > 10 * 1024 * 1024) { setSocialError("头像不能超过 10 MB。"); return; }
    await change(async () => { const image = await client.uploadCoverImage(worldId, file); await client.setCharacterAvatar(worldId, selectedRoot, image.digest); });
  };
  return <><details ref={locationEditor} className="contacts-management location-management" open={locationOpen} onToggle={event => setLocationOpen(event.currentTarget.open)}><summary><strong>添加／编辑地点</strong><span>地点层级、隐藏分支与角色开放范围</span></summary><LocationManager client={client} worldId={worldId} locations={places.locations} directory={places.directory} refresh={places.refresh} onDirtyChange={setCatalogDirty} /></details><UnplacedCharactersEditor client={client} worldId={worldId} directory={places.directory} social={social} locations={places.locations} refresh={places.refresh} onDirtyChange={setBulkDirty} /><div className={`chat-workspace contacts-workspace ${selected && mode === "profile" ? "thread-open" : ""}`}><aside className="conversation-list" aria-label="当前世界角色"><div className="directory-heading"><strong>世界中的人</strong><small>{loading ? "读取中" : failed ? "读取未完成" : `${characters.length} 位角色`}</small></div>
    <DirectorySearch label="搜索角色名称" value={search} onChange={setSearch} />
    {loading ? <p className="thread-hint">正在读取角色…</p> : failed ? <><p className="app-alert" role="alert">无法读取通讯录或阵营。</p><button type="button" onClick={() => setReload(value => value + 1)}>重试读取</button></> : characters.length === 0 ? <div className="empty-state"><h2>当前世界还没有角色</h2><p>在这里新建、联网生成或导入角色卡，确认后加入当前世界。</p><button className="text-action" onClick={onSettings}>添加角色卡</button></div> : matchingCharacters.slice(Math.min(peoplePage, Math.max(0, Math.ceil(matchingCharacters.length / 50) - 1)) * 50, (Math.min(peoplePage, Math.max(0, Math.ceil(matchingCharacters.length / 50) - 1)) + 1) * 50).map(item => { const person = social?.characters.find(value => value.current_import_id === item.import_id); return <button key={item.import_id} className={`conversation-row ${selected?.import_id === item.import_id ? "selected" : ""}`} aria-pressed={selected?.import_id === item.import_id} onClick={() => { if (positionDirty && selected?.import_id !== item.import_id && !window.confirm("位置规则尚未保存，确定切换角色并放弃本次编辑吗？")) return; setSelected(item); setGraphRoot(person?.root_import_id ?? null); }}><ContactAvatar name={item.characters[0].name} url={urls[person?.avatar_digest ?? ""]} /><span className="row-copy"><strong>{item.characters[0].name}</strong><small>查看角色资料与阵营</small></span></button>; })}
    {matchingCharacters.length > 50 && <div className="profile-actions"><button type="button" disabled={peoplePage === 0} onClick={() => setPeoplePage(old => Math.max(0, old - 1))}>上一页</button><span>{Math.min(peoplePage + 1, Math.ceil(matchingCharacters.length / 50))} / {Math.ceil(matchingCharacters.length / 50)}</span><button type="button" disabled={peoplePage >= Math.ceil(matchingCharacters.length / 50) - 1} onClick={() => setPeoplePage(old => old + 1)}>下一页</button></div>}
    {!loading && !failed && characters.length > 0 && matchingCharacters.length === 0 && <p className="thread-hint" role="status">没有找到这个名字，试试其他关键词。</p>}
  </aside><div className="conversation-detail"><div className="contacts-view-switch"><button type="button" className="secondary-button" aria-pressed={mode === "profile"} onClick={() => selectMode("profile")}>角色资料</button><button type="button" className="secondary-button" aria-pressed={mode === "factions"} onClick={() => selectMode("factions")}>编辑阵营</button><button type="button" className="secondary-button" aria-pressed={mode === "graph"} onClick={() => selectMode("graph")}>人物关系网</button><button type="button" className="secondary-button" aria-pressed={mode === "locations"} onClick={() => selectMode("locations")}>地点</button><button type="button" className="text-action" disabled={socialBusy || loading} onClick={() => setReload(value => value + 1)}>刷新</button></div>
    {places.error && <div className="app-alert" role="alert">{places.error}<button className="text-action" onClick={() => void places.refresh()}>刷新地点</button></div>}
    {socialError && <p className="app-alert" role="alert">{socialError}</p>}
    {mode === "locations" && social ? <LocationMap onAvatarDigests={setMapAvatarDigests} locations={places.locations} directory={places.directory} social={social} urls={urls} selected={graphRoot} onSelect={root => { setGraphRoot(root); setSelected(items.find(item => item.import_id === social.characters.find(person => person.root_import_id === root)?.current_import_id) ?? null); }} onChat={importId => void onOpenChat(importId)} openingChat={openingChat} onEdit={editLocations} /> : mode === "graph" && social ? <SocialGraph visible={visible} social={social} urls={urls} selected={graphRoot} onSelect={root => { setGraphRoot(root); setSelected(items.find(item => item.import_id === social.characters.find(person => person.root_import_id === root)?.current_import_id) ?? null); }} onChat={importId => void onOpenChat(importId)} canChat={canOpenChat} openingChat={openingChat} />
      : mode === "factions" && social ? <FactionManager key={worldId} social={social} selectedRoot={selectedRoot} busy={socialBusy} onSelect={root => { setSelected(items.find(item => item.import_id === social.characters.find(person => person.root_import_id === root)?.current_import_id) ?? null); }} onCreate={(name, parent) => change(() => client.createFaction(worldId, name, parent))} onEdit={(id, name, parent) => change(() => client.editFaction(worldId, id, name, parent))} onRemove={id => { if (window.confirm("确定删除这个空阵营吗？")) void change(() => client.removeFaction(worldId, id)); }} onMembership={(id, root, enabled, cut) => change(() => client.setFactionMember(worldId, id, root, enabled, cut))} />
      : selected ? <><div className="thread-heading"><button className="text-action" onClick={() => setSelected(null)}>返回通讯录</button><h2>角色档案</h2></div>
        <div className="contact-dossier"><header className="dossier-hero">
          <ContactAvatar name={selected.characters[0].name} url={urls[current?.avatar_digest ?? ""]} className="dossier-portrait" />
          <div className="dossier-title"><span className="dossier-caption">人物档案</span><h2>{selected.characters[0].name}</h2><div className="dossier-factions" aria-label="所属阵营">{selectedFactions.length ? selectedFactions.map((name, index) => <span key={`${index}:${name}`}>{name}</span>) : <span>尚未加入阵营</span>}</div></div>
          {canOpenChat ? <button type="button" className="primary-button" disabled={openingChat} onClick={() => void onOpenChat(selected.import_id)}>{openingChat ? "正在打开…" : "打开会话"}<WorkspaceIcon name="arrow" /></button> : <button type="button" className="text-action" onClick={onIdentity}>先进入世界，再打开会话</button>}
        </header>
        {current && <details className="dossier-avatar-options"><summary>编辑角色头像</summary><div className="contact-avatar-edit"><label>上传角色头像（JPG、PNG 或 WebP，最大 10 MB）<input type="file" accept="image/jpeg,image/png,image/webp" disabled={socialBusy} onChange={event => { void uploadAvatar(event.target.files?.[0]); event.target.value = ""; }} /></label>{current.avatar_digest && <button type="button" className="text-action" disabled={socialBusy} onClick={() => void change(() => client.setCharacterAvatar(worldId, current.root_import_id, null))}>移除头像</button>}</div></details>}
        {current && <CharacterLocationEditor key={`${identityKey}:${current.root_import_id}`} client={client} worldId={worldId} person={current} activity={places.directory?.items.find(person => person.root_import_id === current.root_import_id)} directory={places.directory} locations={places.locations} refresh={places.refresh} onDirtyChange={reportPositionDirty} />}
        <p className="inline-hint">同阵营直接成员默认相互认识；相遇仍可记录新见闻。</p><ContentDetails item={selected} hideCharacterTitle /><div className="profile-actions"><button type="button" className="secondary-button destructive-action" disabled={socialBusy || removing || loading || removalDisabled} onClick={() => void removeSelected()}>{removing ? "正在删除…" : "删除角色卡"}</button><small>历史会话和世界事件保留。</small></div></div></> : <CelestialEmpty title="在这里，认识彼此">选择一个名字，打开人物档案。<br />他们的资料、所属阵营和相识关系，都在这里。</CelestialEmpty>}
  </div></div></>;
}
