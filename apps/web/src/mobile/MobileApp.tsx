import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, type CoreConnection, type WorldSettings, type ChatConversation, type GroupChatConversation } from "@dreamtalk/api-client";
import { ChatTranscript } from "../ChatTranscript";
import { GroupChatDetails, GroupChatSetup } from "../GroupChat";
import { SpeechProvider } from "../SpeechPlayback";
import { MobileContacts } from "./Contacts";
import { ProfileEditor } from "../ProfileEditor";
import { MobileSettings } from "./Settings";
import { useChatVisuals } from "../useChatVisuals";
import { SaveSlotsPanel } from "../SaveSlots";
import { mobileInvoke } from "./native";
import { Brand } from "../Brand";
import { hostCall, feedback } from "./host";
import { ArrowLeft, Heart, MessageCircle, Settings2, Users } from "lucide-react";
import { MobileConversationDirectory } from "./ConversationDirectory";
import { MobileArchiveHome } from "./ArchiveHome";
import { useChatAvatars } from "../useChatAvatars";
type Tab = "chats" | "contacts" | "settings" | "me";
type Conversation = ChatConversation | GroupChatConversation;
const labels: Record<Tab, string> = { chats: "聊天", contacts: "通讯录", settings: "设置", me: "我" };
const tabIcons = { chats: MessageCircle, contacts: Users, settings: Settings2, me: Heart };
export function MobileApp() {
  const [client, setClient] = useState<CoreClient | null>(null), [error, setError] = useState(""), [attempt, setAttempt] = useState(0);
  const [world, setWorld] = useState<WorldSettings | null>(null);
  useEffect(() => { if(world)try{localStorage.setItem("livingworld.lastWorldId",world.world_id);}catch{/* Last view is optional; authoritative data remains in Core. */} },[world]);
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
  if (!client) return <main className="mobile-start dt-world"><span className="mobile-wordmark"><Brand /></span><h1>{error ? "暂时未能打开" : "正在打开你的世界"}</h1><p>{error || "首次启动需要准备本机数据，请稍候。"}</p>{error && <button onClick={() => { setError(""); setAttempt(v => v + 1); }}>重新打开</button>}{error && <button onClick={() => void hostCall("copy_diagnostics").then(() => setError("诊断信息已复制，可发给工程端排查。")).catch(() => setError("诊断暂时无法复制，请保留当前页面。"))}>复制启动诊断</button>}{error && <button onClick={() => setRecovery(value => !value)}>查看存档与恢复</button>}{recovery && <SaveSlotsPanel recovery mobile nativeInvoke={mobileInvoke} />}</main>;
  return <div className="mobile-app dt-world">{world ? <Workspace key={world.world_id} client={client} world={world} onBack={() => setWorld(null)} reconnect={reconnect} onDirtyRoot={onRootDirty} onWorldChange={setWorld} target={target} onTargetUsed={() => setTarget(null)} /> : <MobileArchiveHome client={client} onEnter={setWorld} reconnect={reconnect} onDirtyRoot={onRootDirty} />}</div>;
}
function Workspace({ client, world, onBack, reconnect, onWorldChange, target, onTargetUsed, onDirtyRoot }: { onDirtyRoot: (value: boolean) => void; client: CoreClient; world: WorldSettings; onBack: () => void; reconnect: () => Promise<void>; onWorldChange: (world: WorldSettings) => void; target: { conversation_id: string; player_id: string } | null; onTargetUsed: () => void }) {
  const [tab, setTab] = useState<Tab>("chats"), [player, setPlayer] = useState<string | null>(null);
  const [contactRoot, setContactRoot] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null), [groupSetup, setGroupSetup] = useState(false);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [budget, setBudget] = useState(() => { const stored = Number(localStorage.getItem("livingworld.turnTokenCeiling")); return Number.isSafeInteger(stored) && stored > 0 ? stored : 131072; });
  const dirty = useRef(false);
  const selectedAvatars = useChatAvatars(client, world.world_id, selected?.kind === "direct" ? [selected.root_import_id] : [], !!selected);
  const visuals = useChatVisuals(client, world.world_id, tab === "settings" || tab === "contacts" || !!selected, { roots: selected?.kind === "direct" ? [selected.root_import_id] : tab === "contacts" && contactRoot ? [contactRoot] : [], expressions: false });
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
    void Promise.all([client.selectedPlayer(world.world_id), client.conversations(world.world_id), client.groupConversations(world.world_id)]).then(([identity, direct, groups]) => {
      if (active) { setPlayer(identity.player_id); setConversations([...direct, ...groups]); setError(""); }
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
  const open = async (importId: string) => { if (!player || busy) return; setBusy(true); try { setSelected(await client.openDirectConversation(world.world_id, importId)); } catch { setError("暂时无法打开会话，请重试。"); } finally { setBusy(false); } };
  const start = async () => { setBusy(true); try { await client.startAtHome(world.world_id); refresh(); } catch { setError("未能完成身份初始化，请重试。"); } finally { setBusy(false); } };
  const setDirty = useCallback((value: boolean) => { dirty.current = value; onDirtyRoot(value); }, [onDirtyRoot]);
  return <SpeechProvider client={client} worldId={world.world_id}><div className={"mobile-workspace" + (selected ? " mobile-in-chat" : "")}>
    {!selected && <header className="mobile-top"><button className="mobile-icon-action" onClick={() => leave(onBack)} aria-label="返回世界列表"><ArrowLeft size={21}/></button><div><h1>{labels[tab]}</h1><small>{world.name}<span className="mobile-world-time" aria-label="世界时间"> · {world.world_time}</span></small></div><span className="mobile-top-end" aria-hidden="true"><Brand /></span></header>}
    {error && <div className="mobile-error" role="alert">{error}<button onClick={refresh}>重新读取</button></div>}
    {selected && player ? <main className="mobile-chat">{selected.kind === "direct" ? <ChatTranscript client={client} worldId={world.world_id} playerId={player} conversation={selected} avatarUrl={selectedAvatars[selected.root_import_id]} tokenCeiling={budget} visualState={visuals} onBack={() => leave(() => { setSelected(null); refresh(); })} onDirtyChange={setDirty} onModelSettings={() => leave(() => { setSelected(null); setTab("settings"); })} /> : <GroupChatDetails client={client} worldId={world.world_id} playerId={player} group={selected} tokenCeiling={budget} visualState={visuals} onBack={() => leave(() => { setSelected(null); refresh(); })} onDirtyChange={setDirty} onModelSettings={() => leave(() => { setSelected(null); setTab("settings"); })} />}</main>
    : <main className={"mobile-page mobile-tab-" + tab}>
      {loading ? <p role="status">正在读取…</p> : !player ? <section className="mobile-empty"><h2>先设置你在世界中的身份</h2><p>初始化玩家身份后，即可导入角色并开始聊天。</p><button disabled={busy} onClick={() => void start()} className="primary-button">{busy ? "正在准备…" : "从家开始"}</button></section> : null}
      {!loading && player && tab === "chats" && (groupSetup ? <GroupChatSetup client={client} worldId={world.world_id} onBack={() => leave(() => setGroupSetup(false))} onDirtyChange={setDirty} onCreated={group => { setGroupSetup(false); setSelected(group); refresh(); }} /> : <>
        <MobileConversationDirectory key={player} client={client} worldId={world.world_id} conversations={conversations} unread={unread} busy={busy}
          onOpen={setSelected} onNewGroup={() => setGroupSetup(true)} onContacts={() => setTab("contacts")}
          onPinned={(id, pinned) => setConversations(items => items.map(item => item.conversation_id === id ? { ...item, pinned } : item))}/>
      </>)}
      {player && tab === "contacts" && <MobileContacts client={client} worldId={world.world_id} refreshKey={reload} busy={busy} onOpenChat={open} onSaved={refresh} onDirtyChange={setDirty} visualState={visuals} onSelectedRootChange={setContactRoot} />}
      {tab === "settings" && <MobileSettings client={client} world={world} player={player} budget={budget} onBudget={applyBudget} onConfigured={reconnect} onDirtyChange={setDirty} visuals={visuals} onWorldChange={onWorldChange} onNavigate={destination => leave(() => { setTab(destination === "me" ? "me" : destination === "chats" ? "chats" : "contacts"); })} />}
      {player && tab === "me" && <><ProfileEditor client={client} worldId={world.world_id} onDirtyChange={setDirty} /></>}
    </main>}
    {!selected && <nav className="mobile-tabs" aria-label="主导航">{(Object.keys(labels) as Tab[]).map(name => { const Icon = tabIcons[name]; return <button key={name} aria-current={tab === name ? "page" : undefined} onClick={() => leave(() => { setTab(name); setGroupSetup(false); })}><span className="mobile-tab-icon"><Icon size={21}/></span><span>{labels[name]}</span></button>; })}</nav>}
  </div></SpeechProvider>;
}
