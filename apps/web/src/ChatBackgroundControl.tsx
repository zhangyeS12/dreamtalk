import { useState } from "react";
import type { CoreClient } from "@dreamtalk/api-client";
import type { ChatVisualState } from "./useChatVisuals";

export function ChatBackgroundControl({ client, worldId, rootImportId, state }: { client: CoreClient; worldId: string; rootImportId: string; state: ChatVisualState }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const digest = state.visuals?.character_backgrounds[rootImportId] ?? null;
  const save = async (file?: File) => {
    if (!file || busy) return;
    if (file.size > 10 * 1024 * 1024) { setError("背景图片不能超过 10 MB。"); return; }
    setBusy(true); setError("");
    try {
      const image = await client.uploadCoverImage(worldId, file);
      state.replace(await client.setCharacterChatBackground(worldId, rootImportId, image.digest));
    } catch { setError("角色专属背景保存失败，请稍后重试。"); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (busy) return;
    setBusy(true); setError("");
    try { state.replace(await client.setCharacterChatBackground(worldId, rootImportId, null)); }
    catch { setError("角色专属背景移除失败，请稍后重试。"); }
    finally { setBusy(false); }
  };
  return <details className="thread-visual-control">
    <summary title="设置当前角色的聊天背景">背景</summary>
    <div className="thread-visual-popover">
      <strong>{digest ? "已使用角色专属背景" : "当前使用通用背景"}</strong>
      <label className="secondary-button chat-visual-upload">上传专属背景<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={event => { void save(event.target.files?.[0]); event.target.value = ""; }} /></label>
      {digest && <button type="button" className="text-action" disabled={busy} onClick={() => void remove()}>恢复通用背景</button>}
      {error && <span className="thread-visual-error" role="alert">{error}</span>}
    </div>
  </details>;
}

