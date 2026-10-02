import { useCallback, useEffect, useRef, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import "react-easy-crop/react-easy-crop.css";
import { CoreClient, CoreRequestError, type CoverCrop, type CoverFace, type CoverImage, type WorldCover, type WorldCoverWrite, type WorldSettings } from "@dreamtalk/api-client";
import { BookFaces, type BookAppearance } from "./BookFaces";
import { coverPreview } from "./coverPreview";
import "./world-cover.css";

type FaceDraft = { source: CoverImage; url: string; crop?: CoverCrop };
const FACES: CoverFace[] = ["front", "spine", "back"];
const LABELS = { front: "正面", spine: "书脊", back: "背面" };
const SIZES = { front: [980, 1430], spine: [210, 1430], back: [980, 1430] } as const;

function FaceCropper({ face, draft, disabled, onCrop, onPending }: {
  face: CoverFace; draft: FaceDraft; disabled: boolean;
  onCrop: (face: CoverFace, crop: CoverCrop, changed: boolean, preview?: boolean) => void; onPending: (pending: boolean) => void;
}) {
  const [point, setPoint] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState<CoverCrop["rotation"]>(draft.crop?.rotation ?? 0);
  const [initialArea, setInitialArea] = useState<Area | undefined>(draft.crop);
  const touched = useRef(false);
  const ratio = SIZES[face][0] / SIZES[face][1];
  const changed = () => { touched.current = true; };
  return <>
    <div className={`cover-crop-stage ${disabled ? "is-disabled" : ""}`} onKeyDownCapture={event => { if (disabled) { event.preventDefault(); event.stopPropagation(); } }}>
      <Cropper image={draft.url} aspect={ratio} crop={point} zoom={zoom} rotation={rotation}
        initialCroppedAreaPercentages={initialArea} maxZoom={5} objectFit="contain" disableAutomaticStylesInjection
        cropperProps={{ tabIndex: disabled ? -1 : 0, "aria-label": `裁剪${LABELS[face]}图片，方向键移动图片` }} onCropChange={setPoint} onZoomChange={setZoom} onInteractionStart={changed}
        onCropAreaChange={area => { onCrop(face, { ...area, rotation }, touched.current, false); onPending(false); }}
        onCropComplete={area => {
          const rounded = { x: area.x, y: area.y, width: area.width, height: area.height };
          onCrop(face, { ...rounded, rotation }, touched.current); onPending(false);
        }} />
    </div>
    <div className="cover-crop-tools">
      <label htmlFor="cover-zoom">缩放</label><input id="cover-zoom" type="range" min={1} max={5} step={.01} value={zoom} disabled={disabled}
        onChange={event => { changed(); setZoom(Number(event.target.value)); }} />
      <button type="button" className="secondary-button" disabled={disabled} onClick={() => {
        changed(); onPending(true); setInitialArea(undefined); setPoint({ x: 0, y: 0 }); setZoom(1); setRotation(value => ((value + 90) % 360) as CoverCrop["rotation"]);
      }}>旋转 90°</button>
      <button type="button" className="text-action" disabled={disabled} onClick={() => {
        changed(); if (draft.crop) onCrop(face, draft.crop, true, false); onPending(false); setInitialArea(undefined); setPoint({ x: 0, y: 0 }); setZoom(1); setRotation(0);
      }}>重置裁剪</button>
    </div>
    <p className="cover-hint">拖动图片选择保留的区域，滚轮或滑杆缩放。{LABELS[face]}建议 {SIZES[face][0]} × {SIZES[face][1]} 像素。</p>
  </>;
}

function failureMessage(error: unknown) {
  if (error instanceof CoreRequestError) {
    if (error.status === 409) return "封面已被其他编辑更新。草稿仍保留；可重新读取已保存封面后再编辑。";
    if (error.code === "cover_image_size_limit" || error.status === 413) return "图片太大，请选择不超过 10 MB 的图片。";
    if (error.code === "cover_image_dimensions_limit") return "图片尺寸过大或包含动画，请使用不超过 2000 万像素、最长边 10000 像素的静态图片。";
    if (error.code === "cover_crop_invalid") return "裁剪区域尚未准备好，请重新调整图片后保存。";
    if (error.code === "cover_image_invalid" || error.status === 415) return "图片无法读取。请使用有效的 JPG、PNG 或 WebP 静态图片。";
  }
  return "未能完成操作。草稿仍保留，请检查核心连接后重试。";
}
function sameCrop(a: CoverCrop, b: CoverCrop) {
  return (["x", "y", "width", "height", "rotation"] as const).every(key => Math.abs(a[key] - b[key]) < .000001);
}
function sameSaved(value: WorldCover, draft: WorldCoverWrite) {
  return value.revision === draft.expected_revision + 1 && value.mode === draft.mode && value.title === draft.title &&
    value.show_title === draft.show_title && FACES.every(face => {
      const a = value.faces[face], b = draft.faces[face];
      return !a && !b || Boolean(a && b && a.source.digest === b.source_digest && sameCrop(a.crop, b.crop));
    });
}

export function WorldCoverEditor({ client, world, onDirty, onBusy, onSaved, onClose }: {
  client: CoreClient; world: WorldSettings; onDirty: (dirty: boolean) => void; onBusy: (busy: boolean) => void;
  onSaved: (cover: WorldCover) => void; onClose: () => void;
}) {
  const [cover, setCover] = useState<WorldCover | null>(null);
  const [mode, setMode] = useState<"text" | "image">("text");
  const [title, setTitle] = useState(world.name);
  const [showTitle, setShowTitle] = useState(true);
  const [faces, setFaces] = useState<Partial<Record<CoverFace, FaceDraft>>>({});
  const latestFaces = useRef(faces); latestFaces.current = faces;
  const [previews, setPreviews] = useState<BookAppearance["urls"]>({});
  const [face, setFace] = useState<CoverFace>("front");
  const [view, setView] = useState<CoverFace>("front");
  const [busy, setBusy] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [cropKey, setCropKey] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const operation = useRef(false);
  const controller = useRef(new AbortController());
  const urls = useRef(new Set<string>());
  const previewTimers = useRef<Partial<Record<CoverFace, number>>>({});
  const previewEpoch = useRef<Record<CoverFace, number>>({ front: 0, spine: 0, back: 0 });
  const dirtyCallback = useRef(onDirty); dirtyCallback.current = onDirty;
  const busyCallback = useRef(onBusy); busyCallback.current = onBusy;
  const markDirty = () => { setDirty(true); dirtyCallback.current(true); setNotice(""); };
  const setWorking = (value: boolean) => { operation.current = value; setBusy(value); busyCallback.current(value); };
  const makeUrl = useCallback((blob: Blob) => { const url = URL.createObjectURL(blob); urls.current.add(url); return url; }, []);
  useEffect(() => {
    mounted.current = true; const owned = urls.current; const timers = previewTimers.current;
    heading.current?.scrollIntoView({ block: "start" }); heading.current?.focus({ preventScroll: true });
    return () => { mounted.current = false; Object.values(timers).forEach(window.clearTimeout); controller.current.abort(); owned.forEach(url => URL.revokeObjectURL(url)); owned.clear(); dirtyCallback.current(false); busyCallback.current(false); };
  }, []);
  useEffect(() => {
    const abort = new AbortController(); controller.current = abort;
    operation.current = true; busyCallback.current(true);
    const load = async () => {
      setBusy(true); setError("");
      try {
        const saved = await client.worldCover(world.world_id, abort.signal);
        const sources: Partial<Record<CoverFace, FaceDraft>> = {}, displays: BookAppearance["urls"] = {};
        for (const face of FACES) {
          const image = saved.faces[face]; if (!image) continue;
          const original = await client.coverImage(world.world_id, image.source.digest, abort.signal);
          const display = await client.coverImage(world.world_id, image.display.digest, abort.signal);
          if (abort.signal.aborted) return;
          sources[face] = { source: image.source, url: makeUrl(original), crop: image.crop };
          displays[face] = makeUrl(display);
        }
        if (abort.signal.aborted) return;
        FACES.forEach(face => { previewEpoch.current[face] += 1; });
        setCover(saved); setTitle(saved.title); setMode(saved.mode); setShowTitle(saved.show_title);
        setFaces(sources); setPreviews(displays); setDirty(false); dirtyCallback.current(false); setCropKey(value => value + 1);
      } catch (failure) { if (!abort.signal.aborted) setError(failureMessage(failure)); }
      finally { if (!abort.signal.aborted) { operation.current = false; setBusy(false); busyCallback.current(false); } }
    };
    void load(); return () => abort.abort();
  }, [client, world.world_id, reload, makeUrl]);
  const updateCrop = useCallback((which: CoverFace, crop: CoverCrop, changed: boolean, preview = true) => {
    const source = faces[which];
    if (!source || latestFaces.current[which]?.source.digest !== source.source.digest) return;
    setFaces(current => current[which]?.source.digest === source.source.digest ? { ...current, [which]: { ...current[which]!, crop } } : current);
    const original = cover?.faces[which];
    if (changed && (!original || original.source.digest !== faces[which]?.source.digest || !sameCrop(original.crop, crop))) {
      setDirty(true); dirtyCallback.current(true); setNotice("");
    }
    window.clearTimeout(previewTimers.current[which]);
    const epoch = ++previewEpoch.current[which];
    const generate = () => { void coverPreview(source.url, crop, SIZES[which][0], SIZES[which][1]).then(blob => {
      if (mounted.current && epoch === previewEpoch.current[which]) setPreviews(current => {
        const previous = current[which]; if (previous) { URL.revokeObjectURL(previous); urls.current.delete(previous); }
        return { ...current, [which]: makeUrl(blob) };
      });
    }).catch(() => { if (mounted.current && epoch === previewEpoch.current[which]) setError("预览暂时无法生成，请重新选择图片。原图仍保留。"); }); };
    if (preview) generate(); else previewTimers.current[which] = window.setTimeout(generate, 100);
  }, [faces, makeUrl, cover]);
  const upload = async (file: File | undefined) => {
    if (!file || operation.current || !cover) return;
    const extension = /\.(jpe?g|png|webp)$/i.test(file.name);
    if (!extension || file.type && !["image/jpeg", "image/png", "image/webp"].includes(file.type)) { setError("请选择 JPG、PNG 或 WebP 图片。"); return; }
    if (file.size > 10 * 1024 * 1024) { setError("每张图片不能超过 10 MB。"); return; }
    const target = face;
    setWorking(true); setError(""); setNotice("");
    try {
      const source = await client.uploadCoverImage(world.world_id, file, controller.current.signal);
      if (!mounted.current) return;
      previewEpoch.current[target] += 1;
      setFaces(current => ({ ...current, [target]: { source, url: makeUrl(file) } }));
      setPreviews(current => { const next = { ...current }; delete next[target]; return next; });
      setPending(true); setCropKey(value => value + 1); markDirty();
    } catch (failure) { if (mounted.current) setError(failureMessage(failure)); }
    finally { if (mounted.current) setWorking(false); }
  };
  const save = async () => {
    if (operation.current || !cover || pending || !title.trim() || mode === "image" && !faces.front) return;
    const draft: WorldCoverWrite = { mode, title: title.trim(), show_title: showTitle, faces: {}, expected_revision: cover.revision };
    for (const face of FACES) { const value = faces[face]; if (value) {
      if (!value.crop) { setError("图片裁剪尚未准备好，请选择该面并完成裁剪。"); return; }
      draft.faces[face] = { source_digest: value.source.digest, crop: value.crop };
    } }
    setWorking(true); setError(""); setNotice("");
    try {
      let result: WorldCover;
      try { result = await client.saveWorldCover(world.world_id, draft, controller.current.signal); }
      catch (failure) {
        // A lost response is resolved by a read; never repeat an uncertain write automatically.
        const saved = await client.worldCover(world.world_id, controller.current.signal).catch(() => null);
        if (!saved || !sameSaved(saved, draft)) throw failure;
        result = saved;
      }
      if (!mounted.current) return;
      setCover(result); setDirty(false); dirtyCallback.current(false); onSaved(result); setNotice("封面已保存，书架已更新。");
    } catch (failure) { if (mounted.current) setError(failureMessage(failure)); }
    finally { if (mounted.current) setWorking(false); }
  };
  const draft = faces[face];
  return <section className="archive-editor cover-editor" aria-label="编辑世界书封面" aria-busy={busy}>
    <div className="archive-editor-heading"><h2 ref={heading} tabIndex={-1}>「{world.name}」的封面</h2>
      <button type="button" className="text-action" disabled={busy} onClick={onClose}>{dirty ? "取消编辑" : "收起编辑"}</button></div>
    <div className="cover-editor-grid">
      <div className="cover-preview-pane"><p className="cover-eyebrow">封面预览</p>
        <div className={`cover-book-stage view-${view}`} aria-label={`${title || world.name}的${LABELS[view]}预览`}>
          <span className="book-volume"><BookFaces name={world.name} appearance={{ cover: { mode, title: title || world.name, show_title: showTitle }, urls: previews }} /></span>
        </div>
        <div className="cover-segment" aria-label="预览角度">{FACES.map(item => <button key={item} type="button" aria-pressed={view === item} onClick={() => setView(item)}>{LABELS[item]}</button>)}</div>
        <p className="cover-hint">左上角的 dreamtalk 始终保留。保存后才会应用到书架。</p>
      </div>
      <div className="cover-controls">
        {error && <p className="app-alert" role="alert">{error}</p>}{notice && <p className="app-notice" role="status">{notice}</p>}
        {!cover && busy ? <p role="status">正在读取封面…</p> : <>
          <div className="cover-segment" aria-label="封面方式"><button type="button" disabled={busy || !cover} aria-pressed={mode === "text"} onClick={() => { setMode("text"); setPending(false); markDirty(); }}>文字封面</button><button type="button" disabled={busy || !cover} aria-pressed={mode === "image"} onClick={() => { setMode("image"); setPending(false); setCropKey(value => value + 1); markDirty(); }}>图片封面</button></div>
          <label className="field"><span>封面标题</span><input maxLength={120} value={title} disabled={busy || !cover} onChange={event => { setTitle(event.target.value); markDirty(); }} placeholder={world.name} /></label>
          <p className="cover-hint">标题同步到正面和书脊，不会修改世界名称或世界书内容。</p>
          {mode === "image" && <>
            <label className="cover-check"><input type="checkbox" checked={showTitle} disabled={busy} onChange={event => { setShowTitle(event.target.checked); markDirty(); }} />在图片上显示封面标题</label>
            <div className="cover-face-tabs" aria-label="编辑书的各面">{FACES.map(item => <button key={item} type="button" disabled={busy || pending} aria-pressed={face === item} onClick={() => { setFace(item); setView(item); setCropKey(value => value + 1); }}>{LABELS[item]}<small>{faces[item] ? "已上传" : item === "front" ? "必选" : "可选"}</small></button>)}</div>
            <input ref={input} className="cover-file-input" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" disabled={busy || !cover} onChange={event => { void upload(event.target.files?.[0]); event.target.value = ""; }} />
            <div className={`cover-drop ${dragOver ? "is-over" : ""}`} onDragOver={event => { event.preventDefault(); if (!busy) setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={event => { event.preventDefault(); setDragOver(false); void upload(event.dataTransfer.files[0]); }}>
              <button type="button" className="secondary-button" disabled={busy || !cover} onClick={() => input.current?.click()}>{draft ? `更换${LABELS[face]}图片` : `选择${LABELS[face]}图片`}</button><span>也可以拖入图片 · JPG / PNG / WebP · 每张最多 10 MB</span>
              {draft && <button type="button" className="text-action" disabled={busy} onClick={() => {
                previewEpoch.current[face] += 1; setPending(false);
                setFaces(current => { const next = { ...current }; delete next[face]; return next; });
                setPreviews(current => { const next = { ...current }; delete next[face]; return next; }); markDirty();
              }}>移除图片</button>}
            </div>
            {draft ? <FaceCropper key={`${face}:${draft.source.digest}:${cropKey}`} face={face} draft={draft} disabled={busy} onCrop={updateCrop} onPending={setPending} /> : <p className="cover-empty">{face === "front" ? "先上传正面图片，再拖动和缩放裁剪。" : "这一面可暂时留空，使用白灰书体与封面标题。"}</p>}
            <p className="cover-hint">正面和背面比例 196:286，书脊比例 42:286。原图无需精确匹配，裁剪会保持比例。只上传正面也可以保存。</p>
          </>}
          <div className="cover-save-actions"><button type="button" className="primary-button" disabled={busy || !cover || !dirty || !title.trim() || pending || mode === "image" && !faces.front} onClick={() => void save()}>{busy ? "正在处理…" : "保存封面"}</button>
            <button type="button" className="text-action" disabled={busy} onClick={() => { if (!dirty || window.confirm("重新读取会放弃尚未保存的封面编辑，是否继续？")) { FACES.forEach(face => { previewEpoch.current[face] += 1; }); setPending(false); setReload(value => value + 1); } }}>重新读取已保存封面</button></div>
          <p className="cover-hint">图片与原图副本只保存在本机，不调用模型，也不发送到联网服务。</p>
        </>}
      </div>
    </div>
  </section>;
}
