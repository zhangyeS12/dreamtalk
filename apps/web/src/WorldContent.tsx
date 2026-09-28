import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type WorldContentItem } from "@dreamtalk/api-client";

function originalCardGreeting(authored: Record<string, unknown>): string | null {
  const card = authored.character_card;
  if (!card || typeof card !== "object" || Array.isArray(card)) return null;
  const greeting = (card as Record<string, unknown>).first_mes;
  return typeof greeting === "string" && greeting.trim() ? greeting : null;
}

function ContentDetails({ item, onCommonChange, changingEntry }: {
  item: WorldContentItem;
  onCommonChange?: (entryId: string, common: boolean) => void;
  changingEntry?: string | null;
}) {
  return <div className="content-details">
    {item.characters.map(character => {
      const greeting = originalCardGreeting(character.authored_instructions);
      return <section key={character.id}><h2>{character.name}</h2>{([
      ["角色描述", character.description], ["性格", character.personality],
      ["背景", character.background], ["情境", character.scenario],
      ["说话方式", character.speech_guidance], ["创作者备注", character.creator_notes],
      ["标签", character.tags.join("、")], ["对话示例", character.example_dialogue.join("\n")],
    ] as const).filter(([, value]) => value).map(([label, value]) => <div key={label}><h3>{label}</h3><p>{value}</p></div>)}
      {greeting && <div><h3>角色卡开场白（原文）</h3><p>{greeting}</p><small>回复可参考其语气；不会自动作为消息发送。</small></div>}
    </section>;
    })}
    {item.characters.some(character => Object.keys(character.authored_instructions).length > 0) && <details><summary>角色卡附加设定</summary>{item.characters.map(character => <pre key={character.id}>{JSON.stringify(character.authored_instructions, null, 2)}</pre>)}</details>}
    {item.lorebooks.map(book => <section key={book.id}><h2>{book.name}</h2><p>{book.description}</p></section>)}
    {item.entries.length > 0 && <details><summary>世界书条目（{item.entries.length}）</summary><p className="inline-hint">设为公共背景后，条目按来源的常驻或关键词条件参与聊天；未触发的条目不会占用聊天背景。</p>{item.entries.map((entry, index) => <div key={entry.id}><h3>{entry.title || `条目 ${index + 1}`}</h3>{entry.keywords.length > 0 && <p>关键词：{entry.keywords.join("、")}</p>}<p>{entry.content}</p>{!!entry.secondary_keywords?.length && <p>次级关键词：{entry.secondary_keywords.join("、")}</p>}{entry.activation_summary && <p className="inline-hint">{entry.activation_summary}</p>}{!entry.enabled && <small>来源中已禁用；不会进入角色聊天。</small>}{onCommonChange && <label className="field"><span>角色可见范围</span><select value={entry.common ? "common" : "hidden"} disabled={!entry.enabled || changingEntry === entry.id} onChange={event => onCommonChange(entry.id, event.target.value === "common")}><option value="hidden">隐藏（默认）</option><option value="common">公共背景（所有角色可见）</option></select></label>}</div>)}</details>}
  </div>;
}

export function WorldImports({ client, worldId }: { client: CoreClient; worldId: string }) {
  const active = useRef(true);
  const pendingId = useRef<string | null>(null);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      if (pendingId.current) void client.discardWorldContent(worldId, pendingId.current).catch(() => undefined);
    };
  }, [client, worldId]);
  const [kind, setKind] = useState<"character" | "lorebook">("character");
  const [replacement, setReplacement] = useState<WorldContentItem | null>(null);
  const [preview, setPreview] = useState<WorldContentItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [accepted, setAccepted] = useState<WorldContentItem[]>([]);
  const [changingEntry, setChangingEntry] = useState<string | null>(null);
  useEffect(() => {
    let mounted = true;
    void client.worldContent(worldId).then(items => { if (mounted) setAccepted(items); }).catch(() => { if (mounted) setError("无法读取当前世界的已导入内容。"); });
    return () => { mounted = false; };
  }, [client, worldId]);
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
      ? "该内容已更新，请重新打开设置并选择最新版本。"
      : "无法读取文件。请选择有效的角色卡或世界书；文件内容尚未保存。"); }
    finally { setBusy(false); }
  };
  const commit = async () => {
    if (!preview) return;
    setBusy(true); setError("");
    try {
      const saved = await client.commitWorldContent(worldId, preview);
      setAccepted(items => items.some(item => item.import_id === saved.import_id)
        ? items : [...items.filter(item => item.import_id !== saved.replaces_import_id), saved]);
      pendingId.current = null; setPreview(null); setReplacement(null);
      setMessage(saved.replaces_import_id ? "当前世界的内容已更新。" : preview.kind === "character" ? "已加入当前世界，可在通讯录查看角色。" : "世界书已加入当前世界。");
    } catch (failure) {
      setError(failure instanceof CoreRequestError && failure.status === 422
        ? "预览已过期，请重新选择文件。" : failure instanceof CoreRequestError && failure.status === 409
          ? "该内容已有更新，当前预览无法覆盖。请重新选择最新版本。"
          : "未能确认保存结果。可以再次确认，同一次导入不会重复保存。");
    } finally { setBusy(false); }
  };
  const setCommon = async (importId: string, entryId: string, common: boolean) => {
    setChangingEntry(entryId); setError(""); setMessage("");
    try {
      await client.setCommonLore(worldId, importId, entryId, common);
      setAccepted(items => items.map(item => item.import_id !== importId ? item : {
        ...item, entries: item.entries.map(entry => entry.id === entryId ? { ...entry, common } : entry),
      }));
      setMessage(common ? "已设为公共背景。" : "已设为隐藏内容。");
    } catch { setError("无法更新公共背景范围，请重新进入设置后重试。"); }
    finally { setChangingEntry(null); }
  };
  return <section className="settings-section import-section"><div className="section-heading"><h2>导入内容</h2><p>预览确认后加入当前世界，其他世界的版本保持独立。</p></div>
    {(kind === "lorebook" || accepted.some(item => item.kind === "lorebook")) && <p className="inline-hint">世界书条目默认隐藏。确认导入后，可逐条设为公共背景，供当前世界所有角色聊天时参考；暗线请保持隐藏。聊天内容不会因此变成世界事实。</p>}
    {replacement && <p className="inline-hint">正在更新：{replacement.characters[0]?.name ?? replacement.lorebooks[0]?.name} <button type="button" className="text-action" disabled={busy || !!preview} onClick={() => setReplacement(null)}>取消更新</button></p>}
    <label className="field"><span>内容类型</span><select value={kind} disabled={busy || !!preview || !!replacement} onChange={event => setKind(event.target.value as typeof kind)}><option value="character">角色卡（PNG / JSON）</option><option value="lorebook">世界书（JSON）</option></select></label>
    <label className="field import-file"><span>选择文件</span><input type="file" disabled={busy} accept={kind === "character" ? ".png,.json" : ".json"} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file); }} /></label>
    {busy && <p role="status">正在处理…</p>}{error && <p role="alert" className="app-alert">{error}</p>}{message && <p role="status" className="app-notice">{message}</p>}
    {preview && <div className="import-preview"><h3>导入预览</h3><ContentDetails item={preview} />
      {!!preview.warnings?.length && <div className="compatibility-notice"><p>部分来源内容无法完整映射，原始数据仍会保留。确认前请检查以下提示。</p><ul>{preview.warnings.map((warning, index) => <li key={index}>{warning.code === "lore_activation_metadata_preserved_inert" ? "导入不会执行触发设定；聊天支持范围见各条目说明。" : warning.code.includes("blank_tags") ? "空白标签已从角色标签中省略。" : warning.code.includes("empty_content") ? "空白条目已从世界书中省略。" : warning.code.includes("secondary_keys") ? "存在含义不明确的次级关键词，未作猜测转换。" : "存在兼容性差异，请核对预览内容。"}</li>)}</ul></div>}
      <div className="profile-actions"><button className="primary-button" type="button" disabled={busy} onClick={() => void commit()}>{replacement ? "确认更新当前世界" : "确认加入当前世界"}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => { pendingId.current = null; void client.discardWorldContent(worldId, preview.import_id).catch(() => undefined); setPreview(null); }}>取消</button></div>
    </div>}
    {accepted.length > 0 && <div className="accepted-content"><h3>当前世界已导入</h3>{accepted.map(item => <div key={item.import_id} className="accepted-item"><details><summary>{item.characters[0]?.name ?? item.lorebooks[0]?.name ?? "导入内容"} · {item.kind === "character" ? "角色卡" : "世界书"}</summary><ContentDetails item={item} onCommonChange={item.kind === "lorebook" ? (entryId, common) => void setCommon(item.import_id, entryId, common) : undefined} changingEntry={changingEntry} /></details><button type="button" className="text-action" disabled={busy || !!preview} onClick={() => { setReplacement(item); setKind(item.kind); setMessage(""); }}>更新</button></div>)}</div>}
  </section>;
}

export function WorldContacts({ client, worldId, onSettings, onIdentity, onOpenChat, canOpenChat, openingChat }: {
  client: CoreClient;
  worldId: string;
  onSettings: () => void;
  onIdentity: () => void;
  onOpenChat: (importId: string) => Promise<void>;
  canOpenChat: boolean;
  openingChat: boolean;
}) {
  const [items, setItems] = useState<WorldContentItem[]>([]);
  const [selected, setSelected] = useState<WorldContentItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    void client.worldContent(worldId).then(result => { if (active) setItems(result); }).catch(() => { if (active) setFailed(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [client, worldId]);
  const characters = items.filter(item => item.characters.length > 0);
  return <div className={`chat-workspace contacts-workspace ${selected ? "thread-open" : ""}`}><aside className="conversation-list" aria-label="当前世界角色">
    {loading ? <p className="thread-hint">正在读取角色…</p> : failed ? <p className="app-alert" role="alert">无法读取通讯录，请重新进入此页面。</p> : characters.length === 0 ? <div className="empty-state"><h2>当前世界还没有角色</h2><p>在设置中导入角色卡，确认后显示在这里。</p><button className="text-action" onClick={onSettings}>前往设置</button></div> : characters.map(item => <button key={item.import_id} className={`conversation-row ${selected?.import_id === item.import_id ? "selected" : ""}`} onClick={() => setSelected(item)}><span className="avatar event-avatar" aria-hidden="true">{Array.from(item.characters[0].name)[0]}</span><span className="row-copy"><strong>{item.characters[0].name}</strong><small>查看角色资料</small></span></button>)}
  </aside><div className="conversation-detail">{selected ? <><div className="thread-heading"><button className="text-action" onClick={() => setSelected(null)}>返回通讯录</button><h2>角色资料</h2></div><div className="contact-chat-action">{canOpenChat ? <button type="button" className="primary-button" disabled={openingChat} onClick={() => void onOpenChat(selected.import_id)}>{openingChat ? "正在打开…" : "打开会话"}</button> : <button type="button" className="text-action" onClick={onIdentity}>先进入世界，再打开会话</button>}</div><ContentDetails item={selected} /></> : <div className="conversation-placeholder"><h2>当前世界的角色</h2><p>选择左侧角色，查看已确认的资料。</p></div>}</div></div>;
}
