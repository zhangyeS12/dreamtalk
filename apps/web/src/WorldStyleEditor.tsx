import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type WorldStylePreview, type WorldStyleSnapshot } from "@dreamtalk/api-client";
import { useDesktopUpdateBlock } from "./DesktopUpdates";

export function WorldStyleEditor({ client, worldId, onDirtyChange }: {
  client: CoreClient; worldId: string; onDirtyChange: (dirty: boolean) => void;
}) {
  const [saved, setSaved] = useState<WorldStyleSnapshot | null>(null);
  const [draft, setDraft] = useState("");
  const [preview, setPreview] = useState<WorldStylePreview | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const pending = useRef(false), mounted = useRef(true);
  const dirty = saved !== null && draft !== saved.instructions;
  useDesktopUpdateBlock(busy ? "世界风格正在保存，请等结果确认。" : null);
  useEffect(() => { onDirtyChange(dirty || busy); return () => onDirtyChange(false); }, [dirty, busy, onDirtyChange]);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    setSaved(null); setPreview(null); setError(""); setNotice("");
    void client.worldStyle(worldId, controller.signal).then(value => {
      if (!controller.signal.aborted) { setSaved(value); setDraft(value.instructions); }
    }).catch(() => { if (!controller.signal.aborted) setError("无法读取世界风格，请重试读取。"); });
    return () => { mounted.current = false; controller.abort(); };
  }, [client, worldId, reload]);
  const act = async (confirm: boolean) => {
    if (!saved || pending.current || (confirm && !preview)) return;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    try {
      if (confirm && preview) {
        const value = await client.confirmWorldStyle(worldId, preview);
        if (mounted.current) { setSaved(value); setDraft(value.instructions); setPreview(null); setNotice("已保存。从下一次角色发言起采用此风格。"); }
      } else {
        const value = await client.previewWorldStyle(worldId, draft, saved.revision);
        if (mounted.current) setPreview(value);
      }
    } catch (failure) {
      if (mounted.current) setError(failure instanceof CoreRequestError && failure.status === 409
        ? "世界风格已被其他编辑更新。当前草稿保留，请复制需要的内容后重新读取。"
        : failure instanceof CoreRequestError && failure.code === "world_style_capacity"
          ? "内容超出容量，请精简到 4000 字以内；过多特殊转义字符也会占用容量。草稿已保留。"
          : confirm ? "保存结果未能确认。请先重新读取，核对是否已保存；不会自动重发。" : "预览未完成，请检查连接或精简内容后重试。草稿已保留。");
    } finally { pending.current = false; if (mounted.current) setBusy(false); }
  };
  const readAgain = () => {
    if (!busy && (!dirty || window.confirm("重新读取会丢弃当前未保存的草稿，确定继续吗？"))) setReload(value => value + 1);
  };
  return <section className="world-style-editor" aria-labelledby="world-style-title">
    <div className="thread-heading"><h2 id="world-style-title">世界风格</h2><button type="button" className="text-action" disabled={busy} onClick={readAgain}>重新读取</button></div>
    <p className="inline-hint">为当前世界约定题材、内容尺度与叙事风格。涉及这些写作要求时优先采用本页约定；角色身份、性格和偏好仍以角色卡为准，关系发展承接已有对话。</p>
    <p className="inline-hint">用于私聊、群聊和角色主动联系。留空表示不添加世界风格。不会改写历史消息；模型的实际表现仍取决于所用服务。</p>
    {error && <p role="alert" className="app-alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!saved && !error && <p role="status">正在读取世界风格…</p>}
    {saved && <><label htmlFor="world-style-draft">当前世界的写作约定</label>
      <textarea id="world-style-draft" rows={10} value={draft} maxLength={4000} disabled={busy || preview !== null}
        placeholder="例如：都市悬疑题材，气氛克制；通过动作、环境和对话推进，避免每次都以反问结尾。"
        onChange={event => { setDraft(event.target.value); setNotice(""); }} />
      <p className="inline-hint">{draft.length} / 4000 字。角色台词使用“引号”时显示为黄色，动作、场景和神态保留默认颜色。</p>
      {preview ? <div className="world-style-preview"><h3>确认后的世界风格</h3><p className="world-style-text">{preview.instructions || "不添加世界风格"}</p>
        <p className="inline-hint">保存后影响后续生成，旧风格下尚未投递的后台联系会取消，不会自动重试。</p>
        <div className="profile-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void act(true)}>{busy ? "正在保存…" : "确认并保存"}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setPreview(null)}>返回修改</button></div>
      </div> : <button type="button" className="primary-button" disabled={busy || !dirty} onClick={() => void act(false)}>{busy ? "正在准备预览…" : "预览修改"}</button>}
    </>}
  </section>;
}
