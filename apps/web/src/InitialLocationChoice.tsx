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
  return <div className="editor-panel"><label className="field"><span>初始地点（必选）</span><select value={value} disabled={disabled} onChange={event => onChange(event.target.value)}><option value="">请选择角色的常驻中心</option>{options.map(place => <option key={place.location_id} value={place.location_id}>{paths.get(place.location_id)}</option>)}</select></label><p className="inline-hint">确认后角色会从这里开始生活，无需先打开聊天，也不会调用模型。隐藏地点可在保存后逐角色开放并设置。</p>{!options.length && !error && <p className="inline-hint">请先在“我”中进入世界，或在通讯录添加公开地点。</p>}{error && <p role="alert">未能读取地点。<button type="button" disabled={disabled} onClick={() => setReload(old => old + 1)}>重新读取</button></p>}</div>;
}
