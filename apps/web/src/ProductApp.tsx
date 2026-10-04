import { invoke, isTauri } from "@tauri-apps/api/core";
import { BackgroundSettings, type DesktopStatus } from "./BackgroundSettings";
import { OfflineContactSettings } from "./OfflineContactSettings";
import { useOfflineContact } from "./useOfflineContact";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CoreClient, type ChatConversation, type GroupChatConversation, type KnownWorldEvent, type PlayerAvailability, type SelectablePlayer, type SelectedPlayerState, type WorldSettings } from "@dreamtalk/api-client";
import { useChatUnread } from "./useChatUnread";
import { ProactiveContactSettings } from "./ProactiveContactSettings";
import { ChatTranscript } from "./ChatTranscript";
import { GroupChatDetails, GroupChatSetup } from "./GroupChat";
import { ModelSetup, type ModelSetupSummary } from "./ModelSetup";
import { WorldImports, WorldContacts } from "./WorldContent";
import { WorldEventJournal } from "./WorldEventJournal";
import { WorldNewsSettings } from "./WorldNewsSettings";
import { WorldActivities } from "./WorldActivities";
import type { BackgroundDestination } from "./BackgroundTaskFeedback";
import { WorldLocations } from "./WorldLocations";
import { CharacterActivitySetup } from "./CharacterActivitySetup";
import { ProfileEditor } from "./ProfileEditor";
import { WorldArchivePage } from "./WorldArchivePage";
import { Brand } from "./Brand";
import { SettingsHandbook, SettingsFold, type SettingsPage } from "./SettingsHandbook";
import { SettingsDiagnostics } from "./SettingsDiagnostics";
import "./product.css";

type Tab = "chats" | "contacts" | "settings" | "me";
type IconName = "chats" | "contacts" | "settings" | "me";

function TabIcon({ name }: { name: IconName }) {
  const paths = {
    chats: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5 9 9 0 0 1-3.6-.7L4 20l1.5-4.2a7.5 7.5 0 1 1 14.5-4.3Z" /><path d="M8 11.5h8" /></>,
    contacts: <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M17 5.5a3 3 0 0 1 0 5.5M17 14a5 5 0 0 1 3.5 5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="m10 2-.5 2.2-2 .8-2-1.1-2.6 2.6 1.1 2-.8 2L1 11v2l2.2.5.8 2-1.1 2 2.6 2.6 2-1.1 2 .8L10 22h4l.5-2.2 2-.8 2 1.1 2.6-2.6-1.1-2 .8-2L23 13v-2l-2.2-.5-.8-2 1.1-2-2.6-2.6-2 1.1-2-.8L14 2Z" /></>,
    me: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  } satisfies Record<IconName, ReactNode>;
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

const tabs: Array<{ id: Tab; label: string }> = [
  { id: "chats", label: "聊天" },
  { id: "contacts", label: "通讯录" },
  { id: "settings", label: "设置" },
  { id: "me", label: "我" },
];

function displayTime(raw: string): string {
  const micros = BigInt(raw);
  if (micros < 0n) return `逻辑时间 ${raw} 微秒`;
  const minutes = micros / 60_000_000n;
  const day = minutes / 1440n + 1n;
  const hour = (minutes % 1440n) / 60n;
  const minute = minutes % 60n;
  return `第 ${day} 天 · ${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")}`;
}

const TOKEN_CEILING_KEY = "livingworld.chat.turnTokenCeiling";
const LAST_WORLD_KEY = "livingworld.lastWorldId";
function savedWorldId(): string | null {
  try {
    const value = window.localStorage.getItem(LAST_WORLD_KEY);
    return value && value.length <= 128 ? value : null;
  } catch { return null; }
}
function savedTokenCeiling(): number {
  try {
    const value = Number(window.localStorage.getItem(TOKEN_CEILING_KEY));
    if (Number.isSafeInteger(value) && value >= 1) return value;
  } catch { /* Storage can be disabled; keep a safe local default. */ }
  return 50_000;
}

export function ProductApp({ client, onStartupStatus }: { client: CoreClient; onStartupStatus?: (ready: boolean) => void }) {
  useEffect(() => {
    const preventFileNavigation = (event: DragEvent) => {
      if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
    };
    window.addEventListener("dragover", preventFileNavigation);
    window.addEventListener("drop", preventFileNavigation);
    return () => { window.removeEventListener("dragover", preventFileNavigation); window.removeEventListener("drop", preventFileNavigation); };
  }, []);
  const [entered, setEntered] = useState<{ worldId: string; hasIdentity: boolean } | null>(null);
  const [previewId, setPreviewId] = useState(savedWorldId);
  return entered ? <WorldWorkspace key={entered.worldId} client={client} initialWorldId={entered.worldId}
    initialTab={entered.hasIdentity ? "chats" : "me"} onArchive={() => { setPreviewId(entered.worldId); setEntered(null); }} />
    : <WorldArchivePage client={client} initialWorldId={previewId} displayTime={displayTime} onStartupStatus={onStartupStatus}
      onEnter={(worldId, hasIdentity) => setEntered({ worldId, hasIdentity })} />;
}

function WorldWorkspace({ client, initialWorldId, initialTab, onArchive }: {
  client: CoreClient; initialWorldId: string; initialTab: Tab; onArchive: () => void;
}) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const entryHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { entryHeading.current?.focus(); }, []);
  const [meVisited, setMeVisited] = useState(false);
  const [contactsVisited, setContactsVisited] = useState(initialTab === "contacts");
  const [contactsManagementOpen, setContactsManagementOpen] = useState(false);
  const [contactsRefresh, setContactsRefresh] = useState(0);
  const contactsManager = useRef<HTMLElement>(null);
  const [settingsPage, setSettingsPage] = useState<SettingsPage>("model");
  const [desktopStatus, setDesktopStatus] = useState<DesktopStatus | null>(null);
  const [backgroundDirty, setBackgroundDirty] = useState(false);
  const [modelSummary, setModelSummary] = useState<ModelSetupSummary | null>(null);
  const [worldContentDirty, setWorldContentDirty] = useState(false);
  const [worldLocationsDirty, setWorldLocationsDirty] = useState(false);
  const [characterActivityDirty, setCharacterActivityDirty] = useState(false);
  const [activityReadiness, setActivityReadiness] = useState<{ client: CoreClient; playerId: string | null; ready: boolean | null } | null>(null);
  const [worldProfileDirty, setWorldProfileDirty] = useState(false);
  const [worlds, setWorlds] = useState<WorldSettings[]>([]);
  const worldId = initialWorldId;
  const [generalProfileDirty, setGeneralProfileDirty] = useState(false);
  const [chatDirty, setChatDirty] = useState(false);
  const [modelDirty, setModelDirty] = useState(false);
  const [scale, setScale] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [eventsOpen, setEventsOpen] = useState(false);
  const [players, setPlayers] = useState<SelectablePlayer[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState<string | null>(null);
  const reportActivityReadiness = useCallback((ready: boolean | null) => { setActivityReadiness({ client, playerId: selectedPlayer, ready }); }, [client, selectedPlayer]);
  const [selectedPlayerState, setSelectedPlayerState] = useState<SelectedPlayerState | null>(null);
  const [playerChoice, setPlayerChoice] = useState("");
  const [knownEvents, setKnownEvents] = useState<{ worldId: string; playerId: string; items: KnownWorldEvent[] } | null>(null);
  const [topicEvent, setTopicEvent] = useState<KnownWorldEvent | null>(null);
  const [draftSuggestion, setDraftSuggestion] = useState<{ worldId: string; playerId: string; conversationId: string; text: string } | null>(null);
  const [conversationDirectory, setConversationDirectory] = useState<{ worldId: string; playerId: string; items: ChatConversation[] } | null>(null);
  const [groupDirectory, setGroupDirectory] = useState<{ worldId: string; playerId: string; items: GroupChatConversation[] } | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groupSetupOpen, setGroupSetupOpen] = useState(false);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [conversationsFailed, setConversationsFailed] = useState(false);
  const [conversationsRefresh, setConversationsRefresh] = useState(0);
  const [tokenCeiling, setTokenCeiling] = useState(savedTokenCeiling);
  const [tokenCeilingInput, setTokenCeilingInput] = useState(() => String(savedTokenCeiling()));
  const offlineContact = useOfflineContact(client, worldId, selectedPlayer);
  const unread = useChatUnread(client, worldId, selectedPlayer);
  const unreadDirectoryKey = unread.value?.items.map(item => item.conversation_id).join(":") ?? "";
  const tokenCeilingValid = Number.isSafeInteger(Number(tokenCeilingInput)) && Number(tokenCeilingInput) >= 1;

  const refresh = useCallback(async () => {
    const items = await client.listProductWorlds();
    setWorlds(items);
  }, [client]);
  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let failures = 0;
    const controller = new AbortController();
    const read = async () => {
      try {
        const items = await client.listProductWorlds(controller.signal);
        if (active) { setWorlds(items); failures = 0; setError(current => current === "世界状态暂时无法更新，请检查核心连接。" ? "" : current); }
      } catch {
        if (active) { ++failures; setError("世界状态暂时无法更新，请检查核心连接。"); }
      } finally {
        if (active) timer = window.setTimeout(() => void read(), failures > 0 ? 10_000 : 2_000);
      }
    };
    void read();
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [client]);
  const world = useMemo(() => worlds.find(item => item.world_id === worldId), [worlds, worldId]);
  useEffect(() => {
    if (!world) return;
    try { window.localStorage.setItem(LAST_WORLD_KEY, world.world_id); }
    catch { /* The current world remains selected for this session. */ }
  }, [world?.world_id]);
  useEffect(() => { if (tab === "me") setMeVisited(true); if (tab === "contacts") setContactsVisited(true); }, [tab]);
  const openContactsManager = () => { setContactsManagementOpen(true); window.requestAnimationFrame(() => { contactsManager.current?.scrollIntoView({ block: "start" }); contactsManager.current?.focus({ preventScroll: true }); }); };
  useEffect(() => { if (world) setScale(world.time_scale); }, [world?.world_id, world?.time_scale]);
  const loadIdentity = useCallback(async (id: string) => {
    return await Promise.all([client.listPlayers(id), client.selectedPlayer(id)] as const);
  }, [client]);
  useEffect(() => {
    let active = true;
    setPlayers([]); setSelectedPlayer(null); setSelectedPlayerState(null); setPlayerChoice(""); setKnownEvents(null); setTopicEvent(null); setDraftSuggestion(null); setEventsOpen(false); setConversationDirectory(null); setGroupDirectory(null); setSelectedConversationId(null); setSelectedGroupId(null); setGroupSetupOpen(false);
    if (worldId) void loadIdentity(worldId).then(([available, selected]) => {
      if (!active) return;
      setPlayers(available); setSelectedPlayer(selected.player_id);
      setSelectedPlayerState(selected);
      setPlayerChoice(selected.player_id ?? available[0]?.player_id ?? "");
    }).catch(() => { if (active) setError("无法读取当前世界的玩家身份。"); });
    return () => { active = false; };
  }, [worldId, loadIdentity]);
  useEffect(() => {
    if (!isTauri()) return;
    let active = true;
    let timer: number | undefined;
    let running = false;
    const report = async () => {
      if (running || !active) return;
      running = true;
      try {
        await invoke("report_desktop_presence", { worldId: selectedPlayer ? worldId : null,
          visible: Boolean(worldId && selectedPlayer && document.visibilityState === "visible" && document.hasFocus()) });
      } catch { /* Failure leaves the short visibility lease expired. */ }
      finally { running = false; if (active) { window.clearTimeout(timer); timer = window.setTimeout(() => void report(), 10000); } }
    };
    const changed = () => { void report(); };
    window.addEventListener("focus", changed); window.addEventListener("blur", changed);
    document.addEventListener("visibilitychange", changed);
    void report();
    return () => { active = false; window.clearTimeout(timer);
      window.removeEventListener("focus", changed); window.removeEventListener("blur", changed);
      document.removeEventListener("visibilitychange", changed);
      void invoke("report_desktop_presence", { worldId: null, visible: false }).catch(() => undefined); };
  }, [worldId, selectedPlayer]);
  useEffect(() => { setTopicEvent(null); setDraftSuggestion(null); }, [selectedPlayer]);
  useEffect(() => {
    let active = true;
    if (!worldId || !selectedPlayer || tab !== "chats") return;
    const controller = new AbortController();
    setConversationsLoading(true); setConversationsFailed(false);
    const directRead = client.conversations(worldId, controller.signal).then(items => {
      if (active) setConversationDirectory(current => {
        const justOpened = current?.worldId === worldId && current.playerId === selectedPlayer ? current.items : [];
        return { worldId, playerId: selectedPlayer, items: [
          ...items,
          ...justOpened.filter(local => !items.some(remote => remote.conversation_id === local.conversation_id)),
        ] };
      });
    }).catch(() => { if (active) { setConversationsFailed(true); setError("无法读取当前世界的会话，请重新读取或检查核心连接。"); } });
    const groupRead = client.groupConversations(worldId, controller.signal).then(items => {
      if (active) setGroupDirectory(current => {
        const justCreated = current?.worldId === worldId && current.playerId === selectedPlayer ? current.items : [];
        return { worldId, playerId: selectedPlayer, items: [
          ...items,
          ...justCreated.filter(local => !items.some(remote => remote.conversation_id === local.conversation_id)),
        ] };
      });
    }).catch(() => { if (active) { setConversationsFailed(true); setError("无法读取当前世界的群聊，请重新读取或检查核心连接。"); } });
    void Promise.allSettled([directRead, groupRead]).finally(() => { if (active) setConversationsLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [client, worldId, selectedPlayer, tab, conversationsRefresh, unreadDirectoryKey]);
  useEffect(() => {
    let active = true;
    setKnownEvents(null);
    if (!worldId || !selectedPlayer || !eventsOpen) return;
    const update = () => void client.knownEvents(worldId).then(items => {
      if (active) setKnownEvents({ worldId, playerId: selectedPlayer, items });
    }).catch(() => { if (active) setError("无法读取已获知的事件。"); });
    update();
    const timer = window.setInterval(update, 2_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [client, worldId, selectedPlayer, eventsOpen]);

  const act = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); setNotice(success); }
    catch { setError("操作未完成，请稍后重试。"); }
    finally { setBusy(false); }
  };
  const openChat = async (importId: string) => {
    if (!world || !selectedPlayer || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const conversation = await client.openDirectConversation(world.world_id, importId);
      setConversationDirectory(current => ({
        worldId: world.world_id,
        playerId: selectedPlayer,
        items: [
          ...(current?.worldId === world.world_id && current.playerId === selectedPlayer ? current.items : []).filter(item => item.conversation_id !== conversation.conversation_id),
          conversation,
        ],
      }));
      setSelectedConversationId(conversation.conversation_id);
      setSelectedGroupId(null); setGroupSetupOpen(false);
      setEventsOpen(false);
      setTab("chats");
    } catch { setError("会话未能打开，请稍后重试。"); }
    finally { setBusy(false); }
  };

  const title = tabs.find(item => item.id === tab)?.label ?? "聊天";
  const visibleEvents = knownEvents?.worldId === worldId && knownEvents.playerId === selectedPlayer ? knownEvents.items : [];
  const conversations = conversationDirectory?.worldId === worldId && conversationDirectory.playerId === selectedPlayer ? conversationDirectory.items : [];
  const groups = groupDirectory?.worldId === worldId && groupDirectory.playerId === selectedPlayer ? groupDirectory.items : [];
  const selectedConversation = conversations.find(item => item.conversation_id === selectedConversationId);
  const selectedGroup = groups.find(item => item.conversation_id === selectedGroupId);
  const discussEvent = (conversationId: string, kind: "direct" | "group") => {
    if (!topicEvent || !worldId || !selectedPlayer) return;
    setDraftSuggestion({
      worldId, playerId: selectedPlayer, conversationId,
      text: `我看到一条世界事件：「${topicEvent.description || topicEvent.title}」（${displayTime(topicEvent.occurred_at)}）。你知道这件事吗？`,
    });
    setSelectedConversationId(kind === "direct" ? conversationId : null);
    setSelectedGroupId(kind === "group" ? conversationId : null);
    setTopicEvent(null);
    setEventsOpen(false);
  };
  const suggestedFor = (conversationId: string) => draftSuggestion?.worldId === worldId && draftSuggestion.playerId === selectedPlayer && draftSuggestion.conversationId === conversationId ? draftSuggestion.text : null;
  const returnArchive = () => {
    if ((worldProfileDirty || generalProfileDirty || worldContentDirty || worldLocationsDirty || characterActivityDirty || chatDirty || modelDirty || backgroundDirty || offlineContact.busy || Number(tokenCeilingInput) !== tokenCeiling || busy)
      && !window.confirm("有尚未保存的编辑或正在处理的请求，是否返回书架？已发起的生成可能继续并产生用量。")) return;
    onArchive();
  };
  const navigateBackgroundTask = (destination: BackgroundDestination) => {
    if (destination === "lore") { returnArchive(); return; }
    if (destination === "contacts" || destination === "me") { setTab(destination); return; }
    if (destination === "events" || destination === "chats") {
      setEventsOpen(destination === "events"); setTab("chats"); return;
    }
    setSettingsPage(destination === "locations" ? "activities" : destination);
    if (destination === "locations") window.requestAnimationFrame(() => {
      const section = document.getElementById("character-initial-activity");
      section?.scrollIntoView({ block: "start" }); section?.focus({ preventScroll: true });
    });
  };
  return <div className="product-shell world-workspace">
    <header className="app-header"><Brand /><span role="status" className="sr-only">核心已就绪</span><span className="workspace-header-actions"><span className="world-context">{world?.name ?? "正在读取世界…"}</span><button type="button" className="text-action" onClick={returnArchive}>返回书架</button></span></header>
    <main className="app-content" id="main-content">
      <div className="page-heading"><h1 ref={entryHeading} tabIndex={-1}>{title}</h1>{world ? <span className="page-world">{world.name}</span> : null}</div>
      {error ? <p className="app-alert" role="alert">{error}</p> : null}
      {notice ? <p className="app-notice" role="status">{notice}</p> : null}

      {tab === "chats" && <div className={`chat-workspace ${eventsOpen || selectedConversation || selectedGroup || groupSetupOpen ? "thread-open" : ""}`}>
        <aside className="conversation-list" aria-label="会话列表">
        <button className={`conversation-row pinned ${eventsOpen ? "selected" : ""}`} aria-pressed={eventsOpen} type="button" onClick={() => { setTopicEvent(null); setEventsOpen(true); }}>
          <span className="avatar event-avatar" aria-hidden="true">事</span>
          <span className="row-copy"><strong>世界事件</strong><small>你已获知的事件</small></span>
          <span className="pin-label">置顶</span>
        </button>
        {selectedPlayer ? <button type="button" className="group-create-link" onClick={() => { setGroupSetupOpen(true); setSelectedGroupId(null); setSelectedConversationId(null); setEventsOpen(false); }}>＋ 新建群聊</button> : null}
        {unread.error && <div className="thread-hint" role="status">新消息提示暂未更新。<button type="button" className="text-action" onClick={unread.refresh}>重新读取消息提示</button></div>}
        {conversationsFailed && <div className="thread-hint" role="alert"><p>会话读取未完成，已读取的会话仍保留。</p><button type="button" className="text-action" disabled={conversationsLoading} onClick={() => setConversationsRefresh(value => value + 1)}>重新读取会话</button></div>}
        {conversationsLoading && conversations.length === 0 && groups.length === 0 ? <p className="thread-hint">正在读取会话…</p> : conversationsFailed && conversations.length === 0 && groups.length === 0 ? null : conversations.length === 0 && groups.length === 0 ? <div className="empty-state"><h2>还没有会话</h2><p>在通讯录中选择角色，打开与他的会话。</p><button type="button" className="text-action" onClick={() => setTab("contacts")}>前往通讯录</button></div> : <>
          {groups.map(item => <button key={item.conversation_id} type="button" className={`conversation-row ${!eventsOpen && selectedGroupId === item.conversation_id ? "selected" : ""}`} aria-pressed={!eventsOpen && selectedGroupId === item.conversation_id} onClick={() => { setDraftSuggestion(null); setSelectedGroupId(item.conversation_id); setSelectedConversationId(null); setGroupSetupOpen(false); setEventsOpen(false); }}><span className="avatar event-avatar" aria-hidden="true">群</span><span className="row-copy"><strong>{item.participants.map(member => member.character_name).join("、")}{unread.unread(item.conversation_id) && <span className="unread-dot" role="img" aria-label="有未读角色消息" />}</strong><small>群聊 · {item.participants.length} 位角色</small></span></button>)}
          {conversations.map(item => <button key={item.conversation_id} type="button" className={`conversation-row ${!eventsOpen && selectedConversationId === item.conversation_id ? "selected" : ""}`} aria-pressed={!eventsOpen && selectedConversationId === item.conversation_id} onClick={() => { setDraftSuggestion(null); setSelectedConversationId(item.conversation_id); setSelectedGroupId(null); setGroupSetupOpen(false); setEventsOpen(false); }}><span className="avatar event-avatar" aria-hidden="true">{Array.from(item.character_name)[0]}</span><span className="row-copy"><strong>{item.character_name}{unread.unread(item.conversation_id) && <span className="unread-dot" role="img" aria-label="有未读角色消息" />}</strong><small>{unread.unread(item.conversation_id) ? "新消息" : "私聊"}</small></span></button>)}
        </>}

        </aside>
        <div className="conversation-detail">
          {eventsOpen ? <section className="event-thread" aria-label="世界事件时间线">
        <div className="thread-heading"><button type="button" className="text-action" onClick={() => setEventsOpen(false)}>返回聊天</button><h2>世界事件</h2><span>聊天获知与世界动态</span></div>
        {topicEvent ? <div className="event-topic-picker"><strong>聊聊「{topicEvent.title}」</strong><p>选择已有会话，系统只填写一条可编辑的消息，不会自动发送。</p>{conversations.length === 0 && groups.length === 0 ? <p>先从通讯录打开一位角色的会话。</p> : <div className="event-topic-choices">{conversations.map(item => <button type="button" key={item.conversation_id} onClick={() => discussEvent(item.conversation_id, "direct")}>{item.character_name}</button>)}{groups.map(item => <button type="button" key={item.conversation_id} onClick={() => discussEvent(item.conversation_id, "group")}>群聊：{item.participants.map(member => member.character_name).join("、")}</button>)}</div>}</div> : null}
        {!world ? <p className="thread-hint">先创建世界，才能查看事件。</p> : !selectedPlayer ? <div className="thread-empty"><p>先进入当前世界，才能查看你获知的事件。</p><button type="button" className="text-action" onClick={() => { setEventsOpen(false); setTab("me"); }}>前往我的身份</button></div> : <WorldEventJournal key={`journal:${worldId}:${selectedPlayer}`} client={client} worldId={worldId} witnessed={visibleEvents} onTopic={setTopicEvent} displayTime={displayTime} />}
          </section> : groupSetupOpen ? <GroupChatSetup key={`${worldId}:${selectedPlayer}`} client={client} worldId={worldId} onBack={() => setGroupSetupOpen(false)} onDirtyChange={setChatDirty} onCreated={group => { setGroupDirectory(current => ({ worldId, playerId: selectedPlayer!, items: [...(current?.worldId === worldId && current.playerId === selectedPlayer ? current.items : []).filter(item => item.conversation_id !== group.conversation_id), group] })); setSelectedGroupId(group.conversation_id); setGroupSetupOpen(false); }} /> : selectedGroup && selectedPlayer ? <GroupChatDetails key={`${worldId}:${selectedPlayer}:${selectedGroup.conversation_id}`} client={client} worldId={worldId} playerId={selectedPlayer} group={selectedGroup} onDirtyChange={setChatDirty} tokenCeiling={tokenCeiling} suggestedDraft={suggestedFor(selectedGroup.conversation_id)} onSuggestionUsed={() => setDraftSuggestion(null)} onBack={() => setSelectedGroupId(null)} /> : selectedConversation && selectedPlayer ? <ChatTranscript key={`${worldId}:${selectedPlayer}:${selectedConversation.conversation_id}`} client={client} worldId={worldId} playerId={selectedPlayer} conversation={selectedConversation} onDirtyChange={setChatDirty} tokenCeiling={tokenCeiling} suggestedDraft={suggestedFor(selectedConversation.conversation_id)} onSuggestionUsed={() => setDraftSuggestion(null)} onBack={() => setSelectedConversationId(null)} /> : <div className="conversation-placeholder"><h2>与世界保持联系</h2><p>从左侧选择会话，或查看你已获知的世界事件。</p></div>}
        </div>
      </div>}

      {(tab === "contacts" || contactsVisited) && <div className="contacts-page" hidden={tab !== "contacts"}>
        {world ? <>
          <div className="contacts-toolbar"><div><h2>「{world.name}」的角色</h2><p>已确认的角色卡只加入当前世界。</p></div><button type="button" className="primary-button" onClick={openContactsManager}>＋ 添加角色卡</button></div>
          <details className="contacts-management" open={contactsManagementOpen} onToggle={event => setContactsManagementOpen(event.currentTarget.open)}>
            <summary ref={contactsManager}><strong>添加与编辑角色卡</strong><span>{worldContentDirty ? "有未保存的编辑 · 草稿保留中" : "新建、联网生成或从文件导入"}</span></summary>
            <WorldImports key={`content:${world.world_id}`} client={client} worldId={world.world_id} onlyKind="character" onDirtyChange={setWorldContentDirty} onSaved={() => setContactsRefresh(value => value + 1)} />
          </details>
          <WorldContacts key={world.world_id} client={client} worldId={world.world_id} refreshKey={contactsRefresh} visible={tab === "contacts"} onSettings={openContactsManager} onIdentity={() => setTab("me")} onOpenChat={openChat} canOpenChat={!!selectedPlayer} openingChat={busy} />
        </> : <div className="page-section"><div className="empty-state"><h2>先创建一个世界</h2><p>在世界档案库创建世界，然后新建或导入角色卡。</p><button className="text-action" onClick={returnArchive}>前往世界档案库</button></div></div>}
      </div>}

      <SettingsHandbook client={client} world={world} visible={tab === "settings"} page={settingsPage} onPage={setSettingsPage} onArchive={returnArchive}
        dirtyPages={{ model: modelDirty || Number(tokenCeilingInput) !== tokenCeiling, background: backgroundDirty, activities: worldLocationsDirty || characterActivityDirty }}
        panels={{
          model: <>
            <SettingsFold title="模型服务与回复" summary={modelSummary?.model ? `${modelSummary.model} · 单次回复上限 ${modelSummary.replyTokens?.toLocaleString("zh-CN") ?? "待核对"} Token` : modelSummary?.status === "unconfigured" ? "尚未配置，展开完成首次设置" : modelSummary?.status ? "已读取配置状态，展开查看模型设置" : "正在读取模型配置…"} open>
              <ModelSetup client={client} turnTokenCeiling={tokenCeiling} onDirtyChange={setModelDirty} onSummaryChange={setModelSummary} />
            </SettingsFold>
            <SettingsFold title="聊天额度" summary={`已应用 ${tokenCeiling.toLocaleString("zh-CN")} Token / 轮${Number(tokenCeilingInput) !== tokenCeiling ? " · 新数值尚未应用" : ""}`}>
              <section className="settings-section"><div className="section-heading"><h2>聊天额度</h2><p>每轮输入和输出共用上限。系统按可信上界预留，额度不足时不会开始下一次模型调用。</p></div>
          <div className="setting-row"><label className="field"><span>每轮 Token 上限</span><input type="number" min="1" max={Number.MAX_SAFE_INTEGER} step="1" value={tokenCeilingInput} onChange={event => setTokenCeilingInput(event.target.value)} /></label><button type="button" className="secondary-button" disabled={!tokenCeilingValid} onClick={() => { const next = Number(tokenCeilingInput); setTokenCeiling(next); try { window.localStorage.setItem(TOKEN_CEILING_KEY, String(next)); } catch { /* Session setting remains active. */ } setNotice("聊天额度已更新。"); }}>应用</button></div>
          {!tokenCeilingValid ? <p className="app-alert" role="alert">请输入 1 至 {Number.MAX_SAFE_INTEGER.toLocaleString("zh-CN")} 之间的整数聊天额度。</p> : null}
          <p className="inline-hint" role="status">当前已应用的聊天额度：{tokenCeiling.toLocaleString("zh-CN")} Token。{Number(tokenCeilingInput) !== tokenCeiling ? "输入的新数值尚未应用，请点击应用。" : "该额度仅用于聊天，不限制角色卡或世界书生成；额度是预留上限，实际费用以提供商报告的用量为准。"}</p>
        </section>
            </SettingsFold>
          </>,
          background: <BackgroundSettings onStatusChange={setDesktopStatus} onDirtyChange={setBackgroundDirty} />,
          time: <>{world && <section className="settings-section"><div className="section-heading"><h2>世界时间</h2><p>{displayTime(world.world_time)}</p></div>
          <div className="setting-row"><span><strong>时间状态</strong><small>{world.clock_state === "running" ? "运行中" : "已暂停"}{world.runtime_state === "degraded" ? " · 运行异常" : ""}</small></span><button type="button" className="secondary-button" disabled={busy || world.runtime_state === "degraded"} onClick={() => void act(() => world.clock_state === "running" ? client.pauseProductWorld(world.world_id) : client.resumeProductWorld(world.world_id), world.clock_state === "running" ? "世界已暂停。" : "世界已恢复。")}>{world.clock_state === "running" ? "暂停" : "恢复"}</button></div>
          <div className="setting-row"><label className="field"><span>时间倍率</span><input type="number" min="0.01" max="1000" step="0.01" inputMode="decimal" value={scale} onChange={event => setScale(event.target.value)} /></label><button type="button" className="secondary-button" disabled={busy || !scale || Number(scale) <= 0 || Number(scale) > 1000} onClick={() => void act(() => client.scaleProductWorld(world.world_id, scale), "时间倍率已更新。")}>应用</button></div>
        </section>}</>,
          activities: <>{world && <WorldLocations key={`locations:${world.world_id}`} client={client} worldId={world.world_id} visible={tab === "settings" && settingsPage === "activities"} onDirtyChange={setWorldLocationsDirty} />}
        {world && selectedPlayer && <CharacterActivitySetup key={`initial-activity:${world.world_id}:${selectedPlayer}`} client={client} worldId={world.world_id} playerId={selectedPlayer} visible={tab === "settings" && settingsPage === "activities"} onDirtyChange={setCharacterActivityDirty} onReadinessChange={reportActivityReadiness} />} {world && selectedPlayer && <WorldActivities key={`activities:${world.world_id}:${selectedPlayer}`} client={client} worldId={world.world_id} visible={tab === "settings" && settingsPage === "activities"} paused={world.clock_state === "paused"} onNavigate={navigateBackgroundTask} hasInitializedCharacters={activityReadiness?.client === client && activityReadiness.playerId === selectedPlayer ? activityReadiness.ready : null} />}{!selectedPlayer && <section className="settings-section"><p className="inline-hint">先在“我”中进入当前世界，再设置角色的初始活动位置和自动活动。</p><button type="button" className="text-action" onClick={() => setTab("me")}>前往我</button></section>}</>,
          offline: <>{world && selectedPlayer && selectedPlayerState?.availability && selectedPlayerState.presence_revision !== null && <section className="settings-section"><div className="section-heading"><h2>交流状态</h2><p>忙碌状态不会暂停世界运行，已开启的离线联系会跳过普通主动消息；设为可用不会立即补发。</p></div>
          <div className="setting-row"><span><strong>{selectedPlayerState.availability === "available" ? "可用" : "忙碌"}</strong><small>仅适用于当前世界绑定的玩家身份</small></span><button type="button" className="secondary-button" disabled={busy} onClick={() => {
            const next: PlayerAvailability = selectedPlayerState.availability === "available" ? "busy" : "available";
            void act(async () => {
              await client.setPlayerAvailability(world.world_id, next, selectedPlayerState.presence_revision!, crypto.randomUUID());
              const state = await client.selectedPlayer(world.world_id);
              setSelectedPlayerState(state);
            }, next === "available" ? "当前状态已设为可用。" : "当前状态已设为忙碌。");
          }}>{selectedPlayerState.availability === "available" ? "设为忙碌" : "设为可用"}</button></div>
        </section>} {world && selectedPlayer && <><ProactiveContactSettings key={`proactive:${world.world_id}:${selectedPlayer}`} client={client} worldId={world.world_id} playerId={selectedPlayer} /><OfflineContactSettings key={`offline:${world.world_id}:${selectedPlayer}`} status={offlineContact.status} busy={offlineContact.busy} refreshing={offlineContact.refreshing} error={offlineContact.error} onRefresh={offlineContact.refresh} onSave={offlineContact.save} paused={world.clock_state === "paused"} availability={selectedPlayerState?.availability ?? null} onNavigate={navigateBackgroundTask} /></>}{!selectedPlayer && <section className="settings-section"><p className="inline-hint">先在“我”中进入当前世界，再设置离线联系。</p><button type="button" className="text-action" onClick={() => setTab("me")}>前往我</button></section>}</>,
          news: <>{world && selectedPlayer && <WorldNewsSettings key={`news:${world.world_id}:${selectedPlayer}`} client={client} worldId={world.world_id} visible={tab === "settings" && settingsPage === "news"} paused={world.clock_state === "paused"} onNavigate={navigateBackgroundTask} />}{!selectedPlayer && <section className="settings-section"><p className="inline-hint">先在“我”中进入当前世界，再设置世界动态。</p><button type="button" className="text-action" onClick={() => setTab("me")}>前往我</button></section>}</>,
          about: <SettingsDiagnostics client={client} visible={tab === "settings" && settingsPage === "about"} desktop={desktopStatus} onBackground={() => setSettingsPage("background")} />,
        }} />

      {(tab === "me" || meVisited) && <div className="settings-page profile-page" hidden={tab !== "me"}><ProfileEditor client={client} onDirtyChange={setGeneralProfileDirty} /><section className="settings-section"><div className="section-heading"><h2>我在当前世界</h2><p>每个世界选择一个自己的玩家身份；世界事件按此身份的已知范围显示。</p></div>
        {!world ? <p className="inline-hint">先在书架中创建世界。</p> : <>
          {players.length > 0 ? <div className="identity-row"><label className="field"><span>玩家身份</span><select value={playerChoice} onChange={event => setPlayerChoice(event.target.value)}>{players.map(item => <option value={item.player_id} key={item.player_id}>{item.name}</option>)}</select></label><button type="button" className="secondary-button" disabled={busy || !playerChoice || playerChoice === selectedPlayer} onClick={() => { if (characterActivityDirty && !window.confirm("角色初始地点尚未确认，是否放弃本次设置并切换身份？")) return; void act(async () => { await client.bindPlayer(world.world_id, playerChoice); const [available, selected] = await loadIdentity(world.world_id); setPlayers(available); setSelectedPlayer(selected.player_id); setSelectedPlayerState(selected); setPlayerChoice(selected.player_id ?? available[0]?.player_id ?? ""); }, "当前世界的玩家身份已更新。"); }}>设为我的身份</button></div> : null}
          {!selectedPlayer ? <div className="identity-start"><p className="inline-hint">进入世界后，你会从“家”开始。聊天消息可以跨地点发送，不会改变你的物理位置。</p><button type="button" className="primary-button" disabled={busy} onClick={() => void act(async () => { await client.startAtHome(world.world_id); const [available, selected] = await loadIdentity(world.world_id); setPlayers(available); setSelectedPlayer(selected.player_id); setSelectedPlayerState(selected); setPlayerChoice(selected.player_id ?? available[0]?.player_id ?? ""); }, "已进入世界，当前位置：家。")}>{players.length > 0 ? "继续从家进入" : "进入世界"}</button></div> : null}
        </>}
        {selectedPlayer ? <p className="inline-hint">已绑定：{players.find(item => item.player_id === selectedPlayer)?.name ?? "当前玩家"}</p> : null}
      </section>{world && <ProfileEditor key={world.world_id} client={client} worldId={world.world_id} onDirtyChange={setWorldProfileDirty} />}</div>}
    </main>
    <nav className="bottom-nav" aria-label="主导航">{tabs.map(item => <button key={item.id} type="button" className={tab === item.id ? "nav-item active" : "nav-item"} aria-current={tab === item.id ? "page" : undefined} onClick={() => { if (tab !== item.id && chatDirty && !window.confirm("当前会话有未发送的草稿或正在处理的请求，是否离开会话？已发起的生成可能继续。")) return; setTab(item.id); }}><TabIcon name={item.id} /><span>{item.label}{item.id === "chats" && unread.hasUnread && <span className="unread-dot" role="img" aria-label="有未读角色消息" />}</span></button>)}</nav>
  </div>;
}
