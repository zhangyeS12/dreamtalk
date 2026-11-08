import { useEffect, useRef, useState } from "react";
import type { ActivityCharacterDirectory, ActivityLocation, CoreClient, SocialSnapshot } from "@dreamtalk/api-client";
import { InitialLocationChoice } from "./InitialLocationChoice";

export function UnplacedCharactersEditor({ client, worldId, directory, social, locations, refresh, onDirtyChange }: {
  client: CoreClient; worldId: string; directory: ActivityCharacterDirectory | null; social: SocialSnapshot | null; locations: ActivityLocation[];
  refresh: () => Promise<void>; onDirtyChange: (dirty: boolean) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]), [location, setLocation] = useState("");
  const [query, setQuery] = useState(""), [page, setPage] = useState(0), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const running = useRef(false), alive = useRef(true);
  const pending = useRef<{ location: string; items: { importId: string }[] } | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onDirtyChange(busy || selected.length > 0); return () => onDirtyChange(false); }, [busy, selected, onDirtyChange]);
  const unplaced = directory?.items.filter(item => !item.initialized) ?? [];
  const matches = unplaced.filter(item => item.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const lastPage = Math.max(0, Math.ceil(matches.length / 50) - 1), shownPage = Math.min(page, lastPage);
  async function save() {
    if (running.current || !directory?.player_id || !social || !location || !selected.length) return;
    const request = pending.current ?? { location, items: selected.flatMap(root => {
      const person = social.characters.find(item => item.root_import_id === root);
      return person ? [{ importId: person.current_import_id }] : [];
    }) };
    pending.current = request; running.current = true; setBusy(true); setMessage("");
    let completed = 0;
    try {
      while (request.items.length) {
        const item = request.items[0];
        // One immutable request per card; already placed cards are not moved.
        await client.initializeCardLocation(worldId, item.importId, request.location);
        request.items.shift(); completed++;
        if (alive.current) setMessage(`已设置 ${completed} 位，剩余 ${request.items.length} 位…`);
      }
      pending.current = null; if (alive.current) { setSelected([]); setMessage("所选角色的初始地点已保存，没有调用模型。"); }
    } catch { if (alive.current) setMessage(`批量设置尚未全部完成，剩余 ${request.items.length} 位。再次保存会继续核对，不会移动已经设置的角色。`); }
    finally { running.current = false; if (alive.current) { setBusy(false); await refresh(); } }
  }
  if (!unplaced.length && !pending.current) return null;
  return <details className="editor-panel"><summary>为已有角色批量设置初始地点（{unplaced.length} 位未设置）</summary><p className="inline-hint">只处理尚未设置的角色，已有位置保持原样。</p><input aria-label="筛选未设置地点的角色" placeholder="搜索角色名称" value={query} disabled={busy || !!pending.current} onChange={event => { setQuery(event.target.value); setPage(0); }} /><div className="profile-actions"><button type="button" disabled={busy || !!pending.current} onClick={() => setSelected(matches.map(item => item.root_import_id))}>选择全部筛选结果</button><button type="button" disabled={busy || !!pending.current} onClick={() => setSelected([])}>清空选择</button></div>{matches.slice(shownPage * 50, (shownPage + 1) * 50).map(person => <label className="location-check" key={person.root_import_id}><input type="checkbox" disabled={busy || !!pending.current} checked={selected.includes(person.root_import_id)} onChange={event => setSelected(old => event.target.checked ? [...old, person.root_import_id] : old.filter(id => id !== person.root_import_id))} />{person.name}</label>)}{matches.length > 50 && <div className="profile-actions"><button disabled={!shownPage || busy} onClick={() => setPage(shownPage - 1)}>上一页</button><span>{shownPage + 1} / {lastPage + 1}</span><button disabled={shownPage === lastPage || busy} onClick={() => setPage(shownPage + 1)}>下一页</button></div>}<InitialLocationChoice client={client} worldId={worldId} value={location} onChange={setLocation} disabled={busy || !!pending.current} /><button type="button" className="primary-button" disabled={busy || !location || !selected.length || !directory?.player_id || !locations.length} onClick={() => void save()}>{busy ? "正在设置…" : pending.current ? "继续保存剩余角色" : `为 ${selected.length} 位角色保存初始地点`}</button>{message && <p role="status">{message}</p>}</details>;
}
