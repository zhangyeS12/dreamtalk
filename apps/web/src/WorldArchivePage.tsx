import { DesktopUpdateEntry, useDesktopUpdateBlock } from "./DesktopUpdates";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { CoreClient, CoreRequestError, type WorldSettings, type WorldContentItem } from "@dreamtalk/api-client";
import { ModelSetup } from "./ModelSetup";
import { WorldImports } from "./WorldContent";
import { WorldShelf, worldShelfBlankCount } from "./WorldShelf";
import { WorldCoverEditor } from "./WorldCoverEditor";
import { useWorldCovers } from "./useWorldCovers";
import { Brand } from "./Brand";
import "./world-archive.css";
import "./world-cover.css";

export function WorldArchivePage({ client, initialWorldId, onEnter, displayTime, onStartupStatus }: {
  client: CoreClient; initialWorldId: string | null;
  onEnter: (id: string, hasIdentity: boolean) => void; displayTime: (raw: string) => string;
  onStartupStatus?: (ready: boolean) => void;
}) {
  const covers = useWorldCovers(client);
  const [coverOpen, setCoverOpen] = useState(false);
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
    if (!onStartupStatus || startupReported.current || loading || !startupFailed && !covers.ready) return;
    // The real books/covers have committed. Avoid waiting for animation frames:
    // hidden autostart windows may not receive them at all.
    startupReported.current = true; onStartupStatus(!startupFailed);
  }, [onStartupStatus, loading, covers.ready, startupFailed]);
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
    setCoverOpen(false); setCoverDirty(false); setManaging(false); setModelOpen(false); setContentDirty(false); setModelDirty(false);
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
      onEnter(world.world_id, Boolean(identity.player_id));
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
  return <div className="product-shell archive-shell">
    <header className="archive-header"><Brand /><span className="archive-header-label">世界档案库</span><DesktopUpdateEntry />
      <button type="button" className="text-action" disabled={busy || entering || coverBusy} onClick={() => {
        if (modelOpen) { leaveEditor(); return; }
        if (leaveEditor()) { clearSelection(); setModelOpen(true); }
      }}>模型设置</button>
    </header>
    <main className="archive-main">
      <div className="archive-intro"><div><h1 ref={heading} tabIndex={-1}>世界书架</h1><p>挑一本书，走进其中的世界。</p></div>
        <button type="button" className="text-action" disabled={loading || busy || entering || coverBusy} onClick={refreshArchive}>{loading ? "正在读取…" : "刷新书架"}</button>
      </div>
      {error && <p className="app-alert" role="alert">{error} <button type="button" className="text-action" disabled={busy || entering || coverBusy || loading} onClick={refreshArchive}>刷新书架</button></p>}
      {deletionCleanup && <p className="app-alert" role="status">「{deletionCleanup.name}」的删除结果或收尾待确认。<button type="button" className="text-action" disabled={busy || entering || coverBusy} onClick={() => void deleteWorld(deletionCleanup, true)}>重试清理</button></p>}
      {covers.error && <p className="app-alert" role="alert">{covers.error}</p>}
      {notice && <p className="app-notice" role="status">{notice}</p>}
      {modelOpen && <div className="archive-editor"><div className="archive-editor-heading"><h2>默认模型配置</h2><button type="button" className="text-action" onClick={() => { leaveEditor(); }}>收起</button></div><ModelSetup client={client} onDirtyChange={setModelDirty} /><p className="inline-hint">保存会重新连接核心；尚未单独设置的世界使用这里的默认配置。</p></div>}
      <div ref={layout} className={`archive-layout ${selectionKey ? "has-selection" : ""}`}>
        <WorldShelf worlds={worlds} appearances={covers.appearances} selectedKey={selectionKey} initialWorldId={initialWorldId} loading={loading} disabled={busy || entering || coverBusy} vacatedIndex={vacatedIndex}
          onSelect={select} onCreate={selectBlank} onClose={closeSelection} onSettled={settled} />
        {previewReady && <section key={selectionKey} id="archive-preview" className="archive-preview" aria-label={blankIndex !== null ? "创建世界档案" : "所选世界预览"} aria-busy={entering}
          onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); closeSelection(); } }}>
          <div className="archive-preview-heading"><span>{blankIndex !== null ? "新的世界" : "世界档案"}</span><button type="button" className="text-action" disabled={busy || entering || coverBusy} onClick={closeSelection}>归位 ×</button></div>
          {blankIndex !== null ? creating ? <><h2>先给世界一个名字</h2><p className="archive-description">{createIntent === "import" ? "先创建世界档案，再选择已有世界书文件，检查并确认导入。" : "创建档案后，可以手动填写设定、联网生成，或导入世界书。"}</p>
            <form onSubmit={event => void create(event)}><label className="field"><span>世界名称</span><input ref={creatorInput} maxLength={120} value={name} disabled={busy || pendingCreation} onChange={event => setName(event.target.value)} placeholder="例如：绝区零" required /></label>
              <button type="submit" className="primary-button" disabled={busy || !name.trim()}>{busy ? "正在创建…" : pendingCreation ? "核对上次创建结果" : createIntent === "import" ? "创建档案并导入世界书" : "创建档案并添加世界书"}</button>
            </form>{pendingCreation && !busy && <p className="archive-description">上次创建结果待核对，名称暂时保留。点击核对沿用同一次请求。</p>}
            <button type="button" className="text-action" disabled={busy} onClick={() => setCreating(false)}>返回创建选项</button>
          </> : <><h2>从这本空白书开始</h2><p className="archive-description">给新的世界一个名字，再添加它的故事与设定。</p>
            <div className="archive-preview-actions"><button type="button" className="primary-button" disabled={busy || loading} onClick={() => { setCreateIntent("create"); setCreating(true); }}>创建世界</button>
              <button type="button" className="secondary-button" disabled={busy || loading} onClick={() => { setCreateIntent("import"); setCreating(true); }}>导入世界书</button></div>
            <p className="archive-footnote">空白书位只是入口。确认创建前，不会保存新世界。</p>
          </> : world ? <><h2>{world.name}</h2>
            {contentError ? <p role="alert" className="archive-description">{contentError} <button type="button" className="text-action" onClick={contentChanged}>刷新摘要</button></p> : !books ? <p className="archive-description" role="status">正在读取世界设定…</p> : books.length ? <div className="archive-book-summary"><ul>{books.slice(0, 4).map(item => <li key={item.import_id}><strong>{item.lorebooks[0]?.name ?? "世界书"}</strong>{item.lorebooks[0]?.description && <p>{item.lorebooks[0].description}</p>}</li>)}</ul>{books.length > 4 && <small>管理世界书可查看全部 {books.length} 份设定。</small>}</div> : <p className="archive-description">尚未添加世界书。可以先导入设定，也可以进入世界后继续完善。</p>}
            <div className="archive-facts"><span>世界时间</span><strong>{displayTime(world.world_time)}</strong><span>时间状态</span><strong>{world.clock_state === "paused" ? "已暂停" : "运行中"}{world.runtime_state === "degraded" ? " · 运行需要处理" : ""}</strong></div>
            <div className="archive-preview-actions"><button type="button" className="primary-button" disabled={busy || entering || coverBusy || loading} onClick={() => void enter()}>{entering ? "正在读取世界…" : "进入世界 →"}</button>
              <button type="button" className="secondary-button" disabled={busy || entering || coverBusy} onClick={() => { const shouldOpen = !managing; if (!leaveEditor()) return; setManaging(shouldOpen); }}>管理 / 导入世界书</button>
              <button type="button" className="text-action" disabled={busy || entering || coverBusy} onClick={() => { const opening = !coverOpen; if (leaveEditor()) setCoverOpen(opening); }}>编辑封面</button></div>
            <div className="archive-delete-action"><button type="button" className="text-action destructive-action" disabled={busy || entering || coverBusy || loading || !!deletionCleanup} onClick={() => void deleteWorld(world)}>删除世界</button><small>永久清除本书内的世界和全部存档</small></div>
          </> : <p className="archive-description">这个世界暂时无法读取，请刷新书架。</p>}
        </section>}
      </div>
      {coverOpen && world && previewReady && <WorldCoverEditor key={`cover:${world.world_id}`} client={client} world={world} onDirty={setCoverDirty} onBusy={coverWorking} onSaved={covers.saved} onClose={() => { if (leaveEditor()) heading.current?.focus(); }} />}
      {managing && world && previewReady && <div className="archive-editor"><div className="archive-editor-heading"><h2 ref={managerHeading} tabIndex={-1}>「{world.name}」的世界书</h2><button type="button" className="text-action" disabled={busy || entering || coverBusy} onClick={() => { if (leaveEditor()) heading.current?.focus(); }}>收起管理</button></div>
        <WorldImports key={`archive:${world.world_id}`} client={client} worldId={world.world_id} onlyKind="lorebook" onDirtyChange={setContentDirty} onSaved={contentChanged} />
      </div>}
    </main>
    <footer className="archive-footer"><span>世界档案 · 我的书架</span><span>世界书架只预览，后台功能遵循已有设置</span></footer>
  </div>;
}
