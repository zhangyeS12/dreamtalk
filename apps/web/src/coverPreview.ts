import type { CoverCrop } from "@dreamtalk/api-client";

// Canvas only renders the crop selected by react-easy-crop; it has no gesture logic.
export async function coverPreview(source: string, crop: CoverCrop, width: number, height: number): Promise<Blob> {
  const image = new Image(); image.src = source; await image.decode();
  const rotated = crop.rotation % 180 !== 0;
  const boundWidth = rotated ? image.naturalHeight : image.naturalWidth;
  const boundHeight = rotated ? image.naturalWidth : image.naturalHeight;
  const scaleX = width / (boundWidth * crop.width / 100);
  const scaleY = height / (boundHeight * crop.height / 100);
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("cover_preview_unavailable");
  context.scale(scaleX, scaleY);
  context.translate(-boundWidth * crop.x / 100, -boundHeight * crop.y / 100);
  context.translate(boundWidth / 2, boundHeight / 2);
  context.rotate(crop.rotation * Math.PI / 180);
  context.translate(-image.naturalWidth / 2, -image.naturalHeight / 2);
  context.drawImage(image, 0, 0);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("cover_preview_unavailable")), "image/webp", .9));
}
