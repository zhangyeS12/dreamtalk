import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import type { BookDesign, BookDesignSticker, CoreClient, CoverCrop, CoverFace, WorldCover, WorldCoverWrite, WorldSettings } from "@dreamtalk/api-client";
import { coverPreview } from "../../coverPreview";
import type { Sky } from "../sky";
import { FaceArt, type BookLook, type ShelfAppearance } from "./Book3D";
import { BOOK_FACE, BOOK_HEIGHT, BUILTIN_STICKERS, CASE_COLORS, FACE_LABELS, FONTS, INK_COLORS, MATERIALS, STICKER_LIMIT, TEMPLATES, THICKNESS, cloneDesign, designFor, sameValue, stickerSource, withTemplate, type DesignFace, type ShelfFace } from "./bookDesign";
import { FaceCropper, SIZES, failureMessage, type FaceDraft } from "./FaceCropper";
import styles from "./Designer.module.css";

type Item = { kind: "title" | "window" | "sticker"; index?: number };
const sameItem = (a: Item | null, b: Item) => !!a && a.kind === b.kind && a.index === b.index;
const FACES: DesignFace[] = ["front", "spine", "back"];

/**
 * Design a world's book: form, cover images, title, stickers and the sky window.
 * Edits preview live on the 3D book; nothing is written until “保存设计”.
 */
export function BookDesigner({ client, world, sky, face: shelfFace, onFaceRequest, onDraft, onDirty, onBusy, onSaved, onClose }: {
  client: CoreClient; world: WorldSettings; sky: Sky; face: ShelfFace; onFaceRequest: (face: ShelfFace) => void;
  onDraft: (draft: ShelfAppearance | null) => void; onDirty: (dirty: boolean) => void; onBusy: (busy: boolean) => void;
  onSaved: (cover: WorldCover) => void; onClose: () => void;
}) {
  const [cover, setCover] = useState<WorldCover | null>(null);
  const [design, setDesign] = useState<BookDesign>(() => designFor(undefined, world.name));
  const [history, setHistory] = useState<BookDesign[]>([]);
  const [future, setFuture] = useState<BookDesign[]>([]);
  const [images, setImages] = useState<Partial<Record<CoverFace, FaceDraft>>>({});
  const [previews, setPreviews] = useState<Partial<Record<CoverFace, string>>>({});
  const [uploads, setUploads] = useState<Record<string, string>>({});
  const [face, setFace] = useState<DesignFace>("front");
  const [imageFace, setImageFace] = useState<CoverFace>("front");
  const [picked, setPicked] = useState<Item | null>(null);
  const [busy, setBusyState] = useState(true);
  const [pending, setPending] = useState(false);
  const [dirty, setDirtyState] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cropKey, setCropKey] = useState(0);
  const urls = useRef(new Set<string>());
  const mounted = useRef(true);
  const controller = useRef(new AbortController());
  const imageInput = useRef<HTMLInputElement>(null);
  const stickerInput = useRef<HTMLInputElement>(null);
  const callbacks = useRef({ onDirty, onBusy, onDraft });
  callbacks.current = { onDirty, onBusy, onDraft };
  // Every object URL is owned here. A slot ("preview:front", "image:back", "sticker:<digest>") holds one
  // URL at a time; the URL it replaces is revoked shortly after, once the shelf shows the new one.
  const slots = useRef(new Map<string, string>());
  const slotUrl = useCallback((slot: string, blob: Blob) => {
    const url = URL.createObjectURL(blob), old = slots.current.get(slot);
    urls.current.add(url); slots.current.set(slot, url);
    if (old) releaseUrl(urls.current, old);
    return url;
  }, []);
  const clearSlot = (slot: string) => { const old = slots.current.get(slot); slots.current.delete(slot); if (old) releaseUrl(urls.current, old); };
  const setBusy = (value: boolean) => { setBusyState(value); callbacks.current.onBusy(value); };
  const markDirty = () => { setDirtyState(true); callbacks.current.onDirty(true); setNotice(""); };

  useEffect(() => {
    mounted.current = true; const owned = urls.current;
    return () => { mounted.current = false; controller.current.abort(); owned.forEach(url => URL.revokeObjectURL(url)); owned.clear();
      callbacks.current.onDirty(false); callbacks.current.onBusy(false); callbacks.current.onDraft(null); };
  }, []);
  // The canvas follows whichever face the reader turns toward (the fore-edge has nothing to design).
  useEffect(() => { if (shelfFace !== "edge") { setFace(shelfFace); setPicked(null); } }, [shelfFace]);

  const load = useCallback(async () => {
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError("");
    try {
      const saved = await client.worldCover(world.world_id, abort.signal);
      const sources: Partial<Record<CoverFace, FaceDraft>> = {}, displays: Partial<Record<CoverFace, string>> = {}, stickerUrls: Record<string, string> = {};
      for (const which of FACES) {
        const image = saved.faces[which]; if (!image) continue;
        const original = await client.coverImage(world.world_id, image.source.digest, abort.signal);
        const display = await client.coverImage(world.world_id, image.display.digest, abort.signal);
        if (abort.signal.aborted) return;
        sources[which] = { source: image.source, url: slotUrl(`image:${which}`, original), crop: image.crop };
        displays[which] = slotUrl(`preview:${which}`, display);
      }
      const next = designFor(saved, world.name);
      for (const digest of new Set(FACES.flatMap(which => next.stickers[which]).filter(item => item.kind === "image").map(item => item.ref))) {
        const blob = await client.coverImage(world.world_id, digest, abort.signal);
        if (abort.signal.aborted) return;
        stickerUrls[digest] = slotUrl(`sticker:${digest}`, blob);
      }
      setCover(saved); setDesign(next); setHistory([]); setFuture([]); setImages(sources); setPreviews(displays); setUploads(stickerUrls);
      setDirtyState(false); callbacks.current.onDirty(false); setCropKey(value => value + 1);
    } catch (failure) { if (!abort.signal.aborted) setError(failureMessage(failure)); }
    finally { if (!abort.signal.aborted && mounted.current) setBusy(false); }
  }, [client, world.world_id, world.name, slotUrl]);
  useEffect(() => { void load(); }, [load]);

  const look: BookLook = useMemo(() => ({ name: world.name, design, uploads, sky, paused: world.clock_state === "paused",
    art: { front: previews.front, spine: previews.spine, back: previews.back, jacket: images.front?.url,
      jacketAspect: images.front ? Number(images.front.source.width) / Number(images.front.source.height) : undefined } }),
  [design, images.front, previews, sky, uploads, world.clock_state, world.name]);
  useEffect(() => { if (cover) callbacks.current.onDraft({ design: look.design, art: look.art, uploads: look.uploads }); }, [cover, look]);

  // ---------- Edits with undo ----------
  // Drags fire faster than renders; edits always start from the latest draft.
  const latest = useRef(design);
  latest.current = design;
  const change = (edit: (draft: BookDesign) => void, record = true) => {
    const current = latest.current, next = cloneDesign(current); edit(next);
    if (record) { setHistory(list => [...list.slice(-79), current]); setFuture([]); }
    latest.current = next; setDesign(next); markDirty();
  };
  const checkpoint = () => { setHistory(list => [...list.slice(-79), latest.current]); setFuture([]); };
  const undo = () => { if (!history.length) return; setFuture(list => [design, ...list]); setDesign(history[history.length - 1]); setHistory(list => list.slice(0, -1)); markDirty(); };
  const redo = () => { if (!future.length) return; setHistory(list => [...list, design]); setDesign(future[0]); setFuture(list => list.slice(1)); markDirty(); };
  // ---------- Cover images (front required for wrap; each face optional) ----------
  const previewEpoch = useRef<Record<CoverFace, number>>({ front: 0, spine: 0, back: 0 });
  const updateCrop = useCallback((which: CoverFace, crop: CoverCrop, changed: boolean, preview = true) => {
    const source = images[which]; if (!source) return;
    setImages(current => current[which]?.source.digest === source.source.digest ? { ...current, [which]: { ...current[which]!, crop } } : current);
    if (changed) markDirty();
    if (!preview) return;
    const epoch = ++previewEpoch.current[which];
    void coverPreview(source.url, crop, SIZES[which][0], SIZES[which][1]).then(blob => {
      if (mounted.current && epoch === previewEpoch.current[which]) setPreviews(current => ({ ...current, [which]: slotUrl(`preview:${which}`, blob) }));
    }).catch(() => { if (mounted.current) setError("预览暂时无法生成，请重新选择图片。原图仍保留。"); });
  }, [images, slotUrl]);
  const validImage = (file: File) => {
    if (!/\.(jpe?g|png|webp)$/i.test(file.name) || file.type && !["image/jpeg", "image/png", "image/webp"].includes(file.type)) { setError("请选择 JPG、PNG 或 WebP 图片。"); return false; }
    if (file.size > 10 * 1024 * 1024) { setError("每张图片不能超过 10 MB。"); return false; }
    return true;
  };
  const uploadFace = async (file: File | undefined) => {
    if (!file || busy || !validImage(file)) return;
    const target = imageFace; setBusy(true); setError("");
    try {
      const source = await client.uploadCoverImage(world.world_id, file, controller.current.signal);
      if (!mounted.current) return;
      previewEpoch.current[target] += 1;
      setImages(current => ({ ...current, [target]: { source, url: slotUrl(`image:${target}`, file) } }));
      setPreviews(current => { const next = { ...current }; delete next[target]; return next; }); clearSlot(`preview:${target}`);
      setPending(true); setCropKey(value => value + 1); markDirty();
    } catch (failure) { if (mounted.current) setError(failureMessage(failure)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const removeFace = () => {
    previewEpoch.current[imageFace] += 1; setPending(false);
    setImages(current => { const next = { ...current }; delete next[imageFace]; return next; });
    setPreviews(current => { const next = { ...current }; delete next[imageFace]; return next; });
    clearSlot(`image:${imageFace}`); clearSlot(`preview:${imageFace}`);
    if (imageFace === "front" && design.wrap) change(draft => { draft.wrap = false; }); else markDirty();
  };

  // ---------- Stickers ----------
  const addSticker = (sticker: BookDesignSticker) => {
    const index = design.stickers[face].length, limit = STICKER_LIMIT[face];
    if (index >= limit) { setError(`这一面最多放 ${limit} 张贴纸。`); return; }
    change(draft => { draft.stickers[face].push(sticker); }); setPicked({ kind: "sticker", index });
  };
  const builtin = (ref: string) => addSticker({ kind: "builtin", ref, x: 50, y: face === "spine" ? 60 : 50, w: face === "spine" ? 80 : 26, r: 0, opacity: 1 });
  const uploadSticker = async (file: File | undefined) => {
    if (!file || busy || !validImage(file)) return;
    setBusy(true); setError("");
    try {
      const image = await client.uploadCoverImage(world.world_id, file, controller.current.signal);
      if (!mounted.current) return;
      setUploads(current => ({ ...current, [image.digest]: slotUrl(`sticker:${image.digest}`, file) }));
      addSticker({ kind: "image", ref: image.digest, x: 50, y: 50, w: face === "spine" ? 80 : 34, r: 0, opacity: 1 });
    } catch (failure) { if (mounted.current) setError(failureMessage(failure)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const removeItem = (item: Item) => {
    change(draft => {
      if (item.kind === "title") draft.title.text = "";
      else if (item.kind === "window") draft.sky_window.on = false;
      else draft.stickers[face].splice(item.index!, 1);
    });
    setPicked(null);
  };
  const reorder = (index: number, by: number) => {
    const list = design.stickers[face], to = index + by; if (to < 0 || to >= list.length) return;
    change(draft => { const [moved] = draft.stickers[face].splice(index, 1); draft.stickers[face].splice(to, 0, moved); });
    setPicked({ kind: "sticker", index: to });
  };

  const applyTemplate = (key: string) => {
    const next = withTemplate(latest.current, key), plain = TEMPLATES[key].build("");
    const count = (value: BookDesign) => FACES.reduce((sum, which) => sum + value.stickers[which].length, 0);
    const kept = count(next) - count(plain);
    change(draft => { Object.assign(draft, next); });
    setPicked(null);
    if (kept) setNotice("已换用模板。你放的贴纸都保留着；不满意可以撤销。");
  };

  // ---------- Save ----------
  const save = async () => {
    if (busy || !cover || pending) return;
    const draft: WorldCoverWrite = { mode: images.front ? "image" : "text", title: design.title.text.trim(), show_title: Boolean(design.title.text.trim()),
      faces: {}, expected_revision: cover.revision, design: { ...design, wrap: design.wrap && Boolean(images.front) } };
    for (const which of FACES) {
      const value = images[which];
      if (!value) continue;
      if (!value.crop) { setError(`${FACE_LABELS[which]}图片的裁剪尚未准备好，请在“封面图片”里完成裁剪。`); return; }
      draft.faces[which] = { source_digest: value.source.digest, crop: value.crop };
    }
    setBusy(true); setError(""); setNotice("");
    try {
      let result: WorldCover;
      try { result = await client.saveWorldCover(world.world_id, draft, controller.current.signal); }
      catch (failure) {
        // A lost response is resolved by reading back; never repeat an uncertain write.
        const saved = await client.worldCover(world.world_id, controller.current.signal).catch(() => null);
        if (!saved || saved.revision !== draft.expected_revision + 1 || !sameValue(saved.design, draft.design)) throw failure;
        result = saved;
      }
      if (!mounted.current) return;
      setCover(result); setDirtyState(false); callbacks.current.onDirty(false); onSaved(result); setNotice("设计已保存，书架已更新。");
    } catch (failure) { if (mounted.current) setError(failureMessage(failure)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const cancel = () => { if (!dirty || window.confirm("放弃尚未保存的设计？")) { setDirtyState(false); callbacks.current.onDirty(false); onClose(); } };
  // ---------- Canvas: drag to move, corner to scale and rotate ----------
  const canvas = useRef<HTMLDivElement>(null);
  const faceWidth = face === "spine" ? THICKNESS[design.thickness] : BOOK_FACE;
  const scale = Math.min(320 / faceWidth, 470 / BOOK_HEIGHT);
  const grab = (event: ReactPointerEvent<HTMLElement>, item: Item) => {
    event.preventDefault(); event.stopPropagation();
    const box = canvas.current?.getBoundingClientRect(); if (!box) return;
    setPicked(item); checkpoint();
    const start = latest.current, resizing = (event.target as HTMLElement).dataset.handle === "resize";
    const origin = item.kind === "title" ? start.title : item.kind === "window" ? start.sky_window : start.stickers[face][item.index!];
    const cx = box.left + origin.x / 100 * box.width, cy = box.top + origin.y / 100 * box.height;
    const from = { x: event.clientX, y: event.clientY, distance: Math.max(4, Math.hypot(event.clientX - cx, event.clientY - cy)), angle: Math.atan2(event.clientY - cy, event.clientX - cx) };
    const move = (moveEvent: PointerEvent) => change(draft => {
      if (resizing && item.kind !== "title") {
        const k = Math.hypot(moveEvent.clientX - cx, moveEvent.clientY - cy) / from.distance;
        if (item.kind === "window") { draft.sky_window.w = Math.max(4, Math.min(100, start.sky_window.w * k)); draft.sky_window.h = Math.max(4, Math.min(100, start.sky_window.h * k)); }
        else {
          const target = draft.stickers[face][item.index!], base = start.stickers[face][item.index!];
          target.w = Math.max(2, Math.min(160, base.w * k));
          target.r = Math.max(-720, Math.min(720, Math.round(base.r + (Math.atan2(moveEvent.clientY - cy, moveEvent.clientX - cx) - from.angle) * 180 / Math.PI)));
        }
        return;
      }
      const dx = (moveEvent.clientX - from.x) / box.width * 100, dy = (moveEvent.clientY - from.y) / box.height * 100;
      const target = item.kind === "title" ? draft.title : item.kind === "window" ? draft.sky_window : draft.stickers[face][item.index!];
      const limit = item.kind === "sticker" ? [-20, 120] : [0, 100];
      target.x = Math.max(limit[0], Math.min(limit[1], origin.x + dx)); target.y = Math.max(limit[0], Math.min(limit[1], origin.y + dy));
    }, false);
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const flat: BookLook = { ...look, design: { ...design, stickers: { front: [], spine: [], back: [] } } };
  const editable: Array<{ item: Item; label: string; style: CSSProperties; src?: string }> = [];
  if (face === "front" && design.title.text) editable.push({ item: { kind: "title" }, label: "书名", style: { left: `${design.title.x}%`, top: `${design.title.y}%`, width: design.title.vertical ? "16%" : "64%", height: design.title.vertical ? "54%" : "12%" } });
  if (face === "front" && design.sky_window.on) editable.push({ item: { kind: "window" }, label: "天窗", style: { left: `${design.sky_window.x}%`, top: `${design.sky_window.y}%`, width: `${design.sky_window.w}%`, height: `${design.sky_window.h}%` } });
  design.stickers[face].forEach((sticker, index) => editable.push({ item: { kind: "sticker", index }, label: sticker.kind === "builtin" ? BUILTIN_STICKERS[sticker.ref]?.label ?? "贴纸" : "我的图片",
    src: stickerSource(sticker, uploads), style: { left: `${sticker.x}%`, top: `${sticker.y}%`, width: `${sticker.w}%`, opacity: sticker.opacity, transform: `translate(-50%, -50%) rotate(${sticker.r}deg)` } }));
  const pickedSticker = picked?.kind === "sticker" ? design.stickers[face][picked.index!] : undefined;
  const color = (value: string, label: string, onPick: (value: string) => void, list: string[]) => <div className={styles.swatches} role="group" aria-label={label}>
    {list.map(item => <button key={item} type="button" className={styles.swatch} style={{ background: item }} aria-label={`${label} ${item}`} aria-pressed={value.toLowerCase() === item} onClick={() => onPick(item)} />)}
    <label className={styles.custom} title="自定义颜色"><input type="color" value={value} aria-label={`自定义${label}`} onChange={event => onPick(event.target.value)} /></label>
  </div>;
  const segment = <T extends string>(label: string, value: T, options: Array<[T, string]>, onPick: (value: T) => void) => <div className={styles.segment} role="group" aria-label={label}>
    {options.map(([key, text]) => <button key={key} type="button" aria-pressed={value === key} onClick={() => onPick(key)}>{text}</button>)}
  </div>;
  const image = images[imageFace];
  return <section className={styles.designer} aria-label={`设计「${world.name}」这本书`} aria-busy={busy}
    onKeyDown={event => {
      if ((event.target as HTMLElement).closest("input, select, textarea")) return;
      if (event.key === "Escape") { event.preventDefault(); cancel(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
      if ((event.key === "Delete" || event.key === "Backspace") && picked) { event.preventDefault(); removeItem(picked); }
    }}>
    <div className={styles.dim} aria-hidden="true" />
    <div className={styles.canvasWrap}>
      <span className={styles.canvasLabel}>{FACE_LABELS[face]} · 拖动调整位置，拖右下角圆点缩放和旋转</span>
      <div ref={canvas} className={styles.canvas} style={{ width: faceWidth * scale, height: BOOK_HEIGHT * scale }}
        onPointerDown={event => { if (event.target === event.currentTarget || (event.target as HTMLElement).dataset.paper !== undefined) setPicked(null); }}>
        <span data-paper="" className={styles.paper} style={{ width: faceWidth, height: BOOK_HEIGHT, transform: `scale(${scale})`, "--T": `${faceWidth}px` } as CSSProperties}><FaceArt look={flat} face={face} stickers={false} /></span>
        <span className={styles.safe} aria-hidden="true" />
        {editable.map(({ item, label, style, src }) => <div key={`${item.kind}:${item.index ?? ""}`} className={styles.item} data-picked={sameItem(picked, item) || undefined}
          style={item.kind === "sticker" ? style : { ...style, transform: "translate(-50%, -50%)" }} onPointerDown={event => grab(event, item)}
          role="button" tabIndex={0} aria-label={`选择${label}`} onFocus={() => setPicked(item)}>
          {src && <img src={src} alt="" draggable={false} />}
          {item.kind !== "title" && <span className={styles.handle} data-handle="resize" title="缩放和旋转" />}
          <button type="button" className={styles.remove} aria-label={`删除${label}`} onPointerDown={event => { event.stopPropagation(); removeItem(item); }}>×</button>
        </div>)}
      </div>
    </div>

    <div className={styles.panel}>
      {error && <p className={styles.error} role="alert">{error}</p>}
      {notice && <p className={styles.notice} role="status">{notice}</p>}
      {!cover && busy ? <p role="status">正在读取这本书的设计…</p> : <>
        <h3>从模板开始</h3>
        <div className={styles.templates}>{Object.entries(TEMPLATES).map(([key, template]) => { const preview = template.build("");
          return <button key={key} type="button" aria-pressed={design.template === key} style={{ background: preview.case_color, color: preview.title.color }}
            onClick={() => applyTemplate(key)}>{template.label}</button>; })}</div>

        <h3>书的形体</h3>
        {segment("材质", design.material, MATERIALS, value => change(draft => { draft.material = value; }))}
        {color(design.case_color, "书壳颜色", value => change(draft => { draft.case_color = value; }), CASE_COLORS)}
        {segment("厚度", design.thickness, [["thin", "薄"], ["normal", "标准"], ["thick", "厚"]], value => change(draft => { draft.thickness = value; }))}
        <label className={styles.toggle}>书口刷金边<input type="checkbox" checked={design.edge === "gilt"} onChange={event => change(draft => { draft.edge = event.target.checked ? "gilt" : "paper"; })} /></label>
        <label className={styles.toggle}>整体书衣：正面图片包住背面、书脊和正面<input type="checkbox" checked={design.wrap} disabled={!images.front} onChange={event => change(draft => { draft.wrap = event.target.checked; })} /></label>

        <h3>封面图片</h3>
        {segment("编辑哪一面的图片", imageFace, FACES.map(item => [item, `${FACE_LABELS[item]}${images[item] ? " ✓" : ""}`] as [CoverFace, string]), value => { if (!pending) { setImageFace(value); setCropKey(key => key + 1); } })}
        <div className={styles.row}>
          <button type="button" className={styles.ghost} disabled={busy || !cover} onClick={() => imageInput.current?.click()}>{image ? `更换${FACE_LABELS[imageFace]}图片` : `选择${FACE_LABELS[imageFace]}图片`}</button>
          {image && <button type="button" className={styles.link} disabled={busy} onClick={removeFace}>移除图片</button>}
        </div>
        <input ref={imageInput} hidden type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={event => { void uploadFace(event.target.files?.[0]); event.target.value = ""; }} />
        {image && <div className={styles.crop}><FaceCropper key={`${imageFace}:${image.source.digest}:${cropKey}`} face={imageFace} draft={image} disabled={busy} onCrop={updateCrop} onPending={setPending} /></div>}

        <h3>书名</h3>
        <input className={styles.text} type="text" maxLength={60} value={design.title.text} aria-label="书名文字" placeholder="留空则不显示书名"
          onFocus={checkpoint} onChange={event => change(draft => { draft.title.text = event.target.value; }, false)} />
        <div className={styles.row}>
          <select className={styles.select} aria-label="字体" value={design.title.font} onChange={event => change(draft => { draft.title.font = event.target.value as BookDesign["title"]["font"]; })}>
            {Object.entries(FONTS).map(([key, font]) => <option key={key} value={key}>{font.label}</option>)}</select>
          {segment("排列方向", design.title.vertical ? "v" : "h", [["h", "横排"], ["v", "竖排"]], value => change(draft => { draft.title.vertical = value === "v"; }))}
        </div>
        {color(design.title.color, "文字颜色", value => change(draft => { draft.title.color = value; }), INK_COLORS)}
        <label className={styles.range}>大小<input type="range" min={14} max={80} value={design.title.size} onPointerDown={checkpoint} onChange={event => change(draft => { draft.title.size = Number(event.target.value); }, false)} /></label>

        <h3>贴纸 · 贴在{FACE_LABELS[face]}</h3>
        <div className={styles.tray}>{Object.entries(BUILTIN_STICKERS).map(([key, item]) => <button key={key} type="button" aria-label={`添加贴纸：${item.label}`} title={item.label} onClick={() => builtin(key)}><img src={item.src} alt="" /></button>)}
          <button type="button" className={styles.upload} disabled={busy || !cover} onClick={() => stickerInput.current?.click()}>上传图片</button></div>
        <input ref={stickerInput} hidden type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={event => { void uploadSticker(event.target.files?.[0]); event.target.value = ""; }} />
        {pickedSticker && <label className={styles.range}>透明度<input type="range" min={10} max={100} value={Math.round(pickedSticker.opacity * 100)} onPointerDown={checkpoint}
          onChange={event => change(draft => { draft.stickers[face][picked!.index!].opacity = Number(event.target.value) / 100; }, false)} /></label>}

        <h3>更多</h3>
        <label className={styles.toggle}>天窗：封面上显示这个世界此刻的天色<input type="checkbox" checked={design.sky_window.on} onChange={event => change(draft => { draft.sky_window.on = event.target.checked; })} /></label>
        <label className={styles.toggle}>显示 dreamtalk 标识<input type="checkbox" checked={design.brand} onChange={event => change(draft => { draft.brand = event.target.checked; })} /></label>

        <h3>{FACE_LABELS[face]}的图层</h3>
        <ol className={styles.layers}>{editable.length ? editable.map(({ item, label, src }) => <li key={`${item.kind}:${item.index ?? ""}`} data-picked={sameItem(picked, item) || undefined}>
          <button type="button" className={styles.layerName} onClick={() => setPicked(item)}>{src && <img src={src} alt="" />}{label}</button>
          {item.kind === "sticker" && <><button type="button" aria-label={`${label}上移一层`} onClick={() => reorder(item.index!, 1)}>↑</button><button type="button" aria-label={`${label}下移一层`} onClick={() => reorder(item.index!, -1)}>↓</button></>}
          <button type="button" aria-label={`删除${label}`} onClick={() => removeItem(item)}>×</button>
        </li>) : <li><span className={styles.layerName}>这一面还没有图层，从上面添加贴纸。</span></li>}</ol>
        <p className={styles.hint}>图片、贴纸和原图副本只保存在本机，不调用模型，也不会上传到联网服务。</p>
      </>}
    </div>

    <div className={styles.footer}>
      <button type="button" disabled={!history.length || busy} onClick={undo}>撤销</button>
      <button type="button" disabled={!future.length || busy} onClick={redo}>重做</button>
      <button type="button" disabled={busy} onClick={() => onFaceRequest("front")}>回到正面</button>
      <button type="button" disabled={busy} onClick={cancel}>{dirty ? "取消" : "收起"}</button>
      <button type="button" className={styles.save} disabled={busy || !cover || !dirty || pending} onClick={() => void save()}>{busy ? "正在处理…" : "保存设计"}</button>
    </div>
  </section>;
}

function releaseUrl(owned: Set<string>, url: string) {
  window.setTimeout(() => { if (owned.delete(url)) URL.revokeObjectURL(url); }, 1500);
}
