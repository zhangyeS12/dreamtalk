import { useEffect, useRef, useState } from "react";
import Cropper, { type Area, type MediaSize } from "react-easy-crop";
import "react-easy-crop/react-easy-crop.css";
import type { CoverCrop } from "@dreamtalk/api-client";
import { CardDialog } from "./CardDialog";
import { CARD_RATIO, clamp } from "./cardDesign";
import styles from "./Cards.module.css";

export function CardCropper({ url, initial, busy, error, onApply, onClose, aspect = CARD_RATIO, title = "裁剪卡面图片" }: {
  aspect?: number; title?: string;
  url: string; initial: CoverCrop | null; busy: boolean; error: string; onApply: (crop: CoverCrop) => void; onClose: () => void;
}) {
  const stage = useRef<HTMLDivElement>(null), selection = useRef<Area | null>(null);
  const [point, setPoint] = useState({ x: 0, y: 0 }), [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState<CoverCrop["rotation"]>(initial?.rotation ?? 0), [box, setBox] = useState(78);
  const [media, setMedia] = useState<MediaSize | null>(null), [bounds, setBounds] = useState({ width: 600, height: 340 });
  const [initialArea, setInitialArea] = useState<Area | undefined>(initial ?? undefined), [ready, setReady] = useState(false);
  const [imageError, setImageError] = useState(false);
  const resize = useRef<{ id: number; x: number; y: number; width: number; horizontal: number; vertical: number } | null>(null);
  const maxWidth = Math.max(60, Math.min(bounds.width - 30, (bounds.height - 30) * aspect));
  const cropSize = { width: maxWidth * box / 100, height: maxWidth * box / 100 / aspect };
  const rotated = media ? rotation % 180 ? { width: media.height, height: media.width } : media : null;
  const minZoom = rotated ? Math.max(1, cropSize.width / rotated.width, cropSize.height / rotated.height) : 1;
  const effectiveZoom = Math.max(minZoom, zoom);
  useEffect(() => { const observer = new ResizeObserver(entries => setBounds({ width: entries[0].contentRect.width, height: entries[0].contentRect.height })); if (stage.current) observer.observe(stage.current); return () => observer.disconnect(); }, []);
  const report = (area: Area) => { selection.current = area; setReady(true); };
  return <CardDialog title={title} onClose={onClose} busy={busy} wide className={styles.cropDialog}>
    <p>拖动图片选择显示区域，可缩放、旋转或调整裁剪框大小。</p>
    <div className={styles.cropWorkspace}>
    <div ref={stage} className={styles.cropStage} data-busy={busy || undefined}>
      <Cropper image={url} crop={point} zoom={effectiveZoom} minZoom={minZoom} maxZoom={minZoom * 5} rotation={rotation}
        aspect={aspect} cropSize={cropSize} objectFit="contain" disableAutomaticStylesInjection initialCroppedAreaPercentages={initialArea}
        onCropChange={setPoint} onZoomChange={setZoom} onCropAreaChange={report} onCropComplete={report} onMediaLoaded={setMedia}
        mediaProps={{ onError: () => setImageError(true) }} cropperProps={{ tabIndex: busy ? -1 : 0, "aria-label": "图片裁剪区域，方向键移动图片" }} />
      <div className={styles.cropHandles} style={cropSize}>
        {[{ name: "左上", x: -1, y: -1 }, { name: "右上", x: 1, y: -1 }, { name: "左下", x: -1, y: 1 }, { name: "右下", x: 1, y: 1 }].map(corner => <button key={corner.name} type="button" disabled={busy} aria-label={`调整裁剪框${corner.name}角`} style={{ left: corner.x < 0 ? 0 : "100%", top: corner.y < 0 ? 0 : "100%", cursor: corner.x === corner.y ? "nwse-resize" : "nesw-resize" }}
          onPointerDown={event => { event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId); resize.current = { id: event.pointerId, x: event.clientX, y: event.clientY, width: cropSize.width, horizontal: corner.x, vertical: corner.y }; }}
          onPointerMove={event => { const drag = resize.current; if (!drag || drag.id !== event.pointerId) return; const dx = event.clientX - drag.x, dy = event.clientY - drag.y; const delta = Math.abs(dx) > Math.abs(dy) ? dx * drag.horizontal * 2 : dy * drag.vertical * 2 * aspect; setBox(clamp((drag.width + delta) / maxWidth * 100, 35, 96)); setInitialArea(undefined); }}
          onPointerUp={event => { resize.current = null; event.currentTarget.releasePointerCapture(event.pointerId); }} onPointerCancel={() => { resize.current = null; }}
          onKeyDown={event => { if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) { event.preventDefault(); setInitialArea(undefined); setBox(value => clamp(value + (["ArrowRight", "ArrowDown"].includes(event.key) ? 2 : -2), 35, 96)); } }} />)}
      </div>
    </div>
    <fieldset disabled={busy} className={styles.cropControls}>
      <label>图片缩放<input aria-label="图片缩放" type="range" min={minZoom} max={minZoom * 5} step={.01} value={effectiveZoom} onChange={event => { setInitialArea(undefined); setZoom(Number(event.target.value)); }} /></label>
      <label>裁剪框大小<input aria-label="裁剪框大小" type="range" min={35} max={96} value={box} onChange={event => { setInitialArea(undefined); setBox(Number(event.target.value)); }} /></label>
      <div className={styles.cropButtons}><button type="button" onClick={() => { setReady(false); setInitialArea(undefined); setPoint({ x: 0, y: 0 }); setRotation(value => ((value + 90) % 360) as CoverCrop["rotation"]); setZoom(1); }}>旋转90°</button>
      <button type="button" onClick={() => { setInitialArea(undefined); setPoint({ x: 0, y: 0 }); setRotation(0); setZoom(1); setBox(78); }}>重置裁剪</button></div>
    </fieldset>
    <p className={styles.cropHint}>拖动图片选择区域 · 滚轮缩放 · 拖动四角调整裁剪框</p>
    </div>
    {(error || imageError) && <p role="alert">{error || "无法读取图片，请重新选择。"}</p>}
    <footer><button type="button" disabled={busy} onClick={onClose}>取消</button><button type="button" className={styles.gold} disabled={busy || !ready || imageError} onClick={() => { if (selection.current) onApply({ ...selection.current, rotation }); }}>{busy ? "正在裁剪…" : "使用此区域"}</button></footer>
  </CardDialog>;
}
