import { useEffect, useId, useState } from "react";
import { CoreClient, type PersonaSourceChoice } from "@dreamtalk/api-client";

export function PersonaSourcePicker({ client, worldId, characters = false, lorebooksOnly = false, onChoose }: {
  client: CoreClient;
  worldId: string;
  characters?: boolean;
  lorebooksOnly?: boolean;
  onChoose: (source: PersonaSourceChoice) => void;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [after, setAfter] = useState<string | undefined>();
  const [items, setItems] = useState<PersonaSourceChoice[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    setBusy(true); setError("");
    if (!after) setItems([]);
    const request = lorebooksOnly ? client.playerPersonaSources(worldId, search, after, characters, abort.signal, true) : client.playerPersonaSources(worldId, search, after, characters, abort.signal);
    void request.then(page => {
      if (abort.signal.aborted) return;
      if (page.next_after && page.next_after === after) throw new Error("repeated cursor");
      setItems(page.items); setNext(page.next_after);
    }).catch(() => {
      if (!abort.signal.aborted) setError("资料读取未完成，请重试。");
    }).finally(() => { if (!abort.signal.aborted) setBusy(false); });
    return () => abort.abort();
  }, [client, worldId, characters, lorebooksOnly, search, after, reload]);

  return <div className="persona-source-picker">
    <div className="field"><label htmlFor={id}>{characters ? "查找认识我的角色" : "查找设定资料"}</label>
      <input id={id} value={query} maxLength={120} onChange={event => setQuery(event.target.value)} placeholder="按名称搜索" />
    </div>
    <button type="button" className="secondary-button" disabled={busy} onClick={() => { setSearch(query.trim()); setAfter(undefined); setReload(value => value + 1); }}>搜索</button>
    {busy && <p role="status">正在读取资料…</p>}
    {error && <p role="alert">{error} <button type="button" className="text-action" onClick={() => setReload(value => value + 1)}>重试</button></p>}
    {!busy && !error && <>
      {items.length === 0 && <p className="inline-hint">没有符合条件的已接受资料。</p>}
      <ul className="persona-source-list">{items.map(item => <li key={`${item.reference.import_id}:${item.reference.content_id}`}>
        <details><summary>{item.title} <small>{item.kind === "character" ? "角色卡" : "世界书条目"}</small></summary>
          <p className="persona-text">{item.text || "此条目没有正文。"}</p>
          {item.excerpt && <p className="inline-hint">正文较长，此处仅显示开头。采用前请补充并核对身份介绍。</p>}
        </details>
        <button type="button" className="text-action" onClick={() => onChoose(item)}>{characters ? `添加${item.title}` : `采用${item.title}`}</button>
      </li>)}</ul>
      <div className="profile-actions">
        {after && <button type="button" className="text-action" onClick={() => setAfter(undefined)}>返回第一页</button>}
        {next && <button type="button" className="text-action" onClick={() => setAfter(next)}>下一页资料</button>}
      </div>
    </>}
  </div>;
}
