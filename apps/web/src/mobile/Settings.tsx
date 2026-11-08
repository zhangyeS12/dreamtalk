import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, type WorldSettings, type SelectedPlayerState, type SocialSnapshot, type KnownWorldEvent } from "@dreamtalk/api-client";
import { ModelSetup } from "../ModelSetup";
import { SpeechSettings } from "../SpeechSettings";
import { ChatMediaSettingsPanel, StickerLibraries } from "../ChatMedia";
import { SaveSlotsPanel } from "../SaveSlots";
import { WorldActivities } from "../WorldActivities";
import { WorldNewsSettings } from "../WorldNewsSettings";
import { ProactiveContactSettings } from "../ProactiveContactSettings";
import { OfflineContactSettings } from "../OfflineContactSettings";
import { useOfflineContact } from "../useOfflineContact";
import { ChatVisualSettings } from "../ChatVisualSettings";
import type { ChatVisualState } from "../useChatVisuals";
import { WorldStyleEditor } from "../WorldStyleEditor";
import { BackgroundSettings } from "./BackgroundSettings";
import { mobileInvoke } from "./native";
import { hostCall, feedback } from "./host";
import { LocationManager, CharacterLocationEditor, useLocationDirectory } from "../LocationWorkspace";

export const mobileSettingsPages = [
  ["model", "模型与聊天"], ["visuals", "聊天视觉"], ["media", "表情与图片"], ["speech", "角色配音"],
  ["background", "后台运行与通知"], ["backups", "数据与备份"], ["time", "世界时间"], ["activities", "角色活动"],
  ["offline", "主动联系"], ["news", "世界动态"], ["about", "关于与诊断"],
] as const;
type Page = typeof mobileSettingsPages[number][0];
const appPages: Page[] = ["model", "background", "backups", "about"];
export function MobileSettings({ client, world, player, budget, onBudget, onConfigured, onDirtyChange, visuals, onNavigate, onWorldChange }: {
  client: CoreClient; world?: WorldSettings; player?: string | null; budget: number; onBudget: (value: number) => void;
  onConfigured: () => Promise<void>; onDirtyChange: (value: boolean) => void; visuals?: ChatVisualState;
  onNavigate?: (destination: string) => void; onWorldChange?: (world: WorldSettings) => void;
}) {
  const [page, setPage] = useState<Page | null>(null), [visited, setVisited] = useState<Page[]>([]);
  const dirty = useRef<Record<string, boolean>>({}), callbacks = useRef<Record<string, (value: boolean) => void>>({});
  const dirtyHandler = useRef(onDirtyChange); dirtyHandler.current = onDirtyChange;
  const report = (key: string) => callbacks.current[key] ??= value => { dirty.current[key] = value; dirtyHandler.current(Object.values(dirty.current).some(Boolean)); };
  const open = (next: Page) => { setVisited(current => current.includes(next) ? current : [...current, next]); setPage(next); };
  const navigate = (destination: string) => { if (["model", "time", "about"].includes(destination)) open(destination as Page); else if (destination === "locations") open("activities"); else if (destination === "events") open("news"); else onNavigate?.(destination); };
  useEffect(() => () => dirtyHandler.current(false), []);
  const pages = mobileSettingsPages.filter(([id]) => world || appPages.includes(id));
  return <div className="mobile-settings">
    {page ? <div className="mobile-section-heading"><button onClick={() => setPage(null)}>‹ 设置目录</button><h2>{pages.find(([id]) => id === page)?.[1]}</h2></div> : <><h2>设置</h2><p className="mobile-muted">{world ? `世界设置仅作用于“${world.name}”。` : "先选择世界可编辑其独立设置。"}应用设置由所有世界共用。</p><ul className="mobile-list">{pages.map(([id, title]) => <li key={id}><button onClick={() => open(id)}><span><strong>{title}</strong><small>{appPages.includes(id) ? id === "model" && world ? "当前世界与全局配置" : "应用设置" : "当前世界"}{dirty.current[id] ? " · 未保存" : ""}</small></span><span aria-hidden="true">›</span></button></li>)}</ul></>}
    {visited.map(id => <div key={id} hidden={page !== id}>
      {id === "model" && <><ModelSetup client={client} worldId={world?.world_id} nativeInvoke={mobileInvoke} onConfigured={() => void onConfigured()} onDirtyChange={report("model")} turnTokenCeiling={budget} onApplyTokenCeiling={onBudget} /><TokenBudget value={budget} onSave={onBudget} onDirtyChange={report("budget")} />{world && <WorldStyleEditor client={client} worldId={world.world_id} onDirtyChange={report("style")} />}{world && <details><summary>全局默认 API 与调度器</summary><ModelSetup client={client} nativeInvoke={mobileInvoke} onConfigured={() => void onConfigured()} onDirtyChange={report("default-model")} /></details>}</>}
      {id === "background" && <BackgroundSettings />}
      {id === "backups" && <SaveSlotsPanel mobile nativeInvoke={mobileInvoke} />}
      {id === "about" && <About client={client} world={world} />}
      {world && <>
        {id === "visuals" && visuals && <><p className="inline-hint">图片按需加载，沿用简版布局；不启用毛玻璃和装饰动画。</p><ChatVisualSettings client={client} worldId={world.world_id} state={visuals} /></>}
        {id === "media" && <><ChatMediaSettingsPanel client={client} worldId={world.world_id} nativeInvoke={mobileInvoke} apiOnly onDirtyChange={report("media")} /><MediaLibraries client={client} world={world} onDirtyChange={report("stickers")} /></>}
        {id === "speech" && <SpeechSettings client={client} worldId={world.world_id} nativeInvoke={mobileInvoke} apiOnly onDirtyChange={report("speech")} />}
        {id === "time" && <WorldTime client={client} world={world} onWorldChange={onWorldChange} onDirtyChange={report("time")} />}
        {id === "activities" && (player ? <><WorldActivities client={client} worldId={world.world_id} visible={page === id} paused={world.clock_state === "paused"} onNavigate={navigate} /><MobileLocations client={client} world={world} visible={page === id} onDirtyChange={report("locations")} /></> : <p>先在“我”中初始化当前世界身份。</p>)}
        {id === "offline" && (player ? <ContactSettings client={client} world={world} player={player} onNavigate={navigate} /> : <p>先在“我”中初始化当前世界身份。</p>)}
        {id === "news" && (player ? <><WorldNewsSettings client={client} worldId={world.world_id} visible={page === id} paused={world.clock_state === "paused"} onNavigate={navigate} /><KnownEvents client={client} world={world} visible={page === id} /></> : <p>先在“我”中初始化当前世界身份。</p>)}
      </>}
    </div>)}
  </div>;
}
function TokenBudget({ value, onSave, onDirtyChange }: { value: number; onSave: (value: number) => void; onDirtyChange: (value: boolean) => void }) {
  const [draft, setDraft] = useState(String(value)), [notice, setNotice] = useState("");
  useEffect(() => setDraft(String(value)), [value]);
  useEffect(() => onDirtyChange(Number(draft) !== value), [draft, value, onDirtyChange]);
  return <form className="mobile-form" onSubmit={e => { e.preventDefault(); const next = Number(draft); if (Number.isSafeInteger(next) && next > 0) { onSave(next); setNotice("聊天额度已应用，不调用模型。"); } }}><h2>每轮聊天额度</h2><p>输入、输出、群聊选人和内部尝试共用此硬上限；后台规划及配音费用另计。</p><label>每轮 Token 上限<input type="number" min={1} max={Number.MAX_SAFE_INTEGER} required value={draft} onChange={e => setDraft(e.target.value)} /></label><button>应用聊天额度</button><p role="status">当前已应用 {value.toLocaleString("zh-CN")} Token。{notice}</p></form>;
}
function WorldTime({ client, world, onWorldChange, onDirtyChange }: { client: CoreClient; world: WorldSettings; onWorldChange?: (world: WorldSettings) => void; onDirtyChange: (value: boolean) => void }) {
  const [scale, setScale] = useState(world.time_scale), [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => onDirtyChange(scale !== world.time_scale), [scale, world.time_scale, onDirtyChange]);
  const act = async (operation: () => Promise<unknown>) => { setBusy(true); setError(""); try { await operation(); const next = (await client.listProductWorlds()).find(item => item.world_id === world.world_id); if (next) { onWorldChange?.(next); setScale(next.time_scale); } } catch { setError("世界时间尚未确认更新，请重新读取。"); } finally { setBusy(false); } };
  return <section className="settings-section"><h2>世界时间</h2><p>{world.world_time} · {world.clock_state === "paused" ? "已暂停" : "运行中"}</p><button disabled={busy} onClick={() => void act(() => world.clock_state === "paused" ? client.resumeProductWorld(world.world_id) : client.pauseProductWorld(world.world_id))}>{world.clock_state === "paused" ? "恢复世界" : "暂停世界"}</button><label className="field">时间倍率<input type="number" min="0.01" max="1000" step="0.01" value={scale} disabled={busy} onChange={e => setScale(e.target.value)} /></label><p>提高倍率也会缩短按世界时间计算的规划与联系间隔，可能增加 API 用量。忙碌状态不会暂停世界。</p><button disabled={busy || !Number.isFinite(Number(scale)) || Number(scale) < .01 || Number(scale) > 1000} onClick={() => void act(() => client.scaleProductWorld(world.world_id, scale))}>应用时间倍率</button><button disabled={busy} onClick={() => void act(async () => undefined)}>重新读取世界时间</button>{error && <p role="alert">{error}</p>}</section>;
}
function ContactSettings({ client, world, player, onNavigate }: { client: CoreClient; world: WorldSettings; player: string; onNavigate: (destination: string) => void }) {
  const offline = useOfflineContact(client, world.world_id, player);
  const [identity, setIdentity] = useState<SelectedPlayerState | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const read = useCallback(async () => { try { setIdentity(await client.selectedPlayer(world.world_id)); setError(""); } catch { setError("交流状态未能读取，请重试。"); } }, [client, world.world_id]);
  useEffect(() => { void read(); }, [read]);
  const change = async () => { if (busy || !identity || identity.player_id !== player || identity.presence_revision === null) return; setBusy(true); try { await client.setPlayerAvailability(world.world_id, identity.availability === "available" ? "busy" : "available", identity.presence_revision, crypto.randomUUID()); await read(); } catch { setError("交流状态尚未确认保存，请重新读取。"); } finally { setBusy(false); } };
  return <><section className="settings-section"><h2>交流状态</h2><p>{identity?.availability === "available" ? "当前可联系" : identity?.availability === "busy" ? "当前忙碌" : "正在读取…"}</p><button disabled={busy || !identity?.availability} onClick={() => void change()}>{identity?.availability === "busy" ? "设为可联系" : "设为忙碌"}</button><button disabled={busy} onClick={() => void read()}>重新读取交流状态</button><p>忙碌时跳过普通主动联系，世界继续运行。在线和离线联系共用等待回复限制。</p>{error && <p role="alert">{error}</p>}</section><ProactiveContactSettings client={client} worldId={world.world_id} playerId={player} /><OfflineContactSettings status={offline.status} busy={offline.busy} refreshing={offline.refreshing} error={offline.error} onRefresh={offline.refresh} onSave={offline.save} paused={world.clock_state === "paused"} availability={identity?.availability ?? null} onNavigate={onNavigate} /></>;
}
function MediaLibraries({ client, world, onDirtyChange }: { client: CoreClient; world: WorldSettings; onDirtyChange: (value: boolean) => void }) {
  const [people, setPeople] = useState<{ root_import_id: string; name: string }[]>([]);
  useEffect(() => { let active = true; void client.worldContent(world.world_id).then(items => { if (active) setPeople(items.filter(item => item.kind === "character").map(item => ({ root_import_id: item.import_id, name: item.characters[0]?.name ?? "角色" }))); }).catch(() => undefined); return () => { active = false; }; }, [client, world.world_id]);
  return <details><summary>公共、角色专属与我的表情库</summary><StickerLibraries client={client} worldId={world.world_id} people={people} onDirtyChange={onDirtyChange} /></details>;
}
function About({ client, world }: { client: CoreClient; world?: WorldSettings }) {
  const [info, setInfo] = useState<{ version: string; android: string } | null>(null), [health, setHealth] = useState("尚未读取"), [notice, setNotice] = useState("");
  const read = useCallback(async () => { try { const [app, core] = await Promise.all([hostCall<{ version: string; android: string }>("app_info"), client.health(undefined, world?.world_id)]); setInfo(app); setHealth(core.llm_status === "ready" ? "核心连接成功，模型配置已就绪" : `核心连接成功，模型状态：${core.llm_status}`); } catch { setHealth("连接状态尚未确认，请重试。"); } }, [client, world?.world_id]);
  useEffect(() => { void read(); }, [read]);
  return <section className="settings-section"><h2>dreamtalk 安卓版</h2><p>{info ? `版本 ${info.version} · Android ${info.android}` : "正在读取版本…"}</p><p role="status">{health}</p><p>刷新仅检查本机状态，不验证服务商密钥或余额，不调用模型。</p><div className="profile-actions"><button onClick={() => void read()}>刷新连接状态</button><button onClick={() => void hostCall("copy_diagnostics").then(() => setNotice("诊断已复制，不包含密钥或聊天正文。")).catch(e => setNotice(feedback(e)))}>复制诊断</button></div>{notice && <p role="status">{notice}</p>}</section>;
}

function MobileLocations({ client, world, visible, onDirtyChange }: { client: CoreClient; world: WorldSettings; visible: boolean; onDirtyChange: (value: boolean) => void }) {
  const [opened, setOpened] = useState(false), [visited, setVisited] = useState(false), [social, setSocial] = useState<SocialSnapshot | null>(null), [root, setRoot] = useState(""), [error, setError] = useState("");
  const places = useLocationDirectory(client, world.world_id, visible && opened);
  useEffect(() => { if (!visible || !opened) return; let active = true; void client.socialSnapshot(world.world_id).then(value => { if (active) setSocial(value); }).catch(() => { if (active) setError("角色目录未能读取，请重新打开地点设置。"); }); return () => { active = false; }; }, [client, world.world_id, visible, opened]);
  const dirty = useRef({ places: false, character: false });
  const reportPlaces = useCallback((value: boolean) => { dirty.current.places = value; onDirtyChange(value || dirty.current.character); }, [onDirtyChange]);
  const reportCharacter = useCallback((value: boolean) => { dirty.current.character = value; onDirtyChange(value || dirty.current.places); }, [onDirtyChange]);
  const person = social?.characters.find(item => item.root_import_id === root);
  return <details onToggle={event => { setOpened(event.currentTarget.open); if (event.currentTarget.open) setVisited(true); }}><summary>地点、初始位置与常驻倾向</summary><p>这是地点与角色位置的作者设置。移动图与关系图不在手机上加载。</p>{visited && <><LocationManager client={client} worldId={world.world_id} locations={places.locations} directory={places.directory} refresh={places.refresh} onDirtyChange={reportPlaces} /><label className="field">选择角色<select value={root} onChange={e => { if (dirty.current.character && !window.confirm("角色位置还有未保存的修改，确定切换吗？")) return; reportCharacter(false); setRoot(e.target.value); }}><option value="">选择角色</option>{social?.characters.map(item => <option key={item.root_import_id} value={item.root_import_id}>{item.name}</option>)}</select></label>{person && <CharacterLocationEditor key={root} client={client} worldId={world.world_id} person={person} activity={places.directory?.items.find(item => item.root_import_id === root)} directory={places.directory} locations={places.locations} refresh={places.refresh} onDirtyChange={reportCharacter} />}{(places.error || error) && <p role="alert">{places.error || error}</p>}</>}</details>;
}
function KnownEvents({ client, world, visible }: { client: CoreClient; world: WorldSettings; visible: boolean }) {
  const [items, setItems] = useState<KnownWorldEvent[] | null>(null), [error, setError] = useState("");
  useEffect(() => { if (!visible) return; let active = true; const abort = new AbortController(); void client.knownEvents(world.world_id, abort.signal).then(value => { if (active) { setItems(value); setError(""); } }).catch(() => { if (active) setError("已获知的事件暂未读取。"); }); return () => { active = false; abort.abort(); }; }, [client, world.world_id, visible]);
  return <section className="settings-section"><h2>我已获知的世界动态</h2><p>只显示当前玩家已知的事件。</p>{error && <p role="alert">{error}</p>}{items ? items.length ? <ul>{items.map(item => <li key={item.event_id}><strong>{item.title}</strong><p>{item.description}</p><small>{item.occurred_at}</small></li>)}</ul> : <p>还没有获知的世界动态。</p> : <p>正在读取…</p>}</section>;
}
