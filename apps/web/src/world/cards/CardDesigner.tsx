import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { type CardFaceDesign, type CardLayer, type CoreClient, type CoverCrop, type LibraryCardItem } from "@dreamtalk/api-client";
import { failureMessage } from "../archive/FaceCropper";
import { CardFace, useCardImages } from "./CardFaces";
import { CardCropper } from "./CardCropper";
import { CARD_THEMES, clamp, defaultDesign, layer, STICKERS, symmetricFace, type CardSide } from "./cardDesign";
import { trapTab } from "../focusTrap";
import styles from "./Cards.module.css";

export function CardDesigner({ client, card, onSaved, onClose }: { client: CoreClient; card: LibraryCardItem; onSaved: (card: LibraryCardItem) => void; onClose: () => void }) {
  const [design, setDesign] = useState(() => defaultDesign(card)), [side, setSide] = useState<CardSide>("front");
  const initial = useRef(JSON.stringify(design)), editor = useRef<HTMLDivElement>(null), canvas = useRef<HTMLButtonElement>(null);
  const [selected, setSelected] = useState<string | null>(null), [undo, setUndo] = useState<CardFaceDesign | null>(null);
  const [busy, setBusy] = useState(false), busyRef = useRef(false), [error, setError] = useState("");
  const [crop, setCrop] = useState<{ url: string; digest: string; initial: CoverCrop | null; side: CardSide } | null>(null);
  const drag = useRef<{ id: number; x: number; y: number; layer: CardLayer; width: number; height: number } | null>(null);
  const images = useCardImages(client, card.card_id, design), face = design[side], component = face.layers.find(item => item.id === selected);
  useEffect(() => { const previous = document.activeElement; editor.current?.querySelector<HTMLHeadingElement>("h2")?.focus({ preventScroll: true }); return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true }); }; }, []);
  useEffect(() => () => { if (crop) URL.revokeObjectURL(crop.url); }, [crop]);
  const close = () => { if (!busyRef.current && (JSON.stringify(design) === initial.current || window.confirm("卡面尚未保存，放弃这些修改？"))) onClose(); };
  const changeFace = (change: Partial<CardFaceDesign>) => setDesign(current => ({ ...current, [side]: { ...current[side], ...change } }));
  const changeLayer = (change: Partial<CardLayer>) => changeFace({ layers: face.layers.map(item => item.id === selected ? { ...item, ...change } : item) });
  const add = (kind: CardLayer["kind"], text: string) => { if (face.layers.length >= 24) return; const item = layer(kind, text, 50, 50, kind === "sticker" ? 42 : 20, face.accent); changeFace({ layers: [...face.layers, item] }); setSelected(item.id); };
  const work = async (action: () => Promise<void>) => { if (busyRef.current) return; busyRef.current = true; setBusy(true); setError(""); try { await action(); } catch (failure) { setError(failureMessage(failure).replaceAll("封面", "卡面")); } finally { busyRef.current = false; setBusy(false); } };
  const upload = (file: File) => void work(async () => { const image = await client.uploadLibraryImage(card.card_id, file); setCrop({ url: URL.createObjectURL(file), digest: image.digest, initial: null, side }); });
  const recrop = () => void work(async () => { const digest = face.source_digest; if (!digest) return; const blob = await client.libraryImage(card.card_id, digest); setCrop({ url: URL.createObjectURL(blob), digest, initial: face.crop, side }); });
  const apply = (selection: CoverCrop) => void work(async () => { if (!crop) return; const image = await client.cropLibraryImage(card.card_id, crop.digest, selection); setDesign(current => ({ ...current, [crop.side]: { ...current[crop.side], source_digest: crop.digest, image_digest: image.digest, crop: selection } })); setCrop(null); });
  const layerDown = (event: ReactPointerEvent, item: CardLayer) => {
    if (busy) return; event.preventDefault(); event.stopPropagation(); setSelected(item.id);
    const bounds = canvas.current!.getBoundingClientRect(); event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, layer: item, width: bounds.width, height: bounds.height };
  };
  return <div ref={editor} className={styles.designer} role="dialog" aria-modal="true" aria-label="设计角色卡面" onKeyDown={event => { if (crop) return; if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); } else trapTab(event); }}>
    <div className={styles.designView}>
      <button type="button" aria-label="角色卡设计预览" ref={canvas} data-card-canvas className={styles.canvas} onPointerMove={event => { const current = drag.current; if (!current || current.id !== event.pointerId) return; setDesign(previous => ({ ...previous, [side]: { ...previous[side], layers: previous[side].layers.map(item => item.id === current.layer.id ? { ...item, x: clamp(current.layer.x + (event.clientX - current.x) / current.width * 100, 0, 100), y: clamp(current.layer.y + (event.clientY - current.y) / current.height * 100, 0, 100) } : item) } })); }}
        onPointerUp={event => { drag.current = null; if (event.target instanceof Element && event.target.hasPointerCapture(event.pointerId)) event.target.releasePointerCapture(event.pointerId); }} onPointerCancel={() => { drag.current = null; }}>
        <CardFace design={design} face={face} image={images[face.image_digest ?? ""]} side={side} editing selectedLayer={selected ?? undefined} onLayer={layerDown} />
      </button>
    </div>
    <div className={styles.designIdentity}><h2>{design.display_name}</h2><p>{design.subtitle}</p></div>
    <p className={styles.designHint}>卡片位置固定，可拖动卡面上的组件</p>
    <aside className={styles.designPanel}><header><div><small>让每次相遇都有自己的模样</small><h2 tabIndex={-1}>角色卡设计</h2></div><button type="button" aria-label="关闭设计器" disabled={busy} onClick={close}>×</button></header>
      <fieldset disabled={busy} className={styles.designScroll}>
        <div className={styles.faceTabs}>{(["front", "back"] as const).map(value => <button key={value} type="button" aria-pressed={side === value} onClick={() => { setSide(value); setSelected(null); }}>{value === "front" ? "正面" : "背面"}</button>)}</div>
        <div className={styles.symmetryTools}><button type="button" onClick={() => { setUndo(structuredClone(design.back)); setDesign(current => ({ ...current, back: symmetricFace(current.front) })); setSide("back"); setSelected(null); }}>对称到背面 <span aria-hidden="true">→</span></button>{undo && <button type="button" aria-label="撤销上次对称" onClick={() => { setDesign(current => ({ ...current, back: undo })); setUndo(null); setSelected(null); }}>撤销</button>}</div>
        <p className={styles.fieldNote}>两面独立设计。对称操作将正面应用到背面，之后仍可分别修改。</p>
        <section><h3>卡片信息</h3><label>角色名称<input maxLength={60} value={design.display_name} onChange={event => setDesign(current => ({ ...current, display_name: event.target.value, front: { ...current.front, layers: current.front.layers.map(item => item.kind === "name" ? { ...item, text: event.target.value } : item) } }))} /></label>
          <label>身份描述<input maxLength={120} value={design.subtitle} onChange={event => setDesign(current => ({ ...current, subtitle: event.target.value, front: { ...current.front, layers: current.front.layers.map(item => item.kind === "role" ? { ...item, text: event.target.value } : item) } }))} /></label></section>
        <section><h3>底色与质感</h3><div className={styles.swatches} role="group" aria-label="卡片配色">{CARD_THEMES.map(theme => <button key={theme.name} type="button" aria-label={theme.name} aria-pressed={face.color === theme.color} style={{ background: theme.color }} onClick={() => changeFace({ color: theme.color, accent: theme.accent, layers: face.layers.map(item => item.kind === "name" || item.kind === "role" ? { ...item, color: theme.accent } : item) })} />)}</div>
          <label>卡面材质<select value={face.material} onChange={event => changeFace({ material: event.target.value as CardFaceDesign["material"] })}><option value="matte">哑光纸面</option><option value="metal">细纹金属</option><option value="gloss">亮面覆膜</option><option value="holo">虹彩镭射</option></select></label><label className={styles.check}><input type="checkbox" checked={face.frame} onChange={event => changeFace({ frame: event.target.checked })} />显示细边框</label></section>
        <section><h3>图片组件</h3><label className={styles.upload}>＋ 上传并裁剪图片<input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) upload(file); }} /></label>
          {face.image_digest && <><div className={styles.symmetryTools}><button type="button" disabled={!face.source_digest} onClick={recrop}>重新裁剪</button><button type="button" onClick={() => changeFace({ image_digest: null, source_digest: null, crop: null })}>移除图片</button></div><label>图片透明度<input type="range" min={0} max={100} value={face.image_opacity} onChange={event => changeFace({ image_opacity: Number(event.target.value) })} /></label><p className={styles.fieldNote}>保留原图，可随时重新选择显示区域。</p></>}</section>
        <section><h3>添加组件</h3><div className={styles.stickers} role="group" aria-label="贴纸组件">{STICKERS.map(text => <button key={text} type="button" disabled={face.layers.length >= 24} aria-label={`添加贴纸 ${text}`} onClick={() => add("sticker", text)}>{text}</button>)}</div><button type="button" className={styles.fullWidth} disabled={face.layers.length >= 24} onClick={() => add("text", "新的文字")}>＋ 添加自定义文字</button><p className={styles.fieldNote}>卡面上的组件可直接拖动。</p></section>
        {component && <section><h3>当前组件</h3><label>文字内容<input aria-label="文字内容" maxLength={300} value={component.text} onChange={event => changeLayer({ text: event.target.value })} /></label>
          {([ ["size", "大小", 8, 128], ["rotation", "旋转角度", -180, 180], ["opacity", "透明度", 0, 100] ] as const).map(([key, title, min, max]) => <label key={key}>{title}<input aria-label={title} type="range" min={min} max={max} value={component[key]} onChange={event => changeLayer({ [key]: Number(event.target.value) })} /></label>)}
          <label>组件颜色<input type="color" value={component.color} onChange={event => changeLayer({ color: event.target.value })} /></label><button type="button" className={styles.danger} onClick={() => { changeFace({ layers: face.layers.filter(item => item.id !== selected) }); setSelected(null); }}>删除组件</button></section>}
      </fieldset>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <footer><button type="button" disabled={busy} onClick={close}>取消</button><button type="button" className={styles.gold} disabled={busy || Boolean(crop)} onClick={() => void work(async () => { const saved = await client.saveLibraryDesign(card, design); initial.current = JSON.stringify(design); onSaved(saved); onClose(); })}>{busy ? "正在保存…" : "保存设计"}</button></footer>
    </aside>
    {crop && <CardCropper key={crop.url} url={crop.url} initial={crop.initial} busy={busy} error={error} onApply={apply} onClose={() => { if (!busyRef.current) { setCrop(null); setError(""); } }} />}
  </div>;
}
