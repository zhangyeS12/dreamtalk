import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { CoreClient, CoreRequestError, type WorldSettings, type WorldContentItem } from "@dreamtalk/api-client";
import { ModelSetup } from "./ModelSetup";
import { WorldImports } from "./WorldContent";
import { WorldShelf } from "./WorldShelf";
import "./world-archive.css";

export function WorldArchivePage({ client, initialWorldId, onEnter, displayTime }: {
  client: CoreClient; initialWorldId: string | null;
  onEnter: (id: string, hasIdentity: boolean) => void; displayTime: (raw: string) => string;
}) {
  const [worlds, setWorlds] = useState<WorldSettings[]>([]);
  const [selectedId, setSelectedId] = useState(initialWorldId ?? "");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [creating, setCreating] = useState(false);
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
  const managerHeading = useRef<HTMLHeadingElement>(null);
  const world = worlds.find(item => item.world_id === selectedId);
  const items = content?.worldId === selectedId ? content.items : null;
  const books = items?.filter(item => item.kind === "lorebook");
  const refresh = useCallback(async () => {
    const result = await client.listProductWorlds();
    if (!active.current) return result;
    setWorlds(result);
    setSelectedId(current => result.some(item => item.world_id === current) ? current : result[0]?.world_id ?? "");
    return result;
  }, [client]);
  useEffect(() => {
    active.current = true;
    void refresh().catch(() => { if (active.current) setError("世界档案未能读取。请检查核心连接后刷新。"); })
      .finally(() => { if (active.current) setLoading(false); });
    const timer = window.setInterval(() => {
      if (!lock.current) void refresh().catch(() => { if (active.current) setError("世界状态暂时无法刷新。已有草稿仍保留。"); });
    }, 15000);
    return () => { active.current = false; window.clearInterval(timer); };
  }, [refresh]);
  useEffect(() => {
    if (!isTauri()) return;
    const report = () => void invoke("report_desktop_presence", { worldId: null, visible: false }).catch(() => undefined);
    report();
    const timer = window.setInterval(report, 10000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { if (creating) creatorInput.current?.focus(); }, [creating]);
  useEffect(() => {
    if (managing) { managerHeading.current?.scrollIntoView({ block: "start" }); managerHeading.current?.focus({ preventScroll: true }); }
  }, [managing]);
  useEffect(() => {
    let mounted = true;
    setContent(null); setContentError("");
    if (selectedId) void client.worldContent(selectedId).then(result => {
      if (mounted) setContent({ worldId: selectedId, items: result });
    }).catch(() => { if (mounted) setContentError("设定摘要暂时无法读取，可刷新后再试。"); });
    return () => { mounted = false; };
  }, [client, selectedId, contentRevision]);
  const leaveEditor = () => {
    if (lock.current) return false;
    if ((contentDirty || modelDirty) && !window.confirm("有尚未保存的编辑，是否离开当前编辑？已发起的联网生成不会自动重放。")) return false;
    setManaging(false); setModelOpen(false); setContentDirty(false); setModelDirty(false);
    return true;
  };
  const select = (id: string) => {
    if (id === selectedId && !creating) return;
    if (!leaveEditor()) return;
    setCreating(false); setSelectedId(id); setNotice(""); setError("");
  };
  const startCreate = () => {
    if (!leaveEditor()) return;
    setCreating(true); setNotice(""); setError("");
  };
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const value = name.trim();
    if (!value || lock.current) return;
    lock.current = true; setBusy(true); setPendingCreation(true); setError(""); setNotice("");
    if (!request.current || request.current.name !== value) request.current = { name: value, id: crypto.randomUUID() };
    try {
      const result = await client.createWorld(value, request.current.id);
      if (!active.current) return;
      const directory = await refresh();
      if (!active.current) return;
      if (!directory.some(item => item.world_id === result.world_id)) throw new Error("archive_not_readable");
      setSelectedId(result.world_id); setName(""); request.current = null; setPendingCreation(false);
      setCreating(false); setManaging(true);
      setNotice("世界档案已创建。现在添加世界书，也可以稍后再完善。");
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
        setWorlds(directory); setError("这个世界已不存在，请刷新书架。"); return;
      }
      onEnter(world.world_id, Boolean(identity.player_id));
    } catch { if (active.current) setError("未能读取进入世界所需的信息。请检查核心连接后重试。"); }
    finally { lock.current = false; if (active.current) setEntering(false); }
  };
  const refreshArchive = () => {
    if (lock.current || loading) return;
    setLoading(true);
    void refresh().then(() => { if (active.current) { setError(""); setContentRevision(value => value + 1); } })
      .catch(() => { if (active.current) setError("世界档案仍无法读取，请检查核心连接。"); })
      .finally(() => { if (active.current) setLoading(false); });
  };
  const contentChanged = useCallback(() => setContentRevision(value => value + 1), []);
  return <div className="product-shell archive-shell">
    <header className="archive-header"><span className="app-brand">dreamtalk</span><span className="archive-header-label">世界档案库</span>
      <button type="button" className="text-action" disabled={busy || entering} onClick={() => {
        if (modelOpen) { leaveEditor(); return; }
        if (leaveEditor()) { setModelOpen(true); setCreating(false); }
      }}>模型设置</button>
    </header>
    <main className="archive-main">
      <div className="archive-intro"><div><p className="archive-eyebrow">YOUR WORLDS, STILL HERE</p><h1 ref={heading} tabIndex={-1}>每个世界，都有下一页。</h1><p>从书架打开一个世界，继续与其中的角色相处。</p></div>
        <div className="archive-top-actions"><button type="button" className="text-action" disabled={loading || busy || entering} onClick={refreshArchive}>{loading ? "正在读取…" : "刷新书架"}</button><button type="button" className="secondary-button" disabled={loading || busy || entering} onClick={startCreate}>＋ 新建 / 导入世界</button></div>
      </div>
      {error && <p className="app-alert" role="alert">{error} <button type="button" className="text-action" disabled={busy || entering || loading} onClick={refreshArchive}>刷新书架</button></p>}
      {notice && <p className="app-notice" role="status">{notice}</p>}
      {modelOpen ? <div className="archive-editor"><div className="archive-editor-heading"><h2>模型连接</h2><button type="button" className="text-action" onClick={() => { leaveEditor(); }}>收起</button></div><ModelSetup client={client} onDirtyChange={setModelDirty} /><p className="inline-hint">保存会重新连接核心；聊天和联网创作使用现有模型配置。</p></div> : null}
      <div className="archive-layout">
        <WorldShelf worlds={worlds} selectedId={creating ? "" : selectedId} loading={loading} disabled={busy || entering} onSelect={select} onCreate={startCreate} />
        <section className="archive-preview" aria-label={creating ? "创建世界档案" : "所选世界预览"} aria-busy={entering}>
          {creating ? <><p className="archive-eyebrow">NEW WORLD</p><h2>先给世界一个名字</h2><p className="archive-description">创建档案后，直接添加已有世界书，或手动、联网填写设定。</p>
            <form onSubmit={event => void create(event)}><label className="field"><span>世界名称</span><input ref={creatorInput} maxLength={120} value={name} disabled={busy || pendingCreation} onChange={event => setName(event.target.value)} placeholder="例如：绝区零" required /></label>
              <button type="submit" className="primary-button" disabled={busy || !name.trim()}>{busy ? "正在创建…" : pendingCreation ? "核对上次创建结果" : "创建档案并添加世界书"}</button>
            </form>{pendingCreation && !busy && <p className="archive-description">上次创建结果待核对，名称暂时保留。点击核对沿用同一次请求。</p>}<button type="button" className="text-action" disabled={busy} onClick={() => { setCreating(false); heading.current?.focus(); }}>返回书架</button>
            <p className="archive-footnote">空白书位不占存档。只有确认创建后，才会保存这个世界。</p></> : world ? <>
            <p className="archive-eyebrow">WORLD ARCHIVE</p><h2>{world.name}</h2>
            <div className="archive-facts"><span>世界时间</span><strong>{displayTime(world.world_time)}</strong><span>时间状态</span><strong>{world.clock_state === "paused" ? "已暂停" : "运行中"}{world.runtime_state === "degraded" ? " · 运行需要处理" : ""}</strong></div>
            {contentError ? <p role="alert" className="archive-description">{contentError} <button type="button" className="text-action" onClick={contentChanged}>刷新摘要</button></p> : !books ? <p className="archive-description" role="status">正在读取世界设定…</p> : books.length ? <div className="archive-book-summary"><h3>已保存的世界书 · {books.length}</h3><ul>{books.slice(0, 4).map(item => <li key={item.import_id}><strong>{item.lorebooks[0]?.name ?? "世界书"}</strong>{item.lorebooks[0]?.description && <p>{item.lorebooks[0].description}</p>}</li>)}</ul>{books.length > 4 && <small>管理世界书可查看全部内容。</small>}</div> : <p className="archive-description">尚未添加世界书。可以先导入设定，也可以进入世界后继续完善。</p>}
            <div className="archive-preview-actions"><button type="button" className="primary-button" disabled={busy || entering || loading} onClick={() => void enter()}>{entering ? "正在读取世界…" : "进入世界 →"}</button>
              <button type="button" className="secondary-button" disabled={busy || entering} onClick={() => { const shouldOpen = !managing; if (!leaveEditor()) return; setManaging(shouldOpen); }}>管理 / 导入世界书</button></div>
            <p className="archive-footnote">书架只预览档案。已开启的后台功能仍按原设置运行。</p>
          </> : <><p className="archive-eyebrow">A PLACE TO BEGIN</p><h2>{loading ? "正在打开书架" : "你的第一个世界"}</h2><p className="archive-description">选择一本空白书，创建世界档案，再添加世界书和角色。</p></>}
        </section>
      </div>
      {managing && world && !creating && <div className="archive-editor"><div className="archive-editor-heading"><h2 ref={managerHeading} tabIndex={-1}>「{world.name}」的世界书</h2><button type="button" className="text-action" disabled={busy || entering} onClick={() => { if (leaveEditor()) heading.current?.focus(); }}>收起管理</button></div>
        <WorldImports key={`archive:${world.world_id}`} client={client} worldId={world.world_id} onlyKind="lorebook" onDirtyChange={setContentDirty} onSaved={contentChanged} />
      </div>}
    </main>
    <footer className="archive-footer"><span>世界档案 · 文字封面</span><span>选择世界后进入聊天、通讯录、设置与我的身份</span></footer>
  </div>;
}
