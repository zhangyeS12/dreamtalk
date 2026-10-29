import { DesktopUpdateEntry, useDesktopUpdateBlock } from "./DesktopUpdates";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type ReactNode, type Ref } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { CoreClient, CoreRequestError, type WorldSettings, type WorldContentItem } from "@dreamtalk/api-client";
import { ModelSetup } from "./ModelSetup";
import { WorldImports } from "./WorldContent";
import { WorldShelf, worldShelfBlankCount } from "./WorldShelf";
import { useWorldCovers } from "./useWorldCovers";
import { SaveBackupPanel } from "./SaveBackups";
import { ExampleWorldPanel } from "./ExampleWorldPanel";
import { ArchiveRoom, archiveSky } from "./world/archive/ArchiveRoom";
import { BookDesigner } from "./world/archive/BookDesigner";
import { FaceArt, type ShelfAppearance } from "./world/archive/Book3D";
import type { ShelfFace } from "./world/archive/bookDesign";
import { bookLook, shelfAppearance } from "./world/archive/bookLook";
import { useWindowStill } from "./world/useWindowStill";
import { trapTab } from "./world/focusTrap";
import { formatClock, skyAt, worldClock } from "./world/sky";
import styles from "./world/archive/Archive.module.css";
const NIGHT = skyAt(0);
import "./world/tokens.css";
import "./world/theme.css";

export function WorldArchivePage({ client, initialWorldId, onEnter, displayTime, onStartupStatus }: {
  client: CoreClient; initialWorldId: string | null;
  onEnter: (id: string, hasIdentity: boolean) => void; displayTime: (raw: string) => string;
  onStartupStatus?: (ready: boolean) => void;
}) {
  const covers = useWorldCovers(client);
  const [designing, setDesigning] = useState(false);
  const [designDraft, setDesignDraft] = useState<ShelfAppearance | null>(null);
  const [shelfFace, setShelfFace] = useState<ShelfFace>("front");
  const [faceRequest, setFaceRequest] = useState<{ face: ShelfFace; nonce: number } | undefined>(undefined);
  const [travelling, setTravelling] = useState<WorldSettings | null>(null);
  const [skyWorldId, setSkyWorldId] = useState<string | null>(initialWorldId);
  const [coverDirty, setCoverDirty] = useState(false);
  const [coverBusy, setCoverBusy] = useState(false);
  const coverBusyRef = useRef(false);
  const coverWorking = useCallback((value: boolean) => { coverBusyRef.current = value; setCoverBusy(value); }, []);
  const [worlds, setWorlds] = useState<WorldSettings[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [blankIndex, setBlankIndex] = useState<number | null>(null);
  const [vacatedIndex, setVacatedIndex] = useState<number | null>(null);
  const [readyKey, setReadyKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [startupFailed, setStartupFailed] = useState(false);
  const startupReported = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(() => {
    try { const message = window.sessionStorage.getItem("livingworld.worldDeletionNotice") || ""; window.sessionStorage.removeItem("livingworld.worldDeletionNotice"); return message; } catch { return ""; }
  });
  const [deletionCleanup, setDeletionCleanup] = useState<{ world_id: string; name: string; erased?: boolean } | null>(() => {
    try {
      const value = JSON.parse(window.localStorage.getItem("livingworld.pendingWorldDeletion") || "null");
      return value && typeof value.world_id === "string" && /^[0-9a-f-]{36}$/i.test(value.world_id) && typeof value.name === "string" && value.name.length <= 120 ? value : null;
    } catch { return null; }
  });
  useEffect(() => {
    try { if (deletionCleanup) window.localStorage.setItem("livingworld.pendingWorldDeletion", JSON.stringify(deletionCleanup)); else window.localStorage.removeItem("livingworld.pendingWorldDeletion"); } catch { /* Optional retry hint; server receipts remain authoritative. */ }
  }, [deletionCleanup]);
  const [creating, setCreating] = useState(false);
  const [createIntent, setCreateIntent] = useState<"create" | "import">("create");
  const [name, setName] = useState("");
  const [pendingCreation, setPendingCreation] = useState(false);
  const [busy, setBusy] = useState(false);
  const [entering, setEntering] = useState(false);
  const [managing, setManaging] = useState(false);
  const [contentDirty, setContentDirty] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [backupsOpen, setBackupsOpen] = useState(false);
  const [exampleOpen, setExampleOpen] = useState(false);
  const [modelDirty, setModelDirty] = useState(false);
  const [content, setContent] = useState<{ worldId: string; items: WorldContentItem[] } | null>(null);
  const [contentError, setContentError] = useState("");
  const [contentRevision, setContentRevision] = useState(0);
  const active = useRef(true);
  const request = useRef<{ name: string; id: string } | null>(null);
  const lock = useRef(false);
  const creatorInput = useRef<HTMLInputElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const layout = useRef<HTMLDivElement>(null);
  const managerHeading = useRef<HTMLHeadingElement>(null);
  const selectionKey = selectedId ? `world:${selectedId}` : blankIndex !== null ? `blank:${blankIndex}` : null;
  const selectionRef = useRef(selectionKey);
  selectionRef.current = selectionKey;
  const previewReady = selectionKey !== null && readyKey === selectionKey;
  const world = worlds.find(item => item.world_id === selectedId);
  const items = content?.worldId === selectedId ? content.items : null;
  const books = items?.filter(item => item.kind === "lorebook");
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const result = await client.listProductWorlds(signal);
    if (!active.current || signal?.aborted) return result;
    setWorlds(result);
    setBlankIndex(current => current === null ? null : Math.min(current, worldShelfBlankCount(result.length) - 1));
    // Remembered world positions never imply an active selection.
    setSelectedId(current => current && !result.some(item => item.world_id === current) ? "" : current);
    return result;
  }, [client]);
  const exampleBusy = useCallback((value: boolean) => { lock.current = value; setBusy(value); }, []);
  const exampleCreated = async (id: string) => {
    const directory = await refresh();
    if (!active.current) return;
    if (!directory.some(item => item.world_id === id)) throw new Error("example_not_readable");
    setExampleOpen(false); setCreating(false); setBlankIndex(null); setReadyKey(null);
    setSelectedId(id); setNotice("校园示例已准备好。进入世界后，可在通讯录选择三位同学聊天。");
  };
  useEffect(() => {
    active.current = true;
    let initialActive = true;
    const initialRequest = new AbortController();
    void refresh(initialRequest.signal).catch(() => { if (initialActive) { setStartupFailed(true); setError("世界档案未能读取。请检查核心连接后刷新。"); } })
      .finally(() => { if (initialActive) setLoading(false); });
    const timer = window.setInterval(() => {
      if (!lock.current && !coverBusyRef.current) void refresh().catch(() => { if (active.current) setError("世界状态暂时无法刷新。已有草稿仍保留。"); });
    }, 15000);
    return () => { initialActive = false; initialRequest.abort(); active.current = false; window.clearInterval(timer); };
  }, [refresh]);
  useEffect(() => {
    if (!onStartupStatus || startupReported.current || loading) return;
    // Covers are optional presentation data. The archive can open with its
    // text appearance while artwork continues loading or falls back.
    // Avoid waiting for animation frames: hidden autostart windows may not
    // receive them at all.
    startupReported.current = true; onStartupStatus(!startupFailed);
  }, [onStartupStatus, loading, startupFailed]);
  useEffect(() => {
    if (!isTauri()) return;
    const report = () => void invoke("report_desktop_presence", { worldId: null, visible: false }).catch(() => undefined);
    report();
    const timer = window.setInterval(report, 10000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { if (creating && previewReady) creatorInput.current?.focus(); }, [creating, previewReady]);
  useEffect(() => {
    if (managing && previewReady) { managerHeading.current?.scrollIntoView({ block: "start" }); managerHeading.current?.focus({ preventScroll: true }); }
  }, [managing, previewReady]);
  useEffect(() => {
    let mounted = true;
    setContent(null); setContentError("");
    if (selectedId) void client.worldContent(selectedId).then(result => {
      if (mounted) setContent({ worldId: selectedId, items: result });
    }).catch(() => { if (mounted) setContentError("设定摘要暂时无法读取，可刷新后再试。"); });
    return () => { mounted = false; };
  }, [client, selectedId, contentRevision]);
  const leaveEditor = () => {
    if (lock.current || coverBusyRef.current) return false;
    if ((contentDirty || modelDirty || coverDirty || creating && name.trim() && !pendingCreation) &&
      !window.confirm("有尚未保存的编辑，是否离开当前编辑？已发起的联网生成不会自动重放。")) return false;
    setDesigning(false); setDesignDraft(null); setCoverDirty(false); setManaging(false); setModelOpen(false); setContentDirty(false); setModelDirty(false);
    return true;
  };
  const clearSelection = () => { setSelectedId(""); setBlankIndex(null); setReadyKey(null); setCreating(false); };
  const closeSelection = () => {
    if (!selectionKey || !leaveEditor()) return;
    const book = [...(layout.current?.querySelectorAll<HTMLButtonElement>("button[data-book-key]") ?? [])]
      .find(element => element.dataset.bookKey === selectionKey);
    clearSelection(); book?.focus({ preventScroll: true });
  };
  const select = (id: string) => {
    if (id === selectedId) { closeSelection(); return; }
    if (!leaveEditor()) return;
    setCreating(false); setBlankIndex(null); setReadyKey(null); setSelectedId(id); setNotice(""); setError("");
  };
  const selectBlank = (index: number) => {
    if (index === blankIndex) { closeSelection(); return; }
    if (!leaveEditor()) return;
    setCreating(false); setSelectedId(""); setReadyKey(null); setBlankIndex(index); setNotice(""); setError("");
  };
  const settled = useCallback((key: string | null) => {
    if (selectionRef.current === key) setReadyKey(key);
  }, []);
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const value = name.trim();
    if (!value || lock.current || coverBusyRef.current) return;
    lock.current = true; setBusy(true); setPendingCreation(true); setError(""); setNotice("");
    if (!request.current || request.current.name !== value) request.current = { name: value, id: crypto.randomUUID() };
    try {
      const result = await client.createWorld(value, request.current.id);
      if (!active.current) return;
      const directory = await refresh();
      if (!active.current) return;
      if (!directory.some(item => item.world_id === result.world_id)) throw new Error("archive_not_readable");
      setReadyKey(null); setBlankIndex(null); setSelectedId(result.world_id); setName(""); request.current = null; setPendingCreation(false);
      setCreating(false); setManaging(true);
      setNotice(createIntent === "import" ? "世界档案已创建。在下方选择世界书文件，预览后确认导入。" : "世界档案已创建。现在添加世界书，也可以稍后再完善。");
    } catch (failure) {
      if (!active.current) return;
      if (failure instanceof CoreRequestError && failure.status === 422) {
        request.current = null; setPendingCreation(false); setError("世界名称未通过校验，请修改名称后再创建。");
      } else setError("尚未确认创建结果。再次核对沿用同一次请求，不会重复创建。");
    }
    finally { lock.current = false; if (active.current) setBusy(false); }
  };
  const enter = async () => {
    if (!world || !leaveEditor()) return;
    lock.current = true; setEntering(true); setError("");
    try {
      const [directory, identity] = await Promise.all([client.listProductWorlds(), client.selectedPlayer(world.world_id)]);
      if (!active.current) return;
      if (!directory.some(item => item.world_id === world.world_id)) {
        setWorlds(directory); clearSelection(); setError("这个世界已不存在，请刷新书架。"); return;
      }
      const go = () => onEnter(world.world_id, Boolean(identity.player_id));
      // The book opens onto that world's sky; skipped when motion is reduced or the window is hidden.
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || document.hidden) { go(); return; }
      setTravelling(world);
      window.setTimeout(() => { if (active.current) setSkyWorldId(world.world_id); }, 650);
      await new Promise(resolve => window.setTimeout(resolve, 1700));
      if (active.current) go();
    } catch { if (active.current) setError("未能读取进入世界所需的信息。请检查核心连接后重试。"); }
    finally { lock.current = false; if (active.current) setEntering(false); }
  };
  const refreshArchive = () => {
    if (lock.current || coverBusyRef.current || loading) return;
    setLoading(true); void covers.refresh();
    void refresh().then(() => { if (active.current) { setError(""); setContentRevision(value => value + 1); } })
      .catch(() => { if (active.current) setError("世界档案仍无法读取，请检查核心连接。"); })
      .finally(() => { if (active.current) setLoading(false); });
  };
  useDesktopUpdateBlock(coverDirty || contentDirty || modelDirty || (creating && Boolean(name.trim())) ? "书架有未保存的编辑。" : busy || entering || coverBusy || pendingCreation ? "书架请求正在处理。" : null);
  const contentChanged = useCallback(() => setContentRevision(value => value + 1), []);
  const deleteWorld = async (target: { world_id: string; name: string; erased?: boolean }, retry = false) => {
    if (lock.current || coverBusyRef.current || entering) return;
    if (!retry) {
      if (!leaveEditor()) return;
      if (!window.confirm(`永久删除世界“${target.name}”？\n\n该世界的世界书、角色卡、阵营、地点、全部聊天及记忆都会删除，书位恢复为空白。\n此操作无法撤销。确定删除吗？`)) return;
    }
    lock.current = true; setBusy(true); setError(""); setNotice("");
    setDeletionCleanup(target);
    let erased = target.erased === true;
    try {
      const outcome = await client.deleteWorld(target.world_id, target.name);
      erased = true;
      const oldIndex = worlds.findIndex(item => item.world_id === target.world_id);
      if (oldIndex >= 0) setVacatedIndex(oldIndex);
      setWorlds(current => current.filter(item => item.world_id !== target.world_id));
      covers.removed(target.world_id); setContent(null); clearSelection();
      setBlankIndex(0);
      setContentDirty(false); setCoverDirty(false); setModelDirty(false);
      try {
        window.localStorage.removeItem(`dreamtalk.content-builder.${target.world_id}.character`);
        window.localStorage.removeItem(`dreamtalk.content-builder.${target.world_id}.lorebook`);
        window.sessionStorage.removeItem(`dreamtalk-model-cleanup-warning:${target.world_id}`);
        if (window.localStorage.getItem("livingworld.lastWorldId") === target.world_id) window.localStorage.removeItem("livingworld.lastWorldId"); } catch { /* Optional last selection only. */ }
      setDeletionCleanup({ ...target, erased: true });
      if (outcome.asset_cleanup_pending) throw new Error("asset_cleanup_pending");
      let reconnected = false;
      if (isTauri()) {
        await invoke("forget_speech_credentials", { worldId: target.world_id, secretRef: null });
        await invoke("forget_media_credentials", { worldId: target.world_id, secretRef: null });
        const result = await invoke<{ old_credential_cleanup_incomplete: boolean; core_restarted: boolean }>("forget_deleted_world_model", { worldId: target.world_id });
        reconnected = result.core_restarted;
        if (result.old_credential_cleanup_incomplete) {
          const message = "世界已删除，书位恢复为空白。独立模型配置已移除，但未引用的旧凭据清理失败，请检查本机凭据存储。";
          setDeletionCleanup(null); setNotice(message);
          try { window.localStorage.removeItem("livingworld.pendingWorldDeletion"); if (reconnected) window.sessionStorage.setItem("livingworld.worldDeletionNotice", message); } catch { /* Optional notice only. */ }
          if (reconnected) window.location.reload();
          return;
        }
      }
      setDeletionCleanup(null); setNotice("世界已删除，书位恢复为空白。");
      // Removing an independent model scope may replace the Core generation.
      try { window.localStorage.removeItem("livingworld.pendingWorldDeletion"); if (reconnected) window.sessionStorage.setItem("livingworld.worldDeletionNotice", "世界已删除，书位恢复为空白。"); } catch { /* Optional notice only. */ }
      if (reconnected) window.location.reload();
    } catch (failure) {
      if (erased) setError("世界内容已删除，但附属图片或独立模型配置的清理尚未完成。请点击重试清理。");
      else setError(failure instanceof CoreRequestError && failure.status === 409 ? "当前仍有请求或生成任务正在处理，暂未删除。请稍后重试。" : "删除结果未能确认，请重试删除或刷新书架核对；不会重复执行已完成的删除。");
    } finally { lock.current = false; if (active.current) setBusy(false); }
  };
  const homeWorld = worlds.find(item => item.world_id === skyWorldId) ?? worlds.find(item => item.world_id === initialWorldId);
  const sky = archiveSky(homeWorld);
  const still = useWindowStill();
  const homeClock = homeWorld ? worldClock(homeWorld.world_time) : null;
  const savedAppearances = useMemo(() => Object.fromEntries(worlds.map(item => [item.world_id, shelfAppearance(covers.appearances[item.world_id], item.name)])), [worlds, covers.appearances]);
  // While designing, only the designed book's entry changes, so the rest of the shelf does not re-render.
  const appearances = useMemo(() => selectedId && designDraft && savedAppearances[selectedId]
    ? { ...savedAppearances, [selectedId]: designDraft } : savedAppearances, [savedAppearances, selectedId, designDraft]);
  const selectedTime = world?.world_time;
  const selectedSky = useMemo(() => { if (selectedTime === undefined) return null; const clock = worldClock(selectedTime); return skyAt(clock ? clock.minuteOfDay : 0); }, [selectedTime]);
  const travelLook = travelling ? bookLook(travelling, appearances[travelling.world_id]) : null;
  const locked = busy || entering || coverBusy;
  const sheet = (title: string, note: string | undefined, onClose: () => void, children: ReactNode, headingRef?: Ref<HTMLHeadingElement>) => <>
    <div className={styles.scrim} onClick={onClose} />
    <section className={styles.sheet} role="dialog" aria-modal="true" aria-label={title} onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); onClose(); } else trapTab(event); }}>
      <header><h2 ref={headingRef} tabIndex={-1}>{title}</h2>{note && <p>{note}</p>}<button type="button" className={styles.close} aria-label="收起" onClick={onClose}>×</button></header>
      <div className={`${styles.sheetBody} dt-world world-workspace dt-sheet-body`}>{children}</div>
    </section>
  </>;

  return <div className={`product-shell dt-world ${styles.root}`} style={sky.style} data-entering={travelling ? "" : undefined} data-still={still || undefined}>
    <ArchiveRoom body={sky.body} />
    <header className={styles.hud}>
      <div className={styles.brand}><img src="/brand/dreamtalk-logo.png" alt="dreamtalk" width="40" height="36" />
        <div><h1 ref={heading} tabIndex={-1}>世界档案库</h1>
          <p>{homeWorld && homeClock ? `刚从「${homeWorld.name}」回来 · ${formatClock(homeClock)} ${skyAt(homeClock.minuteOfDay).phase}` : "挑一本书，走进其中的世界。"}</p></div></div>
      <DesktopUpdateEntry />
      <button type="button" className={styles.pill} aria-expanded={backupsOpen} disabled={locked} onClick={() => { if (backupsOpen || leaveEditor()) setBackupsOpen(value => !value); }}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h11l3 3v13H5Z" /><path d="M8 4v5h7V4M8 20v-6h8v6" /></svg>存档</button>
      <button type="button" className={styles.pill} aria-expanded={modelOpen} disabled={locked} onClick={() => { if (modelOpen) { leaveEditor(); return; } if (leaveEditor()) { clearSelection(); setModelOpen(true); } }}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></svg>模型设置</button>
      <button type="button" className={styles.pill} aria-expanded={exampleOpen} disabled={loading || locked} onClick={() => { if (leaveEditor()) setExampleOpen(current => !current); }}>体验校园示例</button>
      <button type="button" className={styles.pill} disabled={loading || locked} onClick={refreshArchive} aria-label={loading ? "正在读取…" : "刷新书架"} title="刷新书架">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 5v5h-5M4 19v-5h5M5.2 8a7.5 7.5 0 0 1 12-3L20 8M4 16l2.8 3a7.5 7.5 0 0 0 12-3" /></svg></button>
    </header>

    <main className={styles.stage}>
      <WorldShelf worlds={worlds} appearances={appearances} selectedKey={selectionKey} initialWorldId={initialWorldId} loading={loading} disabled={locked} vacatedIndex={vacatedIndex}
        onSelect={select} onCreate={selectBlank} onClose={closeSelection} onSettled={settled} designing={designing && Boolean(world) && previewReady}
        faceRequest={faceRequest} onFace={setShelfFace} />
      {previewReady && !designing && <section key={selectionKey} id="archive-preview" aria-label={blankIndex !== null ? "创建世界档案" : "所选世界预览"} aria-busy={entering}
        onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); closeSelection(); } }}>
        {blankIndex !== null ? <div className={styles.blank}>
          <button type="button" className={styles.close} aria-label="归位" disabled={busy} onClick={closeSelection}>×</button>
          {creating ? <>
            <h2>先给世界一个名字</h2><p>{createIntent === "import" ? "先创建世界档案，再选择已有世界书文件，检查并确认导入。" : "创建档案后，可以手动填写设定、联网生成，或导入世界书。"}</p>
            <form onSubmit={event => void create(event)}><label>世界名称<input ref={creatorInput} maxLength={120} value={name} disabled={busy || pendingCreation} onChange={event => setName(event.target.value)} placeholder="例如：绝区零" required /></label>
              <button type="submit" className={styles.gold} disabled={busy || !name.trim()}>{busy ? "正在创建…" : pendingCreation ? "核对上次创建结果" : createIntent === "import" ? "创建档案并导入世界书" : "创建档案并添加世界书"}</button></form>
            {pendingCreation && !busy && <small>上次创建结果待核对，名称暂时保留。点击核对沿用同一次请求。</small>}
            <button type="button" className={styles.link} style={{ marginTop: 14 }} disabled={busy} onClick={() => setCreating(false)}>返回创建选项</button>
          </> : <>
            <h2>从这本空白书开始</h2><p>给新的世界一个名字，再添加它的故事与设定。创建后，这本书会印上它自己的封面。</p>
            <div className={styles.row}><button type="button" className={styles.gold} style={{ padding: "0 24px" }} disabled={busy || loading} onClick={() => { setCreateIntent("create"); setCreating(true); }}>创建世界</button>
              <button type="button" className={styles.ghost} disabled={busy || loading} onClick={() => { setCreateIntent("import"); setCreating(true); }}>导入世界书</button></div>
            <small>空白书位只是入口。确认创建前，不会保存新世界。</small>
          </>}
        </div> : world ? <>
          <aside className={styles.tag} style={selectedSky ? { "--bz": selectedSky.zenith, "--bh": selectedSky.horizon } as CSSProperties : undefined}>
            <span className={styles.chip} />
            <h2>{world.name}</h2>
            <span className={styles.clock}>{displayTime(world.world_time)}{selectedSky ? ` · ${selectedSky.phase}` : ""}{world.clock_state === "paused" && <span className={styles.paused}>已暂停</span>}{world.runtime_state === "degraded" && <span className={styles.paused}>运行需要处理</span>}</span>
            <p className={styles.books}>{contentError ? <>{contentError} <button type="button" onClick={contentChanged}>刷新摘要</button></>
              : !books ? <span role="status">正在读取世界设定…</span>
              : books.length ? `世界书：${books.slice(0, 3).map(item => item.lorebooks[0]?.name ?? "世界书").join("、")}${books.length > 3 ? ` 等 ${books.length} 份` : ""}`
              : "尚未添加世界书。可以先导入设定，也可以进入世界后继续完善。"}</p>
          </aside>
          <nav className={styles.actions} aria-label="世界操作">
            <button type="button" className={styles.enter} disabled={locked || loading} onClick={() => void enter()}>{entering ? "正在读取世界…" : "进入世界 →"}</button>
            <button type="button" disabled={locked} onClick={() => { if (leaveEditor()) setDesigning(true); }}>设计这本书</button>
            <button type="button" disabled={locked} onClick={() => { if (leaveEditor()) setManaging(true); }}>管理 / 导入世界书</button>
            <span className={styles.sep} />
            <button type="button" className={styles.delete} disabled={locked || loading || !!deletionCleanup} onClick={() => void deleteWorld(world)}>删除世界</button>
          </nav>
        </> : <aside className={styles.tag}><span /><p className={styles.books}>这个世界暂时无法读取，请刷新书架。</p></aside>}
      </section>}
    </main>
    <div className={styles.notices}>
      {error && <p role="alert">{error} <button type="button" disabled={locked || loading} onClick={refreshArchive}>刷新书架</button></p>}
      {deletionCleanup && <p role="status">「{deletionCleanup.name}」的删除结果或收尾待确认。<button type="button" disabled={locked} onClick={() => void deleteWorld(deletionCleanup, true)}>重试清理</button></p>}
      {covers.error && <p role="alert">{covers.error}</p>}
      {notice && <p role="status">{notice}</p>}
    </div>

    {designing && world && previewReady && <BookDesigner key={`design:${world.world_id}`} client={client} world={world} sky={selectedSky ?? NIGHT} face={shelfFace}
      onFaceRequest={face => setFaceRequest(current => ({ face, nonce: (current?.nonce ?? 0) + 1 }))}
      onDraft={setDesignDraft} onDirty={setCoverDirty} onBusy={coverWorking} onSaved={cover => { covers.saved(cover); }}
      onClose={() => { setDesigning(false); setDesignDraft(null); setCoverDirty(false); heading.current?.focus(); }} />}

    {backupsOpen && sheet("存档", "保存、导入或切换整份本机数据。加载前需要明确确认。", () => setBackupsOpen(false), <SaveBackupPanel />)}
    {modelOpen && sheet("默认模型配置", "保存会重新连接核心；尚未单独设置的世界使用这里的默认配置。", () => { leaveEditor(); }, <ModelSetup client={client} onDirtyChange={setModelDirty} />)}
    {exampleOpen && sheet("体验校园示例", undefined, () => setExampleOpen(false), <ExampleWorldPanel client={client} onCreated={exampleCreated} onBusy={exampleBusy} onClose={() => setExampleOpen(false)} />)}
    {managing && world && previewReady && sheet(`「${world.name}」的世界书`, undefined, () => { if (leaveEditor()) heading.current?.focus(); },
      <WorldImports key={`archive:${world.world_id}`} client={client} worldId={world.world_id} onlyKind="lorebook" onDirtyChange={setContentDirty} onSaved={contentChanged} />, managerHeading)}

    {travelling && travelLook && <>
      <div className={styles.veil} />
      <div className={styles.portal} aria-hidden="true">
        <div className={styles.case} style={{ "--wz": travelLook.sky.zenith, "--wh": travelLook.sky.horizon } as CSSProperties}>
          <div className={styles.inside} /><div className={styles.lid}><FaceArt look={travelLook} face="front" /></div>
        </div>
      </div>
    </>}
    <p className="sr-only" role="status">{travelling ? `正在进入「${travelling.name}」` : ""}</p>
  </div>;
}
