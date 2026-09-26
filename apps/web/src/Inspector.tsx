import { useCallback, useEffect, useMemo, useState } from "react";
import { CoreClient, type InspectorSnapshot, type WorldSummary } from "@dreamtalk/api-client";

interface Props { client: CoreClient }
const short = (value: string) => value.slice(0, 8);
const worldTime = (value: string) => {
  const micros = BigInt(value);
  const seconds = micros / 1_000_000n;
  const hundredths = ((micros % 1_000_000n) / 10_000n).toString().padStart(2, "0");
  return `${seconds}.${hundredths} 秒（${value} 微秒）`;
};
const label = (value: string, labels: Record<string, string>) => labels[value] ?? value;
const clockLabels = { running: "运行中", paused: "已暂停" };
const runtimeLabels = { starting: "启动中", catching_up: "追赶中", ready: "就绪", paused: "已暂停", degraded: "降级", stopping: "停止中", unmanaged: "未纳入运行时" };
const principalLabels = { player: "玩家", character: "角色", world: "世界" };
const activityLabels = { active: "活跃", inactive: "非活跃" };
const availabilityLabels = { busy: "忙碌", available: "可用" };
const triggerStatusLabels = { pending: "待处理", fired: "已触发", cancelled: "已取消" };
const priorityLabels: Record<string, string> = { "-1": "高", "0": "普通", "1": "低" };
const activationKindLabels = { world_orchestration: "世界编排", character_reaction: "角色反应", character_schedule_due: "角色日程到期", scene_activity: "场景活动" };
const fidelityLabels = { dormant: "休眠", background: "后台", active: "活跃", scene_active: "场景活跃", player_facing: "面向玩家" };
const channelLabels = { witnessed: "目击", told: "被告知", message: "消息", news: "新闻", document: "文档", inferred: "推断" };
const eventTypeLabels: Record<string, string> = {
  WorldCreated: "世界已创建",
  LocationCreated: "地点已创建",
  PlayerCreated: "玩家已创建",
  PlayerPlaced: "玩家已安置",
  CharacterCreated: "角色已创建",
  CharacterPlaced: "角色已安置",
  RelationshipChanged: "关系已变化",
  WorldTruthAsserted: "世界事实已声明",
  CharacterBeliefFormed: "角色信念已形成",
  ObservationRecorded: "观察已记录",
  KnowledgeAcquired: "知识已获得",
  PlayerMoved: "玩家已移动",
};
const triggerKindLabels = { "developer.inspector": "开发检查器" };
const demoNameLabels: Record<string, string> = { world_demo: "演示世界", player_a: "玩家甲", character_a: "角色甲", character_b: "角色乙", location_a: "地点甲", location_b: "地点乙", scene_a: "场景甲" };
const displayName = (value: string) => demoNameLabels[value] ?? value;
const targetLabel = (value: string) => {
  const [kind, identity] = value.split(":", 2);
  return `${label(kind, principalLabels)}：${short(identity ?? "")}`;
};

function Table({ headers, rows }: { headers: string[]; rows: Array<Array<string | number | null>> }) {
  return <div className="table-wrap"><table><thead><tr>{headers.map(item => <th key={item}>{item}</th>)}</tr></thead>
    <tbody>{rows.length ? rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell ?? "—"}</td>)}</tr>) : <tr><td colSpan={headers.length}>暂无记录</td></tr>}</tbody></table></div>;
}

export function Inspector({ client }: Props) {
  const [worlds, setWorlds] = useState<WorldSummary[]>([]);
  const [worldId, setWorldId] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [snapshot, setSnapshot] = useState<InspectorSnapshot | null>(null);
  const [scale, setScale] = useState("1");
  const [moveDestination, setMoveDestination] = useState("");
  const [observationId, setObservationId] = useState("");
  const [message, setMessage] = useState("");

  const loadWorlds = useCallback(async () => {
    const items = await client.listWorlds(); setWorlds(items);
    setWorldId(current => current || items[0]?.world_id || "");
  }, [client]);
  const refresh = useCallback(async () => {
    if (!worldId) return;
    const next = await client.snapshot(worldId, ownerId || undefined); setSnapshot(next);
    if (!ownerId && next.characters[0]) setOwnerId(next.characters[0].character_id);
    const currentLocation = next.players[0]?.location_id;
    const alternative = next.locations.find(item => item.location_id !== currentLocation);
    if (alternative && (!moveDestination || moveDestination === currentLocation)) setMoveDestination(alternative.location_id);
  }, [client, worldId, ownerId, moveDestination]);
  useEffect(() => { void loadWorlds().catch(() => setMessage("无法加载开发者接口")); }, [loadWorlds]);
  useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(), 500); return () => clearInterval(timer); }, [refresh]);

  const act = async (operation: () => Promise<unknown>, label: string) => {
    try { await operation(); setMessage(label); await refresh(); } catch { setMessage("操作失败，请检查核心日志"); }
  };
  const selectedPlayer = snapshot?.players[0];
  const authorizedObservations = useMemo(() => snapshot?.observations.filter(item => item.principal_kind === "character" && (!ownerId || item.principal_id === ownerId)) ?? [], [snapshot, ownerId]);

  if (!worldId) return <section className="empty"><h2>开发者运行时检查器</h2><p>当前没有世界。</p>
    <button onClick={() => void act(async () => { const created = await client.createDemoWorld(); await loadWorlds(); setWorldId(created.world_id); }, "中性演示世界已创建")}>创建中性演示世界</button><p>{message}</p></section>;
  if (!snapshot) return <section><h2>开发者运行时检查器</h2><p>正在加载当前状态……</p></section>;
  return <section className="inspector">
    <header className="toolbar"><div><h2>开发者运行时检查器</h2><p className="muted">已认证的开发工具 · 使用真实应用路径</p></div>
      <div className="controls"><button onClick={() => void act(async () => { const created = await client.createDemoWorld(); await loadWorlds(); setWorldId(created.world_id); }, "中性演示世界已就绪")}>创建或加载中性演示世界</button><label>世界<select value={worldId} onChange={event => setWorldId(event.target.value)}>{worlds.map(item => <option key={item.world_id} value={item.world_id}>{displayName(item.name)}</option>)}</select></label></div></header>
    <div className="status-grid"><article><span>世界时间</span><strong>{worldTime(snapshot.clock.world_time)}</strong></article><article><span>时钟</span><strong>{label(snapshot.clock.state, clockLabels)}</strong></article><article><span>时间倍率</span><strong>{snapshot.clock.scale}×</strong></article><article><span>运行状态</span><strong>{label(snapshot.runtime_state, runtimeLabels)}</strong></article></div>
    <div className="controls">
      <button onClick={() => void act(() => snapshot.clock.state === "running" ? client.pauseWorld(worldId) : client.resumeWorld(worldId), snapshot.clock.state === "running" ? "世界已暂停" : "世界已恢复")}>{snapshot.clock.state === "running" ? "暂停" : "恢复"}</button>
      <label>时间倍率 <input value={scale} onChange={event => setScale(event.target.value)} inputMode="decimal" /></label><button onClick={() => void act(() => client.changeClockScale(worldId, scale), "时间倍率已更改")}>应用倍率</button>
      <button disabled={!snapshot.characters[0]} onClick={() => void act(() => client.scheduleTrigger(worldId, 1_000_000, snapshot.characters[0].character_id), "已为所选角色安排 1 秒后的安全触发器")}>安排 1 秒后的安全触发器</button>
    </div><p className="notice" role="status">{message}</p>
    <div className="panel-grid"><article><h3>地点</h3><Table headers={["名称", "标识"]} rows={snapshot.locations.map(item => [displayName(item.name), short(item.location_id)])} /></article>
      <article><h3>位置分布</h3><Table headers={["类型", "名称", "地点", "活动状态", "可用状态"]} rows={[...snapshot.players.map(item => ["玩家", displayName(item.name), short(item.location_id), label(item.activity, activityLabels), label(item.availability, availabilityLabels)]), ...snapshot.characters.map(item => ["角色", displayName(item.name), item.location_id ? short(item.location_id) : null, "—", "—"])]} /></article></div>
    <article><h3>规范玩家移动</h3><div className="controls"><span>{selectedPlayer ? displayName(selectedPlayer.name) : "没有玩家"}</span><select value={moveDestination} onChange={event => setMoveDestination(event.target.value)}>{snapshot.locations.map(item => <option key={item.location_id} value={item.location_id}>{displayName(item.name)}</option>)}</select><button disabled={!selectedPlayer || !moveDestination} onClick={() => void act(() => client.movePlayer(worldId, selectedPlayer!.player_id, moveDestination), "玩家已通过规范动作解析路径移动")}>移动玩家</button></div></article>
    <article><h3>开放场景</h3><Table headers={["场景", "地点", "参与者", "开始时间"]} rows={snapshot.scenes.map(item => [short(item.scene_id), short(item.location_id), item.participants.map(p => displayName(p.name)).join("、"), worldTime(item.started_at)])} /></article>
    <article><h3>计划触发器</h3><Table headers={["标识", "类型", "状态", "优先级", "到期时间"]} rows={snapshot.triggers.map(item => [short(item.trigger_id), label(item.kind, triggerKindLabels), label(item.status, triggerStatusLabels), priorityLabels[String(item.priority)] ?? item.priority, worldTime(item.due_at)])} /></article>
    <article><h3>模拟激活</h3><Table headers={["标识", "目标", "类型", "优先级", "到期时间", "保真度", "原因数"]} rows={snapshot.activations.map(item => [short(item.activation_id), targetLabel(item.target), label(item.kind, activationKindLabels), priorityLabels[String(item.priority)] ?? item.priority, worldTime(item.due_at), item.fidelity ? label(item.fidelity, fidelityLabels) : "—", item.cause_count])} /></article>
    <article><h3>近期世界事件</h3><Table headers={["账本序号", "类型", "标识", "发生时间"]} rows={snapshot.events.map(item => [item.ledger_position, label(item.type, eventTypeLabels), short(item.event_id), worldTime(item.occurred_at)])} /></article>
    <article><h3>事件观察</h3><Table headers={["观察者", "渠道", "观察标识", "事件标识", "观察时间"]} rows={snapshot.observations.map(item => [displayName(item.principal_name), label(item.channel, channelLabels), short(item.observation_id), short(item.event_id), worldTime(item.observed_at)])} /></article>
    <article><h3>显式情景记忆</h3><div className="controls"><label>记忆所有者 <select value={ownerId} onChange={event => { setOwnerId(event.target.value); setObservationId(""); }}>{snapshot.characters.map(item => <option key={item.character_id} value={item.character_id}>{displayName(item.name)}</option>)}</select></label><label>已授权观察 <select value={observationId} onChange={event => setObservationId(event.target.value)}><option value="">选择证据</option>{authorizedObservations.map(item => <option key={item.observation_id} value={item.observation_id}>{short(item.observation_id)} · {displayName(item.principal_name)}</option>)}</select></label><button disabled={!ownerId || !observationId} onClick={() => void act(() => client.recordMemory(worldId, ownerId, observationId, "我目击了玩家甲在地点之间移动。"), "情景记忆已显式记录")}>记录记忆</button></div>
      <Table headers={["记忆标识", "所有者", "内容", "经历时间", "形成时间", "证据"]} rows={snapshot.memories.map(item => [short(item.memory_id), short(item.owner_character_id), item.content, `${worldTime(item.experienced_from)}–${worldTime(item.experienced_to)}`, worldTime(item.formed_at), item.evidence.map(e => `${short(e.observation_id)}，时间 ${worldTime(e.observed_at)}`).join("；")])} /></article>
  </section>;
}
