import { useEffect, useRef, useState } from "react";
import { CoreRequestError, type CoreClient, type ExampleWorldTemplate } from "@dreamtalk/api-client";

const pendingKey = "livingworld.exampleWorld.campus-v1";
function rememberedRequest(template: ExampleWorldTemplate) {
  try {
    const value = JSON.parse(window.localStorage.getItem(pendingKey) ?? "null");
    return value && typeof value.request_id === "string" && /^[0-9a-f-]{36}$/i.test(value.request_id)
      && value.reviewed_hash === template.reviewed_hash && Array.isArray(value.public_entries)
      && value.public_entries.every((key: unknown) => typeof key === "string" && template.entries.some(entry => entry.key === key))
      ? value as ExampleWorldTemplate["pending"][number] : null;
  } catch { return null; }
}

export function ExampleWorldPanel({ client, onCreated, onBusy, onClose }: {
  client: CoreClient; onCreated: (id: string) => Promise<void>;
  onBusy: (busy: boolean) => void; onClose: () => void;
}) {
  const [template, setTemplate] = useState<ExampleWorldTemplate | null>(null);
  const [publicEntries, setPublicEntries] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [pending, setPending] = useState(false);
  const request = useRef<string | null>(null);
  const active = useRef(true);
  const lock = useRef(false);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    active.current = true;
    let current = true;
    title.current?.focus();
    setLoading(true); setError("");
    void client.exampleWorld().then(value => {
      if (!current || !active.current) return;
      const previous = rememberedRequest(value) ?? value.pending[0];
      setTemplate(value); setPending(Boolean(previous));
      request.current = previous?.request_id ?? null;
      setPublicEntries(previous?.public_entries ?? value.entries.map(entry => entry.key));
    }).catch(() => { if (current && active.current) setError("校园示例暂时未能读取，请重新读取。"); })
      .finally(() => { if (current && active.current) setLoading(false); });
    return () => { current = false; active.current = false; };
  }, [client, reload]);
  const create = async () => {
    if (!template || lock.current) return;
    lock.current = true; setBusy(true); onBusy(true); setError(""); setPending(true);
    request.current ??= crypto.randomUUID();
    try {
      window.localStorage.setItem(pendingKey, JSON.stringify({ request_id: request.current,
        reviewed_hash: template.reviewed_hash, public_entries: publicEntries }));
      const result = await client.createExampleWorld(template, request.current, publicEntries);
      if (active.current) {
        await onCreated(result.world_id);
        window.localStorage.removeItem(pendingKey);
      }
    } catch (failure) {
      if (active.current) {
        if (failure instanceof CoreRequestError && failure.code === "example_world_deleted") {
          window.localStorage.removeItem(pendingKey); request.current = null; setPending(false);
          setError("之前创建的示例已经删除。可以确认设定后重新创建。");
        } else setError(failure instanceof CoreRequestError && failure.code === "example_preview_changed"
          ? "示例内容已有更新，请重新读取后确认。"
          : "校园示例尚未完成确认。点击“继续创建”会核对并完成同一次创建，不会重复添加世界。");
      }
    } finally {
      lock.current = false; onBusy(false);
      if (active.current) setBusy(false);
    }
  };
  return <section className="archive-editor example-world" aria-labelledby="example-world-title" aria-busy={busy}>
    <div className="archive-editor-heading"><h2 id="example-world-title" ref={title} tabIndex={-1}>体验校园示例</h2>
      <button type="button" className="text-action" disabled={busy} onClick={onClose}>收起</button></div>
    <div className="example-world-body">
      {loading && <p role="status">正在读取校园设定…</p>}
      {error && <p className="app-alert" role="alert">{error}</p>}
      {!loading && error && <button type="button" className="secondary-button" onClick={() => setReload(value => value + 1)}>重新读取示例</button>}
      {template && <><h3>{template.name}</h3><p>{template.description}</p>
        <dl className="example-character-list">{template.characters.map(character => <div key={character.key}>
          <dt>{character.name}<span>{character.role}</span></dt><dd>{character.description} {character.personality}</dd>
        </div>)}</dl>
        <details><summary>查看世界书与角色可见范围（{template.entries.length}条）</summary>
          <p className="inline-hint">勾选的条目会作为所有角色可见的公共背景；未勾选的条目保留为隐藏设定。创建后可继续编辑。</p>
          {template.entries.map(entry => <div className="example-lore-entry" key={entry.key}>
            <label><input type="checkbox" checked={publicEntries.includes(entry.key)} disabled={busy || pending}
              onChange={event => setPublicEntries(current => event.target.checked ? [...current, entry.key] : current.filter(key => key !== entry.key))} />{entry.title} · 作为公共背景</label>
            <p>{entry.content}</p>
          </div>)}
        </details>
        <p className="inline-hint">将新建一个独立世界，添加世界书、三位角色及教室等地点。你仍从家开始，可在“我”中修改身份。不会调用模型，也不会开启后台生成。</p>
        <p className="inline-hint">首次聊天前，在“模型设置”填写或导入你的API配置。</p>
        <button type="button" className="primary-button" disabled={busy || loading} onClick={() => void create()}>{busy ? "正在准备校园…" : pending ? "继续创建" : "确认设定并创建示例世界"}</button>
      </>}
    </div>
  </section>;
}
