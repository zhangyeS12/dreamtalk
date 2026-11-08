import { useEffect, useRef, useState } from "react";
import type { ContentEditorDraft, CoreClient, LibraryCardItem, LibraryCardPreview, WorldContentItem } from "@dreamtalk/api-client";
import { ContentDetails } from "../../WorldContent";
import { contentImportWarning, groupImportWarnings } from "../../contentImportFeedback";
import { CardPresentationPreview } from "./CardPresentationPreview";
import { defaultDesign } from "./cardDesign";
import { CardDialog } from "./CardDialog";
import styles from "./Cards.module.css";
import { libraryFailure } from "./libraryFeedback";

export function CardReview({ item }: { item: WorldContentItem }) {
  return <div className={`${styles.review} dt-sheet-body`}><ContentDetails item={item} />
    {Boolean(item.warnings?.length) && <div className={styles.warning}><p>请核对兼容性提示，原始文件会完整保留。</p><ul>{groupImportWarnings(item.warnings ?? []).map(warning => <li key={warning.code}>{contentImportWarning(warning.code)}{warning.count > 1 && `（${warning.count}项）`}{warning.paths.length > 0 && <details><summary>涉及字段</summary><p>{warning.paths.join("、")}</p></details>}</li>)}</ul></div>}
  </div>;
}
export function CardAuthor({ client, editing, onSaved, onClose }: { client: CoreClient; editing: LibraryCardItem | null; onSaved: (card: LibraryCardItem) => void | Promise<void>; onClose: () => void }) {
  const [draft, setDraft] = useState<ContentEditorDraft>({ kind: "character", name: "", description: "", personality: "", background: "", scenario: "", speech_guidance: "", first_message: "", creator_notes: "", tags: [], example_dialogue: [], entries: [] });
  const [loading, setLoading] = useState(Boolean(editing)), [busy, setBusy] = useState(false), busyRef = useRef(false);
  const [preview, setPreview] = useState<LibraryCardPreview | null>(null), pending = useRef<string | null>(null);
  const [error, setError] = useState(""), dirty = useRef(false), initialCard = useRef(editing);
  const [readFailed, setReadFailed] = useState(false);
  const original = useRef(draft);
  useEffect(() => { const controller = new AbortController(); if (editing) void client.libraryCard(editing.card_id, controller.signal).then(result => { initialCard.current = result.card; original.current = result.draft; setDraft(result.draft); setLoading(false); }).catch(failure => { if (!controller.signal.aborted) { setReadFailed(true); setError(libraryFailure(failure)); setLoading(false); } }); return () => { controller.abort(); if (pending.current) void client.discardLibraryPreview(pending.current).catch(() => undefined); }; }, [client, editing]);
  const close = () => { if (!busyRef.current && (!dirty.current || window.confirm("角色设定尚未保存，放弃这些修改？"))) onClose(); };
  const change = (patch: Partial<ContentEditorDraft>) => { dirty.current = true; setDraft(current => ({ ...current, ...patch })); };
  const work = async (action: () => Promise<void>) => { if (busyRef.current) return; busyRef.current = true; setBusy(true); setError(""); try { await action(); } catch (failure) { setError(libraryFailure(failure)); } finally { busyRef.current = false; setBusy(false); } };
  const review = (value: LibraryCardPreview) => { pending.current = value.preview_id; setPreview(value); };
  return <CardDialog title={preview ? "核对角色卡" : editing ? "编辑角色设定" : "新建角色卡"} onClose={close} busy={busy} wide>
    {loading ? <p role="status">正在读取角色设定…</p> : preview ? <>
      <p>确认后保存到角色卡库。已经加入世界的副本保持各自的内容、聊天和经历。</p>
      {preview.shared && <><p>完整角色卡：包含双面设计和 {preview.image_count ?? 0} 份卡面图片，可在收藏后继续设计。</p><CardPresentationPreview client={client} cardId={preview.card_id} previewId={preview.preview_id} design={preview.design ?? defaultDesign({ name: preview.content.characters[0]?.name ?? "角色卡", design: null })} /></>}<CardReview item={preview.content} />
      <footer><button type="button" disabled={busy} onClick={() => void work(async () => { await client.discardLibraryPreview(preview.preview_id); pending.current = null; setPreview(null); })}>返回修改</button><button type="button" className={styles.gold} disabled={busy} onClick={() => void work(async () => { const saved = await client.confirmLibraryCard(preview); pending.current = null; dirty.current = false; await onSaved(saved); onClose(); })}>{busy ? "正在保存…" : preview.content.warnings?.some(item => item.code === "character_card_v2_fallback_review_required") ? "确认使用 V2 并保存到卡库" : "确认保存到卡库"}</button></footer>
    </> : <>
      {!editing && <section className={styles.import}><label>从文件导入<input type="file" accept=".json,.png,.apng,.charx" disabled={busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void work(async () => review(await client.previewLibraryImport(file))); }} /></label><small>支持角色卡 JSON、PNG、CHARX，最大32 MiB；先预览，再确认保存。</small></section>}
      <form onSubmit={event => { event.preventDefault(); void work(async () => review(await (initialCard.current ? client.previewLibraryChanges(initialCard.current, original.current, draft) : client.previewLibraryEditor(draft)))); }}>
        <fieldset disabled={busy || loading || readFailed} className={styles.authorFields}>
          <label>角色名称<input required maxLength={300} value={draft.name} onChange={event => change({ name: event.target.value })} /></label>
          {([ ["description", "人物描述"], ["personality", "性格"], ["background", "背景"], ["scenario", "场景"], ["speech_guidance", "说话方式"], ["first_message", "开场白"], ["creator_notes", "创作者备注"] ] as const).map(([key, title]) => <label key={key}>{title}<textarea aria-label={title} maxLength={16000} rows={key === "description" ? 4 : 2} value={draft[key]} onChange={event => change({ [key]: event.target.value })} /></label>)}
          <label>标签（每行一个）<textarea rows={2} value={draft.tags.join("\n")} onChange={event => change({ tags: event.target.value.split("\n").filter(item => item.trim()) })} /></label>
          <section><h3>示例对话</h3>{draft.example_dialogue.map((text, index) => <label key={index}>示例 {index + 1}<textarea maxLength={8000} value={text} onChange={event => change({ example_dialogue: draft.example_dialogue.map((item, i) => i === index ? event.target.value : item) })} /><button type="button" onClick={() => change({ example_dialogue: draft.example_dialogue.filter((_, i) => i !== index) })}>删除此示例</button></label>)}<button type="button" disabled={draft.example_dialogue.length >= 32} onClick={() => change({ example_dialogue: [...draft.example_dialogue, ""] })}>添加示例对话</button></section>
          <p>附带世界书和原文件扩展会保留。这里保存的是角色设定，不会改变世界事实，也不调用模型。</p>
        </fieldset><footer><button type="button" disabled={busy} onClick={close}>取消</button><button className={styles.gold} type="submit" disabled={busy || !draft.name.trim() || loading || readFailed}>{busy ? "正在准备…" : "预览角色设定"}</button></footer>
      </form>
    </>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
  </CardDialog>;
}
