import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, type CoreConnection, type WorldSettings, type WorldContentItem, type ChatConversation, type GroupChatConversation } from "@dreamtalk/api-client";
import { ChatTranscript } from "../ChatTranscript";
import { GroupChatDetails, GroupChatSetup } from "../GroupChat";
import { SpeechProvider } from "../SpeechPlayback";
import { WorldImports, ContentDetails } from "../WorldContent";
import { ProfileEditor } from "../ProfileEditor";
import { MobileSettings } from "./Settings";
import { ExampleWorldPanel } from "../ExampleWorldPanel";
import { useChatVisuals } from "../useChatVisuals";
import { CharacterVoice } from "../CharacterVoice";
import { SaveSlotsPanel } from "../SaveSlots";
import { mobileInvoke } from "./native";
import { Brand } from "../Brand";
import { hostCall, feedback } from "./host";
type Tab = "chats" | "contacts" | "settings" | "me";
type Conversation = ChatConversation | GroupChatConversation;
const labels: Record<Tab, string> = { chats: "聊天", contacts: "通讯录", settings: "设置", me: "我" };
export function MobileApp() {
  const [client, setClient] = useState<CoreClient | null>(null), [error, setError] = useState(""), [attempt, setAttempt] = useState(0);
  const [world, setWorld] = useState<WorldSettings | null>(null);
  const [recovery, setRecovery] = useState(false);
  const rootDirty = useRef(false), currentWorld = useRef<string | null>(null);
  currentWorld.current = world?.world_id ?? null;
  const onRootDirty = useCallback((value: boolean) => { rootDirty.current = value; }, []);
  const [target, setTarget] = useState<{ world_id: string; conversation_id: string; player_id: string } | null>(null);
  useEffect(() => {
    if (!client) return;
    let active = true;
    const read = async () => {
      try {
        const value = await hostCall<typeof target>("notification_target");
        if (!value || !active) return;
        const [worlds, identity] = await Promise.all([client.listProductWorlds(), client.selectedPlayer(value.world_id)]);
        const selected = worlds.find(item => item.world_id === value.world_id);
        if (active && selected && identity.player_id === value.player_id) {
          if (rootDirty.current && currentWorld.current !== value.world_id && !window.confirm("有未保存的输入，是否切换到通知对应的世界？")) return;
          setTarget(value); setWorld(selected);
        }
      } catch { /* A stale/deleted target never changes the selected identity. */ }
    };
    void read(); window.addEventListener("focus", read); document.addEventListener("visibilitychange", read);
    return () => { active = false; window.removeEventListener("focus", read); document.removeEventListener("visibilitychange", read); };
  }, [client]);
  const reconnect = useCallback(async () => {
    const connection = await hostCall<CoreConnection>("connection"); setClient(new CoreClient(connection)); setError("");
  }, []);
  useEffect(() => { let active = true; hostCall<CoreConnection>("connection").then(value => { if (active) { setClient(new CoreClient(value)); setError(""); } }).catch(e => { if (active) setError(feedback(e)); }); return () => { active = false; }; }, [attempt]);
  if (!client) return <main className="mobile-start"><span className="mobile-wordmark"><Brand /></span><h1>{error ? "暂时未能打开" : "正在打开你的世界"}</h1><p>{error || "首次启动需要准备本机数据，请稍候。"}</p>{error && <button onClick={() => { setError(""); setAttempt(v => v + 1); }}>重新打开</button>}{error && <button onClick={() => void hostCall("copy_diagnostics").then(() => setError("诊断信息已复制，可发给工程端排查。")).catch(() => setError("诊断暂时无法复制，请保留当前页面。"))}>复制启动诊断</button>}{error && <button onClick={() => setRecovery(value => !value)}>查看存档与恢复</button>}{recovery && <SaveSlotsPanel recovery mobile nativeInvoke={mobileInvoke} />}</main>;
  return <div className="mobile-app dt-world">{world ? <Workspace key={world.world_id} client={client} world={world} onBack={() => setWorld(null)} reconnect={reconnect} onDirtyRoot={onRootDirty} onWorldChange={setWorld} target={target} onTargetUsed={() => setTarget(null)} /> : <WorldList client={client} onEnter={setWorld} reconnect={reconnect} onDirtyRoot={onRootDirty} />}</div>;
}
function WorldList({ client, onEnter, reconnect, onDirtyRoot }: { client: CoreClient; onEnter: (world: WorldSettings) => void; reconnect: () => Promise<void>; onDirtyRoot: (value: boolean) => void }) {
  const [worlds, setWorlds] = useState<WorldSettings[]>([]), [name, setName] = useState(""), [loading, setLoading] = useState(true);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [settings, setSettings] = useState(false), [reload, setReload] = useState(0);
  const creation = useRef<{ id: string; name: string } | null>(null);
  const [defaultBudget, setDefaultBudget] = useState(() => Number(localStorage.getItem("livingworld.turnTokenCeiling")) || 131072);
  const [example, setExample] = useState(false);
  const dirty = useRef(false);
  const setDirty = useCallback((value: boolean) => { dirty.current = value; onDirtyRoot(value); }, [onDirtyRoot]);
  useEffect(() => { const controller = new AbortController(); setLoading(true); client.listProductWorlds(controller.signal).then(setWorlds).catch(() => { if (!controller.signal.aborted) setError("世界列表没有读取成功，请重试。"); }).finally(() => { if (!controller.signal.aborted) setLoading(false); }); return () => controller.abort(); }, [client, reload]);
  const create = async (event: FormEvent) => {
    event.preventDefault(); if (busy || !name.trim()) return; setBusy(true); setError("");
    creation.current ??= { id: crypto.randomUUID(), name: name.trim() };
    try { await client.createWorld(creation.current.name, creation.current.id); creation.current = null; setName(""); setReload(v => v + 1); }
    catch { setError("创建结果尚未确认。重试会核对同一次创建，不会重复新建。"); } finally { setBusy(false); }
  };
  return <><header className="mobile-top"><div><span className="mobile-wordmark"><Brand /></span><h1>我的世界</h1></div><button aria-label={settings ? "返回世界列表" : "应用设置"} onClick={() => { if (!dirty.current || window.confirm("有未保存的设置，确定离开吗？")) { dirty.current = false; setSettings(v => !v); } }}>{settings ? "返回" : "设置"}</button></header>
    <main className="mobile-page">{settings ? <MobileSettings client={client} onConfigured={reconnect} budget={defaultBudget} onBudget={value => { setDefaultBudget(value); try { localStorage.setItem("livingworld.turnTokenCeiling", String(value)); } catch { /* Keep the applied session value. */ } }} onDirtyChange={setDirty} /> : <>
      <p className="mobile-muted">选择一个世界，继续你的对话。</p>
      <button disabled={busy} onClick={() => setExample(v => !v)}>体验校园示例</button>
      {example && <ExampleWorldPanel client={client} onBusy={setBusy} onClose={() => setExample(false)} onCreated={async id => { const all = await client.listProductWorlds(); setWorlds(all); const next = all.find(item => item.world_id === id); if (next) onEnter(next); }} />}
      {loading ? <p role="status">正在读取世界…</p> : worlds.length ? <ul className="mobile-list">{worlds.map(item => <li key={item.world_id}><button onClick={() => onEnter(item)}><span className="mobile-initial">{item.name.slice(0, 1)}</span><span><strong>{item.name}</strong><small>打开世界</small></span><span aria-hidden="true">›</span></button></li>)}</ul> : <div className="mobile-empty"><h2>从一个世界开始</h2><p>创建世界后，可以导入角色卡和世界书。</p></div>}
      <form className="mobile-form mobile-create" onSubmit={event => void create(event)}><label>新世界名称<input required maxLength={120} disabled={busy || !!creation.current} value={name} onChange={e => setName(e.target.value)} /></label><button disabled={busy} className="primary-button">{busy ? "正在创建…" : creation.current ? "核对并重试创建" : "创建世界"}</button></form>
    </>}{error && <p className="mobile-error" role="alert">{error}<button onClick={() => setReload(v => v + 1)}>重新读取</button></p>}</main></>;
}
function Workspace({ client, world, onBack, reconnect, onWorldChange, target, onTargetUsed, onDirtyRoot }: { onDirtyRoot: (value: boolean) => void; client: CoreClient; world: WorldSettings; onBack: () => void; reconnect: () => Promise<void>; onWorldChange: (world: WorldSettings) => void; target: { conversation_id: string; player_id: string } | null; onTargetUsed: () => void }) {
  const [tab, setTab] = useState<Tab>("chats"), [player, setPlayer] = useState<string | null>(null);
  const [content, setContent] = useState<WorldContentItem[]>([]), [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null), [groupSetup, setGroupSetup] = useState(false), [detail, setDetail] = useState<WorldContentItem | null>(null);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [budget, setBudget] = useState(() => { const stored = Number(localStorage.getItem("livingworld.turnTokenCeiling")); return Number.isSafeInteger(stored) && stored > 0 ? stored : 131072; });
  const dirty = useRef(false);
  const visuals = useChatVisuals(client, world.world_id, tab === "settings" || !!selected, { roots: selected?.kind === "direct" ? [selected.root_import_id] : [], expressions: false });
  const applyBudget = (next: number) => { setBudget(next); try { localStorage.setItem("livingworld.turnTokenCeiling", String(next)); } catch { /* Keep the applied session value. */ } };
  useEffect(() => {
    if (!target || loading || target.player_id !== player) return;
    const found = conversations.find(item => item.conversation_id === target.conversation_id);
    if (found && (!dirty.current || window.confirm("有未保存的输入，是否打开通知对应的会话？"))) setSelected(found);
    onTargetUsed();
  }, [target, loading, player, conversations, onTargetUsed]);
  useEffect(() => { const read = () => { if (!document.hidden) setReload(value => value + 1); }; window.addEventListener("focus", read); document.addEventListener("visibilitychange", read); return () => { window.removeEventListener("focus", read); document.removeEventListener("visibilitychange", read); }; }, []);
  const refresh = () => setReload(v => v + 1);
  useEffect(() => {
    let active = true; setLoading(true);
    void Promise.all([client.selectedPlayer(world.world_id), client.worldContent(world.world_id), client.conversations(world.world_id), client.groupConversations(world.world_id)]).then(([identity, items, direct, groups]) => {
      if (active) { setPlayer(identity.player_id); setContent(items); setConversations([...direct, ...groups]); setError(""); }
    }).catch(() => { if (active) setError("当前世界没有完整读取，请重新读取。"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [client, world.world_id, reload]);
  useEffect(() => {
    if (!player) return;
    let active = true, timer: ReturnType<typeof setTimeout>;
    const read = async () => {
      if (!document.hidden) {
        try { const next = await client.chatUnread(world.world_id); if (active) setUnread(Object.fromEntries(next.items.map(item => [item.conversation_id, item.unread]))); } catch { /* Keep the last confirmed unread state. */ }
      }
      if (active) timer = setTimeout(read, 10000);
    };
    void read(); return () => { active = false; clearTimeout(timer); };
  }, [client, world.world_id, player, reload, selected]);
  const leave = (action: () => void) => { if (!dirty.current || window.confirm("当前有未保存的输入或正在进行的操作，确定离开吗？")) { dirty.current = false; action(); } };
  const open = async (item: WorldContentItem) => { if (!player || busy) return; setBusy(true); try { setSelected(await client.openDirectConversation(world.world_id, item.import_id)); } catch { setError("暂时无法打开会话，请重试。"); } finally { setBusy(false); } };
  const start = async () => { setBusy(true); try { await client.startAtHome(world.world_id); refresh(); } catch { setError("未能完成身份初始化，请重试。"); } finally { setBusy(false); } };
  const setDirty = useCallback((value: boolean) => { dirty.current = value; onDirtyRoot(value); }, [onDirtyRoot]);
  return <SpeechProvider client={client} worldId={world.world_id}><div className={"mobile-workspace" + (selected ? " mobile-in-chat" : "")}>
    {!selected && <header className="mobile-top"><button onClick={() => leave(onBack)} aria-label="返回世界列表">‹ 世界</button><div><h1>{world.name}</h1><small>{labels[tab]}</small></div><span className="mobile-top-end" /></header>}
    {error && <div className="mobile-error" role="alert">{error}<button onClick={refresh}>重新读取</button></div>}
    {selected && player ? <main className="mobile-chat">{selected.kind === "direct" ? <ChatTranscript client={client} worldId={world.world_id} playerId={player} conversation={selected} tokenCeiling={budget} visualState={visuals} onBack={() => leave(() => { setSelected(null); refresh(); })} onDirtyChange={setDirty} onModelSettings={() => leave(() => { setSelected(null); setTab("settings"); })} /> : <GroupChatDetails client={client} worldId={world.world_id} playerId={player} group={selected} tokenCeiling={budget} visualState={visuals} onBack={() => leave(() => { setSelected(null); refresh(); })} onDirtyChange={setDirty} onModelSettings={() => leave(() => { setSelected(null); setTab("settings"); })} />}</main>
    : <main className="mobile-page">
      {loading ? <p role="status">正在读取…</p> : !player ? <section className="mobile-empty"><h2>先设置你在世界中的身份</h2><p>初始化玩家身份后，即可导入角色并开始聊天。</p><button disabled={busy} onClick={() => void start()} className="primary-button">{busy ? "正在准备…" : "从家开始"}</button></section> : null}
      {!loading && player && tab === "chats" && (groupSetup ? <GroupChatSetup client={client} worldId={world.world_id} onBack={() => leave(() => setGroupSetup(false))} onDirtyChange={setDirty} onCreated={group => { setGroupSetup(false); setSelected(group); refresh(); }} /> : <>
        <div className="mobile-section-heading"><h2>会话</h2><button disabled={busy} onClick={() => setGroupSetup(true)}>新建群聊</button></div>
        {conversations.length ? <ul className="mobile-list">{conversations.map(item => <li key={item.conversation_id}><button onClick={() => setSelected(item)}><span className="mobile-initial">{item.kind === "direct" ? item.character_name.slice(0, 1) : "群"}</span><span><strong>{item.kind === "direct" ? item.character_name : item.participants.map(p => p.character_name).join("、")}</strong><small>{item.kind === "direct" ? "私聊" : "群聊"}{item.read_only ? " · 历史只读" : ""}{unread[item.conversation_id] ? ` · ${unread[item.conversation_id]} 条未读` : ""}</small></span><span aria-hidden="true">›</span></button></li>)}</ul> : <div className="mobile-empty"><h3>还没有会话</h3><p>到通讯录导入角色卡，选择角色即可开始。</p><button onClick={() => setTab("contacts")}>打开通讯录</button></div>}
      </>)}
      {player && tab === "contacts" && <><div className="mobile-section-heading"><h2>角色与世界书</h2></div>{detail ? <><button onClick={() => setDetail(null)}>返回资料列表</button><ContentDetails item={detail} evolutionCard={detail.kind === "character" ? { client, worldId: world.world_id, rootImportId: detail.import_id } : undefined} />{detail.kind === "character" && <CharacterVoice nativeInvoke={mobileInvoke} client={client} worldId={world.world_id} root={detail.import_id} name={detail.characters[0]?.name ?? "角色"} onDirtyChange={setDirty} />}</> : <>
        <ul className="mobile-list">{content.filter(item => item.kind === "character").map(item => <li key={item.import_id}><button disabled={busy} onClick={() => void open(item)}><span className="mobile-initial">{item.characters[0]?.name.slice(0, 1)}</span><span><strong>{item.characters[0]?.name}</strong><small>打开聊天</small></span></button><button className="mobile-detail-button" onClick={() => setDetail(item)}>资料</button></li>)}</ul>
        <details className="mobile-import"><summary>导入／管理角色卡与世界书</summary><WorldImports client={client} worldId={world.world_id} onSaved={refresh} onDirtyChange={setDirty} /></details>
      </>}</>}
      {tab === "settings" && <MobileSettings client={client} world={world} player={player} budget={budget} onBudget={applyBudget} onConfigured={reconnect} onDirtyChange={setDirty} visuals={visuals} onWorldChange={onWorldChange} onNavigate={destination => leave(() => { setTab(destination === "me" ? "me" : destination === "chats" ? "chats" : "contacts"); })} />}
      {player && tab === "me" && <><ProfileEditor client={client} worldId={world.world_id} onDirtyChange={setDirty} /></>}
    </main>}
    {!selected && <nav className="mobile-tabs" aria-label="主导航">{(Object.keys(labels) as Tab[]).map(name => <button key={name} aria-current={tab === name ? "page" : undefined} onClick={() => leave(() => { setTab(name); setGroupSetup(false); setDetail(null); })}>{labels[name]}</button>)}</nav>}
  </div></SpeechProvider>;
}
