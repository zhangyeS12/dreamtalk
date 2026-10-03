import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type ContentBuilderJob, type ContentEditorDraft,
  type ContentEditorEntry, type ContentResearch, type WorldContentItem } from "@dreamtalk/api-client";
import { ContentDetails } from "./WorldContent";

function emptyEntry(order: number): ContentEditorEntry {
  return { source_entry_id: null, title: "", content: "", keywords: [], secondary_keywords: [],
    enabled: true, constant: false, selective_logic: "AND_ANY", priority: 0, order };
}
function emptyDraft(kind: "character" | "lorebook"): ContentEditorDraft {
  return { kind, name: "", description: "", personality: "", background: "", scenario: "",
    speech_guidance: "", first_message: "", creator_notes: "", tags: [], example_dialogue: [],
    entries: kind === "lorebook" ? [emptyEntry(0)] : [] };
}
function sameDraft(left: ContentEditorDraft, right: ContentEditorDraft): boolean {
  const stable = (value: unknown) => JSON.stringify(value, (_key, item: unknown) => {
    if (item && typeof item === "object" && !Array.isArray(item)) return Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)));
    return item;
  });
  return stable(left) === stable(right);
}
const generationMessages: Record<string, string> = {
  builder_model_unavailable: "请先在模型设置中配置模型并导入 API 密钥。",
  builder_search_failed: "联网检索失败，请检查网络。可以继续手动填写。",
  builder_search_empty: "未找到可用的检索摘要，请补充作品名、角色名或换一个描述。",
  builder_token_bound_unavailable: "模型缺少可靠的 Token 预留配置，请检查模型设置。",
  builder_token_limit_exceeded: "上次请求被旧版额度检查拦截。新版资料生成已独立于聊天额度，请点击联网生成开始新请求；检查结果只读取上次请求。",
  builder_model_failed: "模型调用未完成，请检查密钥、模型额度和网络；本次可能已产生费用。",
  builder_output_invalid: "模型返回的草稿不完整或格式不符，尚未保存。重新生成将发起新的模型调用。",
  builder_output_empty: "模型未返回草稿正文，尚未保存；可能已产生费用。不会自动重试。",
  builder_output_limit: "草稿输出被截断，尚未保存。请核对回复长度，再决定是否重新生成。",
  builder_context_limit: "生成资料超过模型的上下文容量，请精简描述或检索范围。",
  builder_model_timeout: "模型请求超时，结果未确认，可能已产生费用；不会自动重发。",
  builder_model_rate_limited: "模型服务暂时限流，请稍后再决定是否重新生成。",
  builder_model_quota: "模型服务额度不足，请检查服务余额或额度。",
  builder_model_refused: "模型没有接受本次生成任务，尚未保存。可以继续手动编辑。",
  builder_interrupted: "上次生成已中断，可能已产生费用。可以重新生成，也可以手动填写。",
  builder_capacity_reached: "已有生成正在处理，请稍后再试。",
};
function previewFailureMessage(failure: unknown): string {
  if (!(failure instanceof CoreRequestError)) return "未能连接核心，请检查连接后重试预览。当前草稿仍保留，不需要重新生成。";
  if (failure.code === "editor_preview_failed") return "核心处理草稿预览时发生内部错误，内容尚未保存。当前草稿仍保留，不需要重新生成。";
  if (failure.code === "preview_capacity_reached") return "已有两份预览等待确认。请先确认或返回编辑关闭其他预览，再试一次。当前草稿仍保留。";
  if (failure.code === "builder_result_unavailable") return "暂时无法关联上次生成依据，请先点击检查生成结果，再重新预览。不要重新调用模型。";
  if (failure.status === 404) return "当前世界或关联内容已不存在，请重新选择正确世界。当前草稿仍保留。";
  if (failure.status === 409) return "该内容已有更新，请重新选择最新版本。当前草稿仍保留。";
  if (failure.status === 401 || failure.status === 403) return "核心连接已失效，请重新连接后重试预览。当前草稿仍保留。";
  if (failure.status === 422) return "草稿字段未通过校验，请检查名称、文字长度、条目正文和关键词。当前草稿仍保留，不需要重新生成。";
  return `核心未能完成预览（HTTP ${failure.status}）。当前草稿仍保留，不需要重新生成。`;
}
const fieldNames: Record<string, string> = { name: "名称", description: "描述", personality: "性格",
  background: "背景", scenario: "情境", speech_guidance: "说话方式", first_message: "开场白",
  creator_notes: "创作者备注", tags: "标签", example_dialogue: "对话示例" };

function ListInput({ value, onChange, multiline = false }: { value: string[]; onChange: (value: string[]) => void; multiline?: boolean }) {
  const [text, setText] = useState(value.join(multiline ? "\n\n" : "，"));
  const [focused, setFocused] = useState(false);
  useEffect(() => { if (!focused) setText(value.join(multiline ? "\n\n" : "，")); }, [value, focused, multiline]);
  const props = { value: text, onFocus: () => setFocused(true), onBlur: () => setFocused(false),
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const next = event.target.value; setText(next);
      onChange(next.split(multiline ? /\n\s*\n/ : /[,，、\n]/).map(x => x.trim()).filter(Boolean));
    } };
  return multiline ? <textarea rows={4} {...props} /> : <input {...props} />;
}

export function ResearchDetails({ research, edited = false }: { research: ContentResearch; edited?: boolean }) {
  return <section className="research-details" aria-label="生成依据">
    <h3>检索依据与待核对信息</h3>
    <p className="inline-hint">以下依据来自网页检索摘要。AI 的整理判断需要你核对。</p>
    {(edited || research.user_edited) && <p className="compatibility-notice">你已修改生成内容，以下判断对应原始生成稿。</p>}
    {research.conflicts.length > 0 && <div className="compatibility-notice"><h4>来源存在冲突</h4><ul>{research.conflicts.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}
    {research.uncertainties.length > 0 && <div className="compatibility-notice"><h4>需要核对</h4><ul>{research.uncertainties.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}
    <details><summary>字段依据与创作建议（{research.claims.length}）</summary><ul className="research-claims">{research.claims.map((claim, i) => <li key={i}>
      <strong>{fieldNames[claim.field] ?? (/^entries\.\d+\.content$/.test(claim.field) ? `条目 ${Number(claim.field.split(".")[1]) + 1}` : claim.field)}</strong>
      <span className={`claim-status ${claim.status}`}>{claim.status === "creative" ? "AI 创作建议" : claim.status === "uncertain" ? "待核对" : "AI 标注出处"}</span>
      <p>{claim.text}</p><small>{claim.sources.length ? `依据：${claim.sources.join("、")}` : "无原作事实出处"}</small>
    </li>)}</ul></details>
    <details open><summary>检索出处（{research.sources.length}）</summary><ol className="research-sources">{research.sources.map(source => <li key={source.id}>
      <span>{source.id} · </span><a href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a>
      <p>{source.excerpt}</p><small>{new URL(source.url).hostname} · {new Date(source.retrieved_at).toLocaleString("zh-CN")}</small>
    </li>)}</ol></details>
  </section>;
}

export function ContentEditor({ client, worldId, kind, editing, onSaved, onCancel }: {
  client: CoreClient; worldId: string; kind: "character" | "lorebook"; editing?: WorldContentItem;
  onSaved: (item: WorldContentItem) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState(() => emptyDraft(kind));
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(!!editing);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<ContentBuilderJob | null>(null);
  const [research, setResearch] = useState<ContentResearch | null>(null);
  const [generationId, setGenerationId] = useState<string | undefined>();
  const [recoverId, setRecoverId] = useState<string | null>(null);
  const [preview, setPreview] = useState<WorldContentItem | null>(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const live = useRef(true);
  const errorNotice = useRef<HTMLParagraphElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const target = error ? errorNotice.current : preview ? previewHeading.current : null;
    if (target) {
      target.scrollIntoView({ block: "start" });
      target.focus({ preventScroll: true });
    }
  }, [error, preview]);
  const pending = useRef<string | null>(null);
  const appliedJob = useRef<string | null>(null);
  const currentJob = useRef<string | null>(null);
  const pollFailures = useRef(0);
  const storageKey = `dreamtalk.content-builder.${worldId}.${kind}`;
  const generating = job?.state === "searching" || job?.state === "generating";
  useEffect(() => {
    live.current = true;
    try { const id = localStorage.getItem(storageKey); if (id) setRecoverId(id); } catch { /* Memory still works. */ }
    if (editing) void client.contentEditor(worldId, editing.import_id).then(result => {
      if (live.current) { setDraft(result.draft); setResearch(result.research); }
    }).catch(() => { if (live.current) { setError("无法打开该内容的编辑稿。请重新进入设置并选择最新版本。"); setLoadFailed(true); } })
      .finally(() => { if (live.current) setLoading(false); });
    return () => {
      live.current = false;
      if (pending.current) void client.discardWorldContent(worldId, pending.current).catch(() => undefined);
    };
  }, [client, worldId, editing, storageKey]);

  const applyJob = (result: ContentBuilderJob) => {
    if (!live.current || currentJob.current !== result.request_id) return;
    setJob(result);
    if (result.state === "ready" && result.result && appliedJob.current !== result.request_id) {
      appliedJob.current = result.request_id;
      setDraft(result.result.draft); setResearch(result.result); setGenerationId(result.request_id);
      setQuery(result.result.query); setError("");
    } else if (result.state === "failed" || result.state === "interrupted") {
      setError(generationMessages[result.error ?? ""] ?? "本次生成未完成，内容尚未保存。可以继续手动编辑。");
    }
  };
  useEffect(() => {
    if (!generating || !job) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await client.contentGenerationStatus(worldId, job.request_id);
        if (stopped || !live.current || currentJob.current !== result.request_id) return;
        pollFailures.current = 0;
        setJob(result);
        if (result.state === "ready" && result.result && appliedJob.current !== result.request_id) {
          appliedJob.current = result.request_id;
          setDraft(result.result.draft); setResearch(result.result); setGenerationId(result.request_id);
          setQuery(result.result.query); setError("");
        } else if (result.state === "failed" || result.state === "interrupted") {
          setError(generationMessages[result.error ?? ""] ?? "生成未完成，可以继续手动填写。");
        } else timer = setTimeout(() => void poll(), 2000);
      } catch {
        if (stopped || !live.current) return;
        pollFailures.current += 1;
        if (pollFailures.current < 2) timer = setTimeout(() => void poll(), 2000);
        else setError("暂时无法读取进度，请点击检查生成结果。检查不会再次调用模型。");
      }
    };
    timer = setTimeout(() => void poll(), 2000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [client, worldId, job, generating]);

  const generate = async () => {
    if (recoverId && !job && appliedJob.current !== recoverId && !window.confirm("之前的请求已保留。新的生成会发起新的模型调用，是否继续？")) return;
    if (draft.name.trim() && !window.confirm("联网生成会替换当前填写的字段，生成后仍可修改。是否继续？")) return;
    const id = crypto.randomUUID();
    currentJob.current = id; appliedJob.current = null; pollFailures.current = 0;
    setJob({ request_id: id, state: "searching", result: null, error: null });
    setRecoverId(id); setError("");
    try { localStorage.setItem(storageKey, id); } catch { /* Recovery is optional. */ }
    try { applyJob(await client.generateContent(worldId, kind, query.trim(), id)); }
    catch (failure) {
      if (live.current && currentJob.current === id) setError(failure instanceof CoreRequestError && failure.status === 404
        ? "当前世界不存在，请重新选择世界。" : "未能确认生成结果。请检查结果；检查不会再次调用模型。");
    }
  };
  const check = async () => {
    const id = currentJob.current ?? recoverId;
    if (!id) return;
    if (!currentJob.current && draft.name.trim() && !window.confirm("恢复上次生成结果会替换当前填写的字段。是否继续？")) return;
    currentJob.current = id; setChecking(true); setError(""); pollFailures.current = 0;
    try { applyJob(await client.contentGenerationStatus(worldId, id)); }
    catch { setError("暂时无法找到或读取该次生成结果。请检查网络；也可以继续手动填写。"); }
    finally { if (live.current) setChecking(false); }
  };
  const review = async () => {
    if (busy || generating || loading || loadFailed || preview) return;
    if (!draft.name.trim()) { setError(kind === "character" ? "请填写角色名称后再预览。" : "请填写世界书名称后再预览。"); return; }
    if (kind === "lorebook") {
      if (!draft.entries.length) { setError("请至少添加一条世界书正文后再预览。"); return; }
      const invalid = draft.entries.findIndex(entry => !entry.content.trim() || entry.secondary_keywords.length > 0 && !entry.keywords.length);
      if (invalid >= 0) { setError(`请检查条目 ${invalid + 1}：正文不能为空，使用次级关键词时需要填写主关键词。`); return; }
    }
    setBusy(true); setError("");
    try {
      const result = await client.previewEditedContent(worldId, draft, editing?.import_id, generationId);
      if (!live.current) { await client.discardWorldContent(worldId, result.import_id); return; }
      pending.current = result.import_id; setPreview(result);
    } catch (failure) {
      if (live.current) setError(previewFailureMessage(failure));
    }
    finally { if (live.current) setBusy(false); }
  };
  const save = async () => {
    if (!preview) return;
    setBusy(true); setError("");
    try {
      const saved = await client.commitWorldContent(worldId, preview);
      if (!live.current) return;
      pending.current = null; onSaved(saved);
    } catch (failure) { if (live.current) setError(failure instanceof CoreRequestError && failure.status === 422
      ? "预览已过期，请返回编辑后重新预览。" : failure instanceof CoreRequestError && failure.status === 409
      ? "该内容已有更新，请重新打开最新版本。" : "未能确认保存结果。可以再次确认，同一份预览不会重复保存。"); }
    finally { if (live.current) setBusy(false); }
  };
  const update = (key: keyof ContentEditorDraft, value: string | string[]) => setDraft(old => ({ ...old, [key]: value }));
  const updateEntry = (index: number, change: Partial<ContentEditorEntry>) => setDraft(old => ({ ...old,
    entries: old.entries.map((entry, i) => i === index ? { ...entry, ...change } : entry) }));
  const disabled = busy || generating || loading || loadFailed;
  const reviewActions = preview && (
      <div className="profile-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? "正在保存…" : editing ? "确认更新当前世界" : "确认加入当前世界"}</button>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => { pending.current = null; void client.discardWorldContent(worldId, preview.import_id).catch(() => undefined); setPreview(null); }}>返回编辑</button></div>
  );
  return <div className="content-editor">
    <div className="editor-heading"><div><h3>{editing ? "编辑" : "新建"}{kind === "character" ? "角色卡" : "世界书"}</h3><p>在当前世界保存前，可以自由修改。</p></div>
      <button className="text-action" type="button" disabled={busy} onClick={() => { if (!draft.name.trim() || window.confirm("当前草稿尚未保存，是否放弃编辑？")) onCancel(); }}>关闭编辑</button></div>
    {loading && <p role="status">正在读取编辑稿…</p>}
    {error && <p ref={errorNotice} tabIndex={-1} className="app-alert editor-feedback" role="alert">{error}</p>}
    {preview ? <div className="editor-review"><h3 ref={previewHeading} tabIndex={-1} className="editor-feedback">保存预览</h3>
      <p className="app-notice" role="status">预览已准备好，内容尚未保存。请核对下方内容，再点击“确认{editing ? "更新" : "加入"}当前世界”。</p>
      <p className="inline-hint">{kind === "character" ? "确认后将在当前世界的通讯录中显示。" : editing ? "更新后显示实际保存的可见范围。" : "世界书条目默认隐藏，保存后可逐条设为公共背景。"}{editing && kind === "lorebook" && "完全未变且唯一对应的条目会保留原范围；新增或修改正文、触发条件的条目需要重新确认公开。"}</p>
      {reviewActions}
      <ContentDetails item={preview} />
      {reviewActions}
    </div> : <>
      <div className="research-request"><label className="field"><span>用一句话描述，联网生成初稿</span><textarea rows={2} maxLength={600} value={query} disabled={disabled} onChange={event => setQuery(event.target.value)} placeholder={kind === "character" ? "生成一个绝区零里艾莲的角色卡" : "生成绝区零的世界书，包含新艾利都、空洞和主要势力"} /></label>
        <div className="profile-actions"><button type="button" className="secondary-button" disabled={disabled || !query.trim()} onClick={() => void generate()}>{generating ? job?.state === "generating" ? "正在调用模型填写…" : "正在联网检索…" : "联网生成"}</button>
          {(recoverId || job) && <button type="button" className="text-action" disabled={checking || busy || loading} onClick={() => void check()}>{checking ? "正在检查…" : "检查生成结果"}</button>}
          {generating && <button type="button" className="text-action" onClick={() => { currentJob.current = null; setJob(null); setError("请求已保留，可以稍后检查结果。现在可以手动填写；重新生成会发起新的模型调用。"); }}>继续手动填写</button>}</div>
        <p className="inline-hint">资料生成使用独立任务额度，与聊天的每轮 Token 上限无关，无需调整聊天额度。每次模型输出最多 8,192 Token，若模型设置更低则使用更低上限。描述将发送给搜索引擎，检索摘要与描述将发送给模型；按实际模型用量计费。</p>
        {generating && <p role="status">{job?.state === "generating" ? "已获取检索摘要，正在整理成可编辑草稿。" : "正在查找相关网页与资料。"}</p>}
      </div>
      <fieldset className="editor-fields" disabled={disabled}><legend className="visually-hidden">{kind === "character" ? "角色资料" : "世界书资料"}</legend>
        <label className="field"><span>{kind === "character" ? "角色名称" : "世界书名称"} *</span><input value={draft.name} maxLength={300} onChange={event => update("name", event.target.value)} placeholder={kind === "character" ? "例如：艾莲·乔" : "例如：新艾利都"} required /></label>
        <label className="field"><span>{kind === "character" ? "角色描述" : "世界书简介"}</span><textarea rows={4} maxLength={16000} value={draft.description} onChange={event => update("description", event.target.value)} /></label>
        {kind === "character" ? <>
          <div className="editor-columns">{(["personality", "background", "speech_guidance", "scenario"] as const).map(key => <label className="field" key={key}><span>{fieldNames[key]}</span><textarea rows={4} maxLength={16000} value={draft[key]} onChange={event => update(key, event.target.value)} /></label>)}</div>
          <label className="field"><span>开场白</span><textarea rows={3} maxLength={16000} value={draft.first_message} onChange={event => update("first_message", event.target.value)} /><small>回复可以参考语气，目前不会自动作为消息发送。</small></label>
          <label className="field"><span>对话示例（每段以空行分隔）</span><ListInput multiline value={draft.example_dialogue} onChange={value => update("example_dialogue", value)} /></label>
          <label className="field"><span>标签（用逗号分隔）</span><ListInput value={draft.tags} onChange={value => update("tags", value)} /></label>
          <label className="field"><span>创作者备注</span><textarea rows={2} maxLength={16000} value={draft.creator_notes} onChange={event => update("creator_notes", event.target.value)} /></label>
        </> : <div className="lore-entry-editor"><h4>世界书条目</h4><p className="inline-hint">正文写清独立设定。公开后，常驻条目持续提供；关键词条目在会话中命中时提供。已开启的自动活动规划也会匹配角色名和当前地点名。</p>
          {draft.entries.map((entry, index) => <section className="editable-lore-entry" key={entry.source_entry_id ?? index}>
            <div className="editor-heading"><h4>条目 {index + 1}</h4><button type="button" className="text-action" onClick={() => setDraft(old => ({ ...old, entries: old.entries.filter((_, i) => i !== index) }))}>删除条目</button></div>
            <label className="field"><span>标题</span><input maxLength={300} value={entry.title} onChange={event => updateEntry(index, { title: event.target.value })} /></label>
            <label className="field"><span>正文 *</span><textarea rows={4} maxLength={16000} value={entry.content} required onChange={event => updateEntry(index, { content: event.target.value })} /></label>
            <div className="editor-columns"><label className="field"><span>主关键词（逗号分隔）</span><ListInput value={entry.keywords} onChange={value => updateEntry(index, { keywords: value })} /></label>
              <label className="field"><span>提供条件</span><select value={entry.constant ? "constant" : "keywords"} onChange={event => updateEntry(index, { constant: event.target.value === "constant" })}><option value="keywords">命中关键词</option><option value="constant">常驻背景</option></select></label></div>
            <details><summary>次级条件与排序</summary><label className="field"><span>次级关键词（需要主关键词）</span><ListInput value={entry.secondary_keywords} onChange={value => updateEntry(index, { secondary_keywords: value })} /></label>
              <label className="field"><span>次级条件</span><select value={entry.selective_logic} onChange={event => updateEntry(index, { selective_logic: event.target.value as ContentEditorEntry["selective_logic"] })}><option value="AND_ANY">任一命中</option><option value="AND_ALL">全部命中</option><option value="NOT_ANY">全部不命中</option><option value="NOT_ALL">不能全部命中</option></select></label>
              <div className="editor-columns">{(["priority", "order"] as const).map(key => <label key={key} className="field"><span>{key === "priority" ? "优先级" : "顺序"}</span><input type="number" min={-1000000} max={1000000} step={1} value={entry[key]} onChange={event => updateEntry(index, { [key]: Number(event.target.value) })} /></label>)}</div>
            </details><label className="editor-checkbox"><input type="checkbox" checked={entry.enabled} onChange={event => updateEntry(index, { enabled: event.target.checked })} />启用条目</label>
          </section>)}<button className="secondary-button" type="button" disabled={draft.entries.length >= 128} onClick={() => setDraft(old => ({ ...old, entries: [...old.entries, emptyEntry(old.entries.length)] }))}>添加条目</button>
        </div>}
        {editing && <p className="inline-hint">附带素材、角色内嵌世界书和未开放的兼容字段会保留。高级触发条件的支持范围以保存预览为准。</p>}
      </fieldset>
      {research && <ResearchDetails research={research} edited={!sameDraft(draft, research.draft)} />}
      <div className="profile-actions"><button type="button" className="primary-button" disabled={disabled} onClick={() => void review()}>{busy ? "正在准备预览…" : "预览并保存"}</button><span className="inline-hint" role="status">{busy ? "正在创建保存预览，请稍候。此步骤不会调用模型。" : "先打开保存预览，再确认加入当前世界。"}</span></div>
    </>}
  </div>;
}
