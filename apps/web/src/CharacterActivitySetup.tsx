import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ActivityCharacter, type ActivityLocation } from "@dreamtalk/api-client";

const errors: Record<string, string> = {
  activity_player_changed: "当前玩家身份已改变，请重新选择身份并刷新。",
  activity_character_unavailable: "角色暂不可设置，请先在当前身份的通讯录打开私聊，再刷新列表。",
  activity_location_unavailable: "这个地点不可用于初始设置，请刷新后选择当前世界的手动地点。",
  activity_initial_already_set: "角色已有初始地点，本入口不会改变其位置。请刷新列表核对。",
  activity_character_capacity: "自动活动最多支持16名已设置地点的角色，当前已达到容量。",
  activity_request_conflict: "原请求的参数发生冲突，请刷新列表核对后再设置。",
  activity_target_unavailable: "角色或地点已不可用，请刷新列表核对。",
  world_runtime_unavailable: "当前世界暂时不可修改，请稍后用原请求重试。",
  valid_request_id_required: "保存请求无效，请刷新列表后重新设置。",
};
interface PendingSetup { characterId: string; locationId: string; requestId: string; name: string; locationName: string }

export function CharacterActivitySetup({ client, worldId, playerId, visible, onDirtyChange }: {
  client: CoreClient; worldId: string; playerId: string; visible: boolean; onDirtyChange: (dirty: boolean) => void;
}) {
  const [characters, setCharacters] = useState<ActivityCharacter[] | null>(null);
  const [locations, setLocations] = useState<ActivityLocation[] | null>(null);
  const [characterId, setCharacterId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [pending, setPending] = useState<PendingSetup | null>(null);
  const pendingRef = useRef<PendingSetup | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const serial = useRef(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    onDirtyChange(!!characterId || !!locationId || pending !== null);
    return () => onDirtyChange(false);
  }, [characterId, locationId, pending, onDirtyChange]);
  useEffect(() => () => { serial.current++; }, []);

  const refresh = useCallback(async () => {
    const job = ++serial.current;
    busyRef.current = true; setBusy(true); setError("");
    try {
      const [directory, places] = await Promise.all([
        client.listActivityCharacters(worldId), client.listActivityLocations(worldId),
      ]);
      if (job !== serial.current) return;
      if (directory.player_id !== playerId) {
        setCharacters(null); setLocations(null); setError(errors.activity_player_changed); return;
      }
      setCharacters(directory.items); setLocations(places);
      const unresolved = pendingRef.current;
      if (unresolved) setNotice(directory.items.some(item => item.character_id === unresolved.characterId && item.initialized)
        ? "角色已有初始地点。可用原请求重试确认本次提交结果；不会再次放置或移动角色。"
        : "已刷新列表。原请求仍保留，可用原请求重试。");
    } catch (failure) {
      if (job !== serial.current) return;
      setCharacters(null); setLocations(null);
      setError(failure instanceof CoreRequestError && errors[failure.code ?? ""]
        ? errors[failure.code ?? ""] : "未能读取角色和地点，请检查核心连接后刷新。选择和原请求仍保留。");
    } finally {
      if (job === serial.current) { busyRef.current = false; setBusy(false); }
    }
  }, [client, worldId, playerId]);
  useEffect(() => {
    if (visible && !busyRef.current) void refresh();
  }, [visible, refresh]);
  // Invalidate the previous client session's responses, including while hidden.
  useEffect(() => () => { serial.current++; busyRef.current = false; }, [client]);

  const chosenCharacter = characters?.find(item => item.character_id === characterId);
  const chosenLocation = locations?.find(item => item.location_id === locationId);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (busyRef.current || (!pendingRef.current && (!chosenCharacter || chosenCharacter.initialized || !chosenLocation))) return;
    const request = pendingRef.current ?? {
      characterId: chosenCharacter!.character_id, locationId: chosenLocation!.location_id,
      name: chosenCharacter!.name, locationName: chosenLocation!.name, requestId: crypto.randomUUID(),
    };
    pendingRef.current = request; setPending(request);
    const job = ++serial.current;
    busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try {
      await client.initializeCharacterActivity(worldId, playerId, request.characterId, request.locationId, request.requestId);
      if (job !== serial.current) return;
      setCharacters(items => items?.map(item => item.character_id === request.characterId ? { ...item, initialized: true } : item) ?? null);
      pendingRef.current = null; setPending(null); setCharacterId(""); setLocationId("");
      setNotice(`已为${request.name}设置初始地点：${request.locationName}。自动活动按已有开关和正常规划批次运行。`);
    } catch (failure) {
      if (job !== serial.current) return;
      const code = failure instanceof CoreRequestError ? failure.code ?? "" : "";
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500 && errors[code]) {
        pendingRef.current = null; setPending(null);
        setError(errors[code]);
      } else {
        setError(errors[code] ?? "未能确认保存结果。原请求仍保留，请检查连接后用原请求重试，或刷新列表核对。");
      }
    } finally {
      if (job === serial.current) { busyRef.current = false; setBusy(false); }
    }
  }

  return <section className="settings-section">
    <div className="section-heading"><h2>角色初始活动地点</h2><p>为已打开私聊的角色选择第一次参与世界活动的地点。</p></div>
    <div className="setting-row"><span><strong>当前身份的角色</strong><small>这里仅显示是否已设置初始地点。</small></span><button type="button" className="secondary-button" disabled={busy} onClick={() => { if (!busyRef.current) void refresh(); }}>刷新角色与地点</button></div>
    {characters === null ? <p className="inline-hint">角色列表尚未读取。</p> : characters.length ? <ul className="activity-location-list">{characters.map(item => <li key={item.character_id}><span>{item.name}</span><small>{item.initialized ? "已设置初始地点" : "尚未设置"}</small></li>)}</ul> : <p className="inline-hint">先在通讯录打开希望参与活动的角色私聊，再返回这里刷新。无需发送消息。</p>}
    <form className="create-world" onSubmit={event => void save(event)}>
      <label className="field"><span>角色</span><select value={characterId} disabled={busy || !!pending || !characters?.length} onChange={event => { setCharacterId(event.target.value); setNotice(""); }}><option value="">选择尚未设置的角色</option>{characters?.map(item => <option key={item.character_id} value={item.character_id} disabled={item.initialized}>{item.name}{item.initialized ? "（已设置）" : ""}</option>)}</select></label>
      <label className="field"><span>初始地点</span><select value={locationId} disabled={busy || !!pending || !locations?.length} onChange={event => { setLocationId(event.target.value); setNotice(""); }}><option value="">请选择地点</option>{locations?.map(item => <option key={item.location_id} value={item.location_id}>{item.name}</option>)}</select></label>
      <button type="submit" className="primary-button" disabled={busy || (!pending && (!chosenCharacter || chosenCharacter.initialized || !chosenLocation))}>{busy ? "处理中……" : pending ? "用原请求重试" : "确认初始地点"}</button>
    </form>
    {pending && <p className="inline-hint">待确认：{pending.name} → {pending.locationName}。刷新列表不会重新提交。</p>}
    {pending && !busy && <button type="button" className="text-action" onClick={() => {
      if (window.confirm("原请求可能已经保存。结束重试后请刷新核对，再选择其他角色；确定结束本次重试吗？")) {
        pendingRef.current = null; setPending(null); setCharacterId(""); setLocationId(""); setNotice("已结束本次重试，请刷新核对已保存状态。");
      }
    }}>结束本次重试</button>}
    {error && <p className="app-alert" role="alert">{error}</p>}
    {notice && <p className="app-notice" role="status">{notice}</p>}
    <p className="inline-hint">确认会把尚未设置地点的角色放到所选地点，不移动你，也不改变已有地点的角色。设置不调用模型，不显示角色之后的位置。自动活动需另外开启；若此前因无角色而停止，请在世界自动活动中明确选择“重新规划”。</p>
  </section>;
}
