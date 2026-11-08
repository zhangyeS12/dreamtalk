import { useState } from "react";
import type { ChatVisuals, CoreClient } from "@dreamtalk/api-client";
import type { ChatVisualState } from "./useChatVisuals";

export function ChatVisualSettings({ client, worldId, state }: { client: CoreClient; worldId: string; state: ChatVisualState }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const currentDigest = state.visuals?.common_background_digest ?? null;
  const save = async (operation: () => Promise<ChatVisuals>) => {
    if (busy) return;
    setBusy(true); setError("");
    try { state.replace(await operation()); }
    catch { setError("聊天背景保存失败，请稍后重试。背景不会影响聊天记录。 "); }
    finally { setBusy(false); }
  };
  const upload = async (file?: File) => {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setError("背景图片不能超过 10 MB。"); return; }
    await save(async () => {
      const image = await client.uploadCoverImage(worldId, file);
      return client.setChatBackground(worldId, image.digest);
    });
  };
  return <section className="settings-section chat-visual-settings">
    <div className="section-heading"><h2>聊天背景</h2><p>只作用于当前世界的聊天窗口。未设置角色专属背景时，使用这里的通用背景；不设置则使用默认深色界面。</p></div>
    {error && <p className="app-alert" role="alert">{error}</p>}
    {state.error && <p className="app-alert" role="alert">{state.error}<button type="button" className="text-action" onClick={state.refresh}>重新读取</button></p>}
    <div className="chat-visual-preview" aria-label="通用聊天背景预览" style={currentDigest && state.urls[currentDigest] ? { backgroundImage: `url(${state.urls[currentDigest]})` } : undefined}>
      {!currentDigest && <span>尚未设置通用背景</span>}
    </div>
    <div className="chat-visual-actions">
      <label className="secondary-button chat-visual-upload">上传通用背景<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy || state.loading} onChange={event => { void upload(event.target.files?.[0]); event.target.value = ""; }} /></label>
      {currentDigest && <button type="button" className="text-action" disabled={busy} onClick={() => void save(() => client.setChatBackground(worldId, null))}>恢复默认</button>}
    </div>
    <p className="inline-hint">支持 JPG、PNG、WebP，最大 10 MB。图片只保存在当前世界的素材库中，不会替换世界封面。</p>
    {state.visuals?.expressions.length ? <p className="inline-hint">当前已配置 {state.visuals.expressions.length} 个角色表情立绘；可在通讯录的角色资料中继续编辑。</p> : null}
  </section>;
}

