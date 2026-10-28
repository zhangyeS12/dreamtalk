import { useRef, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import "react-easy-crop/react-easy-crop.css";
import { CoreRequestError, type CoverCrop, type CoverFace, type CoverImage } from "@dreamtalk/api-client";

export type FaceDraft = { source: CoverImage; url: string; crop?: CoverCrop };
export const FACES: CoverFace[] = ["front", "spine", "back"];
export const LABELS = { front: "正面", spine: "书脊", back: "背面" };
export const SIZES = { front: [980, 1430], spine: [210, 1430], back: [980, 1430] } as const;

export function FaceCropper({ face, draft, disabled, onCrop, onPending }: {
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

export function failureMessage(error: unknown) {
  if (error instanceof CoreRequestError) {
    if (error.status === 409) return "封面已被其他编辑更新。草稿仍保留；可重新读取已保存封面后再编辑。";
    if (error.code === "cover_image_size_limit" || error.status === 413) return "图片太大，请选择不超过 10 MB 的图片。";
    if (error.code === "cover_image_dimensions_limit") return "图片尺寸过大或包含动画，请使用不超过 2000 万像素、最长边 10000 像素的静态图片。";
    if (error.code === "cover_crop_invalid") return "裁剪区域尚未准备好，请重新调整图片后保存。";
    if (error.code === "cover_image_invalid" || error.status === 415) return "图片无法读取。请使用有效的 JPG、PNG 或 WebP 静态图片。";
  }
  return "未能完成操作。草稿仍保留，请检查核心连接后重试。";
}

export function sameCrop(a: CoverCrop, b: CoverCrop) {
  return (["x", "y", "width", "height", "rotation"] as const).every(key => Math.abs(a[key] - b[key]) < .000001);
}
