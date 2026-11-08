import { useEffect, useState } from "react";
import type { ActivityLocation, CoreClient } from "@dreamtalk/api-client";
import { locationPaths } from "./LocationWorkspace";

export function InitialLocationChoice({ client, worldId, value, onChange, disabled }: {
  client: CoreClient; worldId: string; value: string; onChange: (value: string) => void; disabled: boolean;
}) {
  const [locations, setLocations] = useState<ActivityLocation[]>([]);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let alive = true;
    void client.listActivityLocations(worldId).then(items => { if (alive) { setLocations(items); setError(false); } }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [client, worldId, reload]);
  const paths = locationPaths(locations);
  const visible = (place: ActivityLocation) => {
    const visited = new Set<string>(); let current: ActivityLocation | undefined = place;
    while (current) {
      if (current.hidden || visited.has(current.location_id)) return false;
      visited.add(current.location_id);
      current = locations.find(item => item.location_id === current?.parent_id);
    }
    return true;
  };
  const options = locations.filter(visible);
  return <div className="editor-panel"><label className="field"><span>初始地点</span><select value={value} disabled={disabled} onChange={event => onChange(event.target.value)}><option value="">无</option>{options.map(place => <option key={place.location_id} value={place.location_id}>{paths.get(place.location_id)}</option>)}</select></label><p className="inline-hint">默认无地点：角色可以聊天，但不能移动，也不会显示在地点图中。选择地点后才会从那里开始生活，不调用模型。</p>{!options.length && !error && <p className="inline-hint">当前没有可选地点，可先保持“无”，以后在角色资料中设置。</p>}{error && <p role="alert">未能读取地点。<button type="button" disabled={disabled} onClick={() => setReload(old => old + 1)}>重新读取</button></p>}</div>;
}
