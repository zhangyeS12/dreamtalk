import { useWorldIdentity } from "./useWorldIdentity";
import { useWorldEvents } from "./useWorldEvents";
import { useWorkspaceActions } from "./useWorkspaceActions";
import { useDesktopPresence } from "./useDesktopPresence";
import { useWorkspaceWorld } from "./useWorkspaceWorld";
import { useWorkspaceNavigation, type WorkspaceTab as Tab } from "./useWorkspaceNavigation";
import { useWorkspaceDrafts } from "./useWorkspaceDrafts";
import { useConversationDirectory } from "./useConversationDirectory";
import { DesktopUpdateEntry, useDesktopUpdateBlock } from "./DesktopUpdates";
import { SaveBackupPanel } from "./SaveBackups";
import { BackgroundSettings, type DesktopStatus } from "./BackgroundSettings";
import { OfflineContactSettings } from "./OfflineContactSettings";
import { useOfflineContact } from "./useOfflineContact";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { CoreClient, type PlayerAvailability, } from "@dreamtalk/api-client";
import { useChatUnread } from "./useChatUnread";
import { ProactiveContactSettings } from "./ProactiveContactSettings";
import { ChatMediaSettingsPanel } from "./ChatMedia";
import { ChatTranscript } from "./ChatTranscript";
import { SpeechProvider } from "./SpeechPlayback";
import { SpeechSettings } from "./SpeechSettings";
import { GroupChatDetails, GroupChatSetup } from "./GroupChat";
import { ModelSetup, type ModelSetupSummary } from "./ModelSetup";
import { WorldImports, WorldContacts } from "./WorldContent";
import { WorldEventJournal } from "./WorldEventJournal";
import { WorldNewsSettings } from "./WorldNewsSettings";
import { WorldActivities } from "./WorldActivities";
import type { BackgroundDestination } from "./BackgroundTaskFeedback";
import { ProfileEditor } from "./ProfileEditor";
import { WorldArchivePage } from "./WorldArchivePage";
import { Brand } from "./Brand";
import { SettingsHandbook, SettingsFold } from "./SettingsHandbook";
import { SettingsDiagnostics } from "./SettingsDiagnostics";
import { ContactAvatar } from "./ContactSocial";
import { useChatAvatars } from "./useChatAvatars";
import { CelestialEmpty, DirectorySearch, WorkspaceIcon } from "./WorkspacePrimitives";
import "./product.css";
import "./world-terminal.css";

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
  return <>{entered ? <WorldWorkspace key={entered.worldId} client={client} initialWorldId={entered.worldId}
    initialTab={entered.hasIdentity ? "chats" : "me"} onArchive={() => { setPreviewId(entered.worldId); setEntered(null); }} />
    : <WorldArchivePage client={client} initialWorldId={previewId} displayTime={displayTime} onStartupStatus={onStartupStatus}
      onEnter={(worldId, hasIdentity) => setEntered({ worldId, hasIdentity })} />}</>;
}

function WorldWorkspace({ client, initialWorldId, initialTab, onArchive }: {
  client: CoreClient; initialWorldId: string; initialTab: Tab; onArchive: () => void;
}) {
  return <SpeechProvider client={client} worldId={initialWorldId}><WorldWorkspaceContent client={client} initialWorldId={initialWorldId} initialTab={initialTab} onArchive={onArchive} /></SpeechProvider>;
}

function WorldWorkspaceContent({ client, initialWorldId, initialTab, onArchive }: {
  client: CoreClient; initialWorldId: string; initialTab: Tab; onArchive: () => void;
}) {
  const { tab, setTab, meVisited, contactsVisited, settingsPage, setSettingsPage } = useWorkspaceNavigation(initialTab);
  const { dirty, onDirty, hasDrafts } = useWorkspaceDrafts();
  const { busy, error, notice, setError, setNotice, run } = useWorkspaceActions();
  const worldId = initialWorldId;
  const { world, scale, setScale, refresh } = useWorkspaceWorld(client, worldId, setError);
  const identity = useWorldIdentity(client, worldId, setError);
  const { players, selectedPlayer, selectedPlayerState, playerChoice, setPlayerChoice } = identity;
  const events = useWorldEvents(client, worldId, selectedPlayer, setError, displayTime);
  const { eventsOpen, setEventsOpen, topicEvent, setTopicEvent, visibleEvents, suggestedFor, clearSuggestion } = events;
  useDesktopPresence(worldId, selectedPlayer);
  const entryHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { entryHeading.current?.focus(); }, []);
  const [contactsManagementOpen, setContactsManagementOpen] = useState(false);
  const [contactsRefresh, setContactsRefresh] = useState(0);
  const contactsManager = useRef<HTMLElement>(null);
  const [desktopStatus, setDesktopStatus] = useState<DesktopStatus | null>(null);
  const [modelSummary, setModelSummary] = useState<ModelSetupSummary | null>(null);
  const [tokenCeiling, setTokenCeiling] = useState(savedTokenCeiling);
  const [tokenCeilingInput, setTokenCeilingInput] = useState(() => String(savedTokenCeiling()));
  const offlineContact = useOfflineContact(client, worldId, selectedPlayer);
  const unread = useChatUnread(client, worldId, selectedPlayer);
  const unreadDirectoryKey = unread.value?.items.map(item => item.conversation_id).join(":") ?? "";
  const directory = useConversationDirectory(client, worldId, selectedPlayer, tab === "chats", contactsRefresh, unreadDirectoryKey, setError);
  const { conversations, groups, selectedConversationId, selectedGroupId, groupSetupOpen, conversationsLoading, conversationsFailed, conversationSearch } = directory;
  const tokenCeilingValid = Number.isSafeInteger(Number(tokenCeilingInput)) && Number(tokenCeilingInput) >= 1;

  useEffect(() => {
    if (!world) return;
    try { window.localStorage.setItem(LAST_WORLD_KEY, world.world_id); }
    catch { /* The current world remains selected for this session. */ }
  }, [world?.world_id]);
  const openContactsManager = () => { setContactsManagementOpen(true); window.requestAnimationFrame(() => { contactsManager.current?.scrollIntoView({ block: "start" }); contactsManager.current?.focus({ preventScroll: true }); }); };
  const act = async (action: () => Promise<unknown>, success: string) => {
    await run(async () => { await action(); await refresh(); }, success);
  };
  const openChat = async (importId: string) => {
    if (!world || !selectedPlayer || busy) return;
    await run(async () => {
      const conversation = await client.openDirectConversation(world.world_id, importId);
      directory.opened({ worldId: world.world_id, playerId: selectedPlayer }, conversation);
      setEventsOpen(false); setTab("chats");
    }, "", "会话未能打开，请稍后重试。");
  };

  const title = tabs.find(item => item.id === tab)?.label ?? "聊天";
  const directoryQuery = conversationSearch.trim().toLocaleLowerCase();
  const matchingConversations = conversations.filter(item => item.character_name.toLocaleLowerCase().includes(directoryQuery));
  const matchingGroups = groups.filter(item => item.participants.some(person => person.character_name.toLocaleLowerCase().includes(directoryQuery)));
  const chatAvatars = useChatAvatars(client, worldId, [...conversations.map(item => item.root_import_id), ...groups.flatMap(item => item.participants.map(person => person.root_import_id))], tab === "chats");
  const pageHint = { chats: "与角色交流，收集世界的片段", contacts: "角色档案、所属阵营与相识关系", settings: "让这个世界按照你的节奏运行", me: "你在这里的称呼与身份" }[tab];
  const selectedConversation = conversations.find(item => item.conversation_id === selectedConversationId);
  const selectedGroup = groups.find(item => item.conversation_id === selectedGroupId);
  const discussEvent = (conversationId: string, kind: "direct" | "group") => {
    if (events.discuss(conversationId)) directory.select(kind, conversationId);
  };
  const openChatModelSettings = () => {
    if (dirty.chat && !window.confirm("当前会话有未发送的草稿，是否离开并打开模型设置？")) return;
    setSettingsPage("model"); setTab("settings");
  };
  useDesktopUpdateBlock(hasDrafts || Number(tokenCeilingInput) !== tokenCeiling
    ? "当前世界有未保存的编辑或聊天草稿。" : busy || offlineContact.busy ? "当前请求正在处理。" : null);
  const returnArchive = () => {
    if ((hasDrafts || offlineContact.busy || Number(tokenCeilingInput) !== tokenCeiling || busy)
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
  return <div className={`product-shell world-workspace world-tab-${tab}${contactsManagementOpen ? " contacts-editing" : ""}`}>
    <header className="app-header"><Brand /><span role="status" className="sr-only">核心已就绪</span><div className="workspace-world"><WorkspaceIcon name="orbit" /><div><strong>{world?.name ?? "正在读取世界…"}</strong>{world && <span>{displayTime(world.world_time)}<span className="world-clock-state">{world.clock_state === "paused" ? " · 已暂停" : ""}{world.runtime_state === "degraded" ? " · 运行异常" : ""}</span></span>}</div></div><button type="button" className="text-action archive-return" onClick={returnArchive}><WorkspaceIcon name="book" /><span>世界书架</span></button></header>
    <main className="app-content" id="main-content">
      <div className={`page-heading${tab === "chats" || tab === "contacts" ? " chat-page-heading" : ""}`}><div><h1 ref={entryHeading} tabIndex={-1}>{title}</h1><p>{pageHint}</p></div>{world ? <span className="page-world"><WorkspaceIcon name="orbit" />{world.name}</span> : null}</div>
      {error ? <p className="app-alert" role="alert">{error}</p> : null}
      {notice ? <p className="app-notice" role="status">{notice}</p> : null}

      {tab === "chats" && <div className={`chat-workspace ${eventsOpen || selectedConversation || selectedGroup || groupSetupOpen ? "thread-open" : ""}`}>
        <aside className="conversation-list" aria-label="会话列表">
        <div className="directory-heading"><div><strong>聊天</strong><small>{conversationsLoading ? "读取中" : conversationsFailed ? "读取未完成" : `${conversations.length + groups.length} 个会话`}</small></div>{selectedPlayer && <button type="button" className="directory-add" aria-label="新建群聊" title="新建群聊" onClick={() => { directory.beginGroup(); setEventsOpen(false); }}><WorkspaceIcon name="plus" /></button>}</div>
        <DirectorySearch label="搜索角色或群聊成员" value={conversationSearch} onChange={directory.search} />
        <button className={`conversation-row pinned ${eventsOpen ? "selected" : ""}`} aria-pressed={eventsOpen} type="button" onClick={() => { setTopicEvent(null); setEventsOpen(true); }}>
          <span className="avatar event-avatar" aria-hidden="true"><WorkspaceIcon name="orbit" /></span>
          <span className="row-copy"><strong>世界事件</strong><small>你已获知的事件</small></span>
          <span className="pin-label">置顶</span>
        </button>
        <div className="directory-section-label">会话列表</div>
        {unread.error && <div className="thread-hint" role="status">新消息提示暂未更新。<button type="button" className="text-action" onClick={unread.refresh}>重新读取消息提示</button></div>}
        {conversationsFailed && <div className="thread-hint" role="alert"><p>会话读取未完成，已读取的会话仍保留。</p><button type="button" className="text-action" disabled={conversationsLoading} onClick={() => directory.refresh()}>重新读取会话</button></div>}
        {conversationsLoading && conversations.length === 0 && groups.length === 0 ? <p className="thread-hint">正在读取会话…</p> : conversationsFailed && conversations.length === 0 && groups.length === 0 ? null : conversations.length === 0 && groups.length === 0 ? <div className="empty-state"><h2>还没有会话</h2><p>在通讯录中选择角色，打开与他的会话。</p><button type="button" className="text-action" onClick={() => setTab("contacts")}>前往通讯录</button></div> : <>
          {matchingGroups.map(item => <button key={item.conversation_id} type="button" className={`conversation-row ${!eventsOpen && selectedGroupId === item.conversation_id ? "selected" : ""}`} aria-pressed={!eventsOpen && selectedGroupId === item.conversation_id} onClick={() => { clearSuggestion(); directory.select("group", item.conversation_id); setEventsOpen(false); }}><span className="avatar group-avatar" aria-hidden="true"><WorkspaceIcon name="people" /></span><span className="row-copy"><strong>{item.participants.map(member => member.character_name).join("、")}{unread.unread(item.conversation_id) && <span className="unread-dot" role="img" aria-label="有未读角色消息" />}</strong><small>群聊 · {item.participants.length} 位角色</small></span></button>)}
          {matchingConversations.map(item => <button key={item.conversation_id} type="button" className={`conversation-row ${!eventsOpen && selectedConversationId === item.conversation_id ? "selected" : ""}`} aria-pressed={!eventsOpen && selectedConversationId === item.conversation_id} onClick={() => { clearSuggestion(); directory.select("direct", item.conversation_id); setEventsOpen(false); }}><ContactAvatar name={item.character_name} url={chatAvatars[item.root_import_id]} /><span className="row-copy"><strong>{item.character_name}{unread.unread(item.conversation_id) && <span className="unread-dot" role="img" aria-label="有未读角色消息" />}</strong><small>{unread.unread(item.conversation_id) ? "新消息" : "私聊"}</small></span></button>)}
        </>}

        {directoryQuery && conversations.length + groups.length > 0 && matchingConversations.length + matchingGroups.length === 0 && <p className="thread-hint" role="status">没有匹配的会话。试试角色的名字。</p>}
        </aside>
        <div className="conversation-detail">
          {eventsOpen ? <section className="event-thread" aria-label="世界事件时间线">
        <div className="thread-heading"><button type="button" className="text-action" onClick={() => setEventsOpen(false)}>返回聊天</button><h2>世界事件</h2><span>聊天获知与世界动态</span></div>
        {topicEvent ? <div className="event-topic-picker"><strong>聊聊「{topicEvent.title}」</strong><p>选择已有会话，系统只填写一条可编辑的消息，不会自动发送。</p>{conversations.length === 0 && groups.length === 0 ? <p>先从通讯录打开一位角色的会话。</p> : <div className="event-topic-choices">{conversations.map(item => <button type="button" key={item.conversation_id} onClick={() => discussEvent(item.conversation_id, "direct")}>{item.character_name}</button>)}{groups.map(item => <button type="button" key={item.conversation_id} onClick={() => discussEvent(item.conversation_id, "group")}>群聊：{item.participants.map(member => member.character_name).join("、")}</button>)}</div>}</div> : null}
        {!world ? <p className="thread-hint">先创建世界，才能查看事件。</p> : !selectedPlayer ? <div className="thread-empty"><p>先进入当前世界，才能查看你获知的事件。</p><button type="button" className="text-action" onClick={() => { setEventsOpen(false); setTab("me"); }}>前往我的身份</button></div> : <WorldEventJournal key={`journal:${worldId}:${selectedPlayer}`} client={client} worldId={worldId} witnessed={visibleEvents} onTopic={setTopicEvent} displayTime={displayTime} />}
          </section> : groupSetupOpen ? <GroupChatSetup key={`${worldId}:${selectedPlayer}`} client={client} worldId={worldId} onBack={directory.closeGroup} onDirtyChange={onDirty.chat} onCreated={group => { directory.created({ worldId, playerId: selectedPlayer! }, group); }} /> : selectedGroup && selectedPlayer ? <GroupChatDetails key={`${worldId}:${selectedPlayer}:${selectedGroup.conversation_id}`} client={client} worldId={worldId} playerId={selectedPlayer} group={selectedGroup} onModelSettings={openChatModelSettings} avatarUrls={chatAvatars} onDirtyChange={onDirty.chat} tokenCeiling={tokenCeiling} suggestedDraft={suggestedFor(selectedGroup.conversation_id)} onSuggestionUsed={() => clearSuggestion()} onBack={directory.clearSelection} onDissolved={() => { directory.removed({ worldId, playerId: selectedPlayer }, selectedGroup.conversation_id); clearSuggestion(); onDirty.chat(false); }} /> : selectedConversation && selectedPlayer ? <ChatTranscript key={`${worldId}:${selectedPlayer}:${selectedConversation.conversation_id}`} client={client} worldId={worldId} playerId={selectedPlayer} conversation={selectedConversation} onModelSettings={openChatModelSettings} avatarUrl={chatAvatars[selectedConversation.root_import_id]} onDirtyChange={onDirty.chat} tokenCeiling={tokenCeiling} suggestedDraft={suggestedFor(selectedConversation.conversation_id)} onSuggestionUsed={() => clearSuggestion()} onBack={directory.clearSelection} /> : <CelestialEmpty title="每次相逢，都从一句话开始" action={<button type="button" className="secondary-button" onClick={() => setTab("contacts")}>寻找一位角色<WorkspaceIcon name="arrow" /></button>}>选择左侧的会话，继续你们的故事。<br />也可以打开世界事件，看看已经获知的片段。</CelestialEmpty>}
        </div>
      </div>}

      {(tab === "contacts" || contactsVisited) && <div className="contacts-page" hidden={tab !== "contacts"}>
        {world ? <>
          <details className="contacts-management" open={contactsManagementOpen} onToggle={event => setContactsManagementOpen(event.currentTarget.open)}>
            <summary ref={contactsManager}><strong>添加／编辑角色卡</strong>{dirty.worldContent && <span>有未保存的编辑 · 草稿保留中</span>}</summary>
            <WorldImports key={`content:${world.world_id}`} client={client} worldId={world.world_id} onlyKind="character" refreshKey={contactsRefresh} onDirtyChange={onDirty.worldContent} onSaved={() => setContactsRefresh(value => value + 1)} />
          </details>
          <WorldContacts key={world.world_id} client={client} worldId={world.world_id} refreshKey={contactsRefresh} visible={tab === "contacts"} onSettings={openContactsManager} onIdentity={() => setTab("me")} onOpenChat={openChat} canOpenChat={!!selectedPlayer} openingChat={busy} identityKey={selectedPlayer} onLocationDirty={onDirty.worldLocations} onCharacterLocationDirty={onDirty.characterActivity} onRemoved={() => setContactsRefresh(value => value + 1)} removalDisabled={dirty.worldContent} />
        </> : <div className="page-section"><div className="empty-state"><h2>先创建一个世界</h2><p>在世界档案库创建世界，然后新建或导入角色卡。</p><button className="text-action" onClick={returnArchive}>前往世界档案库</button></div></div>}
      </div>}

      <SettingsHandbook client={client} world={world} visible={tab === "settings"} page={settingsPage} onPage={setSettingsPage} onArchive={returnArchive}
        dirtyPages={{ model: dirty.model || Number(tokenCeilingInput) !== tokenCeiling, speech: dirty.speech, media: dirty.media, background: dirty.background, activities: false }}
        panels={{
          backups: <SaveBackupPanel />,
          media: <ChatMediaSettingsPanel key={`media:${worldId}`} client={client} worldId={worldId} onDirtyChange={onDirty.media} />,
          speech: <SpeechSettings client={client} worldId={worldId} onDirtyChange={onDirty.speech} />,
          model: <>
            <SettingsFold title="模型服务与回复" summary={modelSummary?.model ? `${modelSummary.model} · 单次回复上限 ${modelSummary.replyTokens?.toLocaleString("zh-CN") ?? "待核对"} Token` : modelSummary?.status === "unconfigured" ? "尚未配置，展开完成首次设置" : modelSummary?.status ? "已读取配置状态，展开查看模型设置" : "正在读取模型配置…"} open>
              <ModelSetup key={worldId} client={client} worldId={worldId} turnTokenCeiling={tokenCeiling} onApplyTokenCeiling={next => { setTokenCeiling(next); setTokenCeilingInput(String(next)); try { window.localStorage.setItem(TOKEN_CEILING_KEY, String(next)); } catch { /* Keep the explicit setting for this session. */ } setNotice("聊天额度已更新；没有发起模型请求。"); }} onDirtyChange={onDirty.model} onSummaryChange={setModelSummary} />
            </SettingsFold>
            <SettingsFold title="聊天额度" summary={`已应用 ${tokenCeiling.toLocaleString("zh-CN")} Token / 轮${Number(tokenCeilingInput) !== tokenCeiling ? " · 新数值尚未应用" : ""}`}>
              <section className="settings-section"><div className="section-heading"><h2>聊天额度</h2><p>每轮输入和输出共用上限。系统按可信上界预留，额度不足时不会开始下一次模型调用。</p></div>
          <div className="setting-row"><label className="field"><span>每轮 Token 上限</span><input type="number" min="1" max={Number.MAX_SAFE_INTEGER} step="1" value={tokenCeilingInput} onChange={event => setTokenCeilingInput(event.target.value)} /></label><button type="button" className="secondary-button" disabled={!tokenCeilingValid} onClick={() => { const next = Number(tokenCeilingInput); setTokenCeiling(next); try { window.localStorage.setItem(TOKEN_CEILING_KEY, String(next)); } catch { /* Session setting remains active. */ } setNotice("聊天额度已更新。"); }}>应用</button></div>
          {!tokenCeilingValid ? <p className="app-alert" role="alert">请输入 1 至 {Number.MAX_SAFE_INTEGER.toLocaleString("zh-CN")} 之间的整数聊天额度。</p> : null}
          <p className="inline-hint" role="status">当前已应用的聊天额度：{tokenCeiling.toLocaleString("zh-CN")} Token。{Number(tokenCeilingInput) !== tokenCeiling ? "输入的新数值尚未应用，请点击应用。" : "该额度仅用于聊天，不限制角色卡或世界书生成；额度是预留上限，实际费用以提供商报告的用量为准。"}</p>
        </section>
            </SettingsFold>
          </>,
          background: <BackgroundSettings onStatusChange={setDesktopStatus} onDirtyChange={onDirty.background} />,
          time: <>{world && <section className="settings-section"><div className="section-heading"><h2>世界时间</h2><p>{displayTime(world.world_time)}</p></div>
          <div className="setting-row"><span><strong>时间状态</strong><small>{world.clock_state === "running" ? "运行中" : "已暂停"}{world.runtime_state === "degraded" ? " · 运行异常" : ""}</small></span><button type="button" className="secondary-button" disabled={busy || world.runtime_state === "degraded"} onClick={() => void act(() => world.clock_state === "running" ? client.pauseProductWorld(world.world_id) : client.resumeProductWorld(world.world_id), world.clock_state === "running" ? "世界已暂停。" : "世界已恢复。")}>{world.clock_state === "running" ? "暂停" : "恢复"}</button></div>
          <div className="setting-row"><label className="field"><span>时间倍率</span><input type="number" min="0.01" max="1000" step="0.01" inputMode="decimal" value={scale} onChange={event => setScale(event.target.value)} /></label><button type="button" className="secondary-button" disabled={busy || !scale || Number(scale) <= 0 || Number(scale) > 1000} onClick={() => void act(() => client.scaleProductWorld(world.world_id, scale), "时间倍率已更新。")}>应用</button></div>
        </section>}</>,
          activities: <><section className="settings-section"><div className="section-heading"><h2>地点与初始位置</h2><p>已移到通讯录。在角色资料中设置初始地点与锁定，添加／编辑地点可调整包含关系和隐藏分支。</p></div><button className="secondary-button" onClick={() => setTab("contacts")}>前往通讯录</button></section>{world && selectedPlayer && <WorldActivities key={`activities:${world.world_id}:${selectedPlayer}`} client={client} worldId={world.world_id} visible={tab === "settings" && settingsPage === "activities"} paused={world.clock_state === "paused"} onNavigate={navigateBackgroundTask} />}{!selectedPlayer && <section className="settings-section"><p className="inline-hint">先在“我”中进入世界，再设置角色活动。</p><button type="button" className="text-action" onClick={() => setTab("me")}>前往我</button></section>}</>,
          offline: <>{world && selectedPlayer && selectedPlayerState?.availability && selectedPlayerState.presence_revision !== null && <section className="settings-section"><div className="section-heading"><h2>交流状态</h2><p>忙碌状态不会暂停世界运行，已开启的离线联系会跳过普通主动消息；设为可用不会立即补发。</p></div>
          <div className="setting-row"><span><strong>{selectedPlayerState.availability === "available" ? "可用" : "忙碌"}</strong><small>仅适用于当前世界绑定的玩家身份</small></span><button type="button" className="secondary-button" disabled={busy} onClick={() => {
            const next: PlayerAvailability = selectedPlayerState.availability === "available" ? "busy" : "available";
            void act(async () => {
              await identity.availability(next, selectedPlayerState.presence_revision!, selectedPlayer!);
            }, next === "available" ? "当前状态已设为可用。" : "当前状态已设为忙碌。");
          }}>{selectedPlayerState.availability === "available" ? "设为忙碌" : "设为可用"}</button></div>
        </section>} {world && selectedPlayer && <><ProactiveContactSettings key={`proactive:${world.world_id}:${selectedPlayer}`} client={client} worldId={world.world_id} playerId={selectedPlayer} /><OfflineContactSettings key={`offline:${world.world_id}:${selectedPlayer}`} status={offlineContact.status} busy={offlineContact.busy} refreshing={offlineContact.refreshing} error={offlineContact.error} onRefresh={offlineContact.refresh} onSave={offlineContact.save} paused={world.clock_state === "paused"} availability={selectedPlayerState?.availability ?? null} onNavigate={navigateBackgroundTask} /></>}{!selectedPlayer && <section className="settings-section"><p className="inline-hint">先在“我”中进入当前世界，再设置离线联系。</p><button type="button" className="text-action" onClick={() => setTab("me")}>前往我</button></section>}</>,
          news: <>{world && selectedPlayer && <WorldNewsSettings key={`news:${world.world_id}:${selectedPlayer}`} client={client} worldId={world.world_id} visible={tab === "settings" && settingsPage === "news"} paused={world.clock_state === "paused"} onNavigate={navigateBackgroundTask} />}{!selectedPlayer && <section className="settings-section"><p className="inline-hint">先在“我”中进入当前世界，再设置世界动态。</p><button type="button" className="text-action" onClick={() => setTab("me")}>前往我</button></section>}</>,
          about: <><DesktopUpdateEntry settings /><SettingsDiagnostics key={worldId} client={client} worldId={worldId} visible={tab === "settings" && settingsPage === "about"} desktop={desktopStatus} onBackground={() => setSettingsPage("background")} /></>,
        }} />

      {(tab === "me" || meVisited) && <div className="settings-page profile-page" hidden={tab !== "me"}><ProfileEditor client={client} onDirtyChange={onDirty.generalProfile} /><section className="settings-section"><div className="section-heading"><h2>我在当前世界</h2><p>每个世界选择一个自己的玩家身份；世界事件按此身份的已知范围显示。</p></div>
        {!world ? <p className="inline-hint">先在书架中创建世界。</p> : <>
          {players.length > 0 ? <div className="identity-row"><label className="field"><span>玩家身份</span><select value={playerChoice} onChange={event => setPlayerChoice(event.target.value)}>{players.map(item => <option value={item.player_id} key={item.player_id}>{item.name}</option>)}</select></label><button type="button" className="secondary-button" disabled={busy || !playerChoice || playerChoice === selectedPlayer} onClick={() => { if (dirty.characterActivity && !window.confirm("角色位置规则尚未确认，是否放弃本次设置并切换身份？")) return; void act(async () => { await identity.bind(playerChoice); }, "当前世界的玩家身份已更新。"); }}>设为我的身份</button></div> : null}
          {!selectedPlayer ? <div className="identity-start"><p className="inline-hint">进入世界后，你会从“家”开始。聊天消息可以跨地点发送，不会改变你的物理位置。</p><button type="button" className="primary-button" disabled={busy} onClick={() => void act(async () => { await identity.startAtHome(); }, "已进入世界，当前位置：家。")}>{players.length > 0 ? "继续从家进入" : "进入世界"}</button></div> : null}
        </>}
        {selectedPlayer ? <p className="inline-hint">已绑定：{players.find(item => item.player_id === selectedPlayer)?.name ?? "当前玩家"}</p> : null}
      </section>{world && <ProfileEditor key={world.world_id} client={client} worldId={world.world_id} onDirtyChange={onDirty.worldProfile} />}</div>}
    </main>
    <nav className="bottom-nav" aria-label="主导航">{tabs.map(item => <button key={item.id} type="button" className={tab === item.id ? "nav-item active" : "nav-item"} aria-current={tab === item.id ? "page" : undefined} onClick={() => { if (tab !== item.id && dirty.chat && !window.confirm("当前会话有未发送的草稿或正在处理的请求，是否离开会话？已发起的生成可能继续。")) return; setTab(item.id); }}><TabIcon name={item.id} /><span>{item.label}{item.id === "chats" && unread.hasUnread && <span className="unread-dot" role="img" aria-label="有未读角色消息" />}</span></button>)}</nav>
  </div>;
}
