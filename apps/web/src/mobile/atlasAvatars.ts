/** Bounded local-media reads; full-resolution blobs are released after thumbnailing. */
export async function smallAvatar(blob: Blob, signal: AbortSignal): Promise<Blob> {
  if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
  if (typeof createImageBitmap !== "function") return blob;
  const image = await createImageBitmap(blob);
  try {
    if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
    const size = Math.min(image.width, image.height), canvas = document.createElement("canvas");
    canvas.width = 112; canvas.height = 112;
    const context = canvas.getContext("2d");
    if (!context) return blob;
    context.drawImage(image, (image.width - size) / 2, (image.height - size) / 2, size, size, 0, 0, 112, 112);
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob(result => {
      if (signal.aborted) reject(new DOMException("Cancelled", "AbortError"));
      else if (result) resolve(result); else reject(new Error("avatar_thumbnail_failed"));
    }, "image/png"));
  } finally { image.close(); }
}
export async function loadAtlasAvatars(digests: string[], read: (digest: string, signal: AbortSignal) => Promise<Blob>,
  signal: AbortSignal, onReady: (digest: string, url: string) => void): Promise<void> {
  const queue = [...new Set(digests)]; let index = 0;
  async function worker() {
    while (!signal.aborted && index < queue.length) {
      const digest = queue[index++];
      try {
        const original = await read(digest, signal);
        const thumbnail = await smallAvatar(original, signal);
        if (signal.aborted) return;
        const url = URL.createObjectURL(thumbnail);
        if (signal.aborted) URL.revokeObjectURL(url); else onReady(digest, url);
      } catch {
        if (signal.aborted) return; // Missing/corrupt local media keeps the real person's initial.
      }
    }
  }
  await Promise.all([worker(), worker()]);
}
