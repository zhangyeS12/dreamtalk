import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ActivityLocation } from "@dreamtalk/api-client";

const errors: Record<string, string> = {
  invalid_location_name: "请输入1至120字的地点名称，不含换行或控制字符。",
  location_home_reserved: "“家”由进入世界时自动创建，请使用其他地点名称。",
  location_name_exists: "当前世界已添加同名地点，请刷新列表查看或使用其他名称。",
  location_catalog_capacity: "已达到当前世界的地点容量。自动规划最多支持32个地点，尚未进入世界时会为“家”保留一个名额。",
  location_creation_conflict: "这次创建请求发生冲突，请刷新列表核对后再创建。",
  world_not_found: "当前世界已不可用，请重新选择世界。",
  world_runtime_unavailable: "当前世界暂时不可修改，请恢复正常运行后用原请求重试。",
};

export function WorldLocations({ client, worldId, visible, onDirtyChange }: {
  client: CoreClient; worldId: string; visible: boolean; onDirtyChange: (dirty: boolean) => void;
}) {
  const [locations, setLocations] = useState<ActivityLocation[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState<{ name: string; requestId: string } | null>(null);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const serial = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; serial.current++; }; }, []);
  useEffect(() => {
    onDirtyChange(!!name.trim() || pending !== null);
    return () => onDirtyChange(false);
  }, [name, pending, onDirtyChange]);

  useEffect(() => {
    if (!visible || busyRef.current) return;
    let active = true;
    const current = ++serial.current;
    void client.listActivityLocations(worldId).then(items => {
      if (active && current === serial.current) { setLocations(items); setError(""); }
    }).catch(() => {
      if (active && current === serial.current) setError("未能读取活动地点，请检查核心连接后刷新。");
    });
    return () => { active = false; };
  }, [client, worldId, visible]);

  async function refresh() {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError("");
    const current = ++serial.current;
    try {
      const items = await client.listActivityLocations(worldId);
      if (!alive.current || current !== serial.current) return;
      setLocations(items);
      if (pending) {
        // A name match is only a hint; the same-ID retry confirms this request.
        setNotice(items.some(item => item.name === pending.name)
          ? "列表中已有这个名称。可用原请求重试，确认本次提交结果；不会重复创建地点。"
          : "已刷新列表。未确认的请求仍保留，你可以用原请求重试。");
      }
    } catch { if (alive.current && current === serial.current) setError("未能刷新活动地点，请检查核心连接。草稿仍保留。"); }
    finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (busyRef.current || (!pending && !name.trim())) return;
    const request = pending ?? { name: name.trim(), requestId: crypto.randomUUID() };
    setPending(request); busyRef.current = true; setBusy(true); setNotice(""); setError("");
    const current = ++serial.current;
    try {
      const item = await client.createActivityLocation(worldId, request.name, request.requestId);
      if (!alive.current || current !== serial.current) return;
      // Preserve an unknown directory state instead of pretending this is all places.
      setLocations(items => items === null ? null : [...items.filter(existing => existing.location_id !== item.location_id), item]);
      setName(""); setPending(null);
      setNotice(`已添加“${item.name}”。已开启的自动活动将在下一次常规规划时考虑此地点。`);
    } catch (failure) {
      if (!alive.current || current !== serial.current) return;
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500) {
        setPending(null);
        setError(errors[failure.code ?? ""] ?? "地点未能保存，请核对名称或刷新列表后再试。草稿仍保留。");
      } else {
        setError(failure instanceof CoreRequestError && errors[failure.code ?? ""]
          ? errors[failure.code ?? ""]
          : "未能确认保存结果。名称和原请求仍保留，请检查连接后重试，或刷新列表核对；系统不会自动重复提交。");
      }
    } finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }

  return <section className="settings-section">
    <div className="section-heading"><h2>活动地点</h2><p>添加角色可以选择的活动场所，例如咖啡馆、录像店或学校。</p></div>
    <div className="setting-row"><span><strong>当前世界的手动地点</strong><small>此目录也包含初始“家”。添加地点不会移动你或角色。</small></span><button type="button" className="secondary-button" disabled={busy} onClick={() => void refresh()}>刷新地点</button></div>
    {locations === null ? <p className="inline-hint">地点列表尚未读取。</p> : locations.length ? <ul className="activity-location-list">{locations.map(item => <li key={item.location_id}><span>{item.name}</span>{item.is_home && <small>初始地点</small>}</li>)}</ul> : <p className="inline-hint">还没有手动地点。进入世界后会自动创建“家”。</p>}
    <form className="create-world" onSubmit={event => void create(event)}><label className="field"><span>新增地点名称</span><input value={name} disabled={busy || pending !== null} onChange={event => setName(event.target.value)} maxLength={120} placeholder="例如：六分街录像店" /></label><button type="submit" className="primary-button" disabled={busy || (!pending && !name.trim())}>{busy ? "正在保存…" : pending ? "用原请求重试" : "添加地点"}</button></form>
    {pending && !busy && <button type="button" className="text-action" onClick={() => {
      if (window.confirm("保存结果尚未确认，请先刷新地点列表核对。放弃重试后，原请求仍可能已经保存；确定开始其他编辑吗？")) { setPending(null); setNotice("已结束本次重试，名称仍保留。请核对列表后再创建。"); }
    }}>结束本次重试，继续编辑</button>}
    {error && <p className="app-alert" role="alert">{error}</p>}
    {notice && <p className="app-notice" role="status">{notice}</p>}
    <p className="inline-hint">手动添加不调用模型。启用自动活动后，地点名称会提供给你配置的模型，用于下一批日常规划；添加时不会立即重规划。地点背景可在世界书里填写并设为公共背景。</p>
  </section>;
}
