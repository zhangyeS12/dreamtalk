import { useCallback, useEffect, useMemo, useState } from "react";
import { CoreClient, type InspectorSnapshot, type WorldSummary } from "@livingworld/api-client";

interface Props { client: CoreClient }
const short = (value: string) => value.slice(0, 8);
const worldTime = (value: string) => {
  const micros = BigInt(value);
  const seconds = micros / 1_000_000n;
  const hundredths = ((micros % 1_000_000n) / 10_000n).toString().padStart(2, "0");
  return `${seconds}.${hundredths}s (${value}µs)`;
};

function Table({ headers, rows }: { headers: string[]; rows: Array<Array<string | number | null>> }) {
  return <div className="table-wrap"><table><thead><tr>{headers.map(item => <th key={item}>{item}</th>)}</tr></thead>
    <tbody>{rows.length ? rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell ?? "—"}</td>)}</tr>) : <tr><td colSpan={headers.length}>No records</td></tr>}</tbody></table></div>;
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
  useEffect(() => { void loadWorlds().catch(() => setMessage("Could not load developer API")); }, [loadWorlds]);
  useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(), 500); return () => clearInterval(timer); }, [refresh]);

  const act = async (operation: () => Promise<unknown>, label: string) => {
    try { await operation(); setMessage(label); await refresh(); } catch (error) { setMessage(error instanceof Error ? error.message : "Operation failed"); }
  };
  const selectedPlayer = snapshot?.players[0];
  const authorizedObservations = useMemo(() => snapshot?.observations.filter(item => item.principal_kind === "character" && (!ownerId || item.principal_id === ownerId)) ?? [], [snapshot, ownerId]);

  if (!worldId) return <section className="empty"><h2>Developer Runtime Inspector</h2><p>No World exists.</p>
    <button onClick={() => void act(async () => { const created = await client.createDemoWorld(); await loadWorlds(); setWorldId(created.world_id); }, "Neutral demo World created")}>Create neutral demo World</button><p>{message}</p></section>;
  if (!snapshot) return <section><h2>Developer Runtime Inspector</h2><p>Loading current state…</p></section>;
  return <section className="inspector">
    <header className="toolbar"><div><h2>Developer Runtime Inspector</h2><p className="muted">Authenticated developer tooling · real application paths</p></div>
      <div className="controls"><button onClick={() => void act(async () => { const created = await client.createDemoWorld(); await loadWorlds(); setWorldId(created.world_id); }, "Neutral demo World ready")}>Create/load neutral demo</button><label>World<select value={worldId} onChange={event => setWorldId(event.target.value)}>{worlds.map(item => <option key={item.world_id} value={item.world_id}>{item.name}</option>)}</select></label></div></header>
    <div className="status-grid"><article><span>WorldTime</span><strong>{worldTime(snapshot.clock.world_time)}</strong></article><article><span>Clock</span><strong>{snapshot.clock.state}</strong></article><article><span>Scale</span><strong>{snapshot.clock.scale}×</strong></article><article><span>Runtime</span><strong>{snapshot.runtime_state}</strong></article></div>
    <div className="controls">
      <button onClick={() => void act(() => snapshot.clock.state === "running" ? client.pauseWorld(worldId) : client.resumeWorld(worldId), snapshot.clock.state === "running" ? "World paused" : "World resumed")}>{snapshot.clock.state === "running" ? "Pause" : "Resume"}</button>
      <label>Scale <input value={scale} onChange={event => setScale(event.target.value)} inputMode="decimal" /></label><button onClick={() => void act(() => client.changeClockScale(worldId, scale), "Clock scale changed")}>Apply scale</button>
      <button disabled={!snapshot.characters[0]} onClick={() => void act(() => client.scheduleTrigger(worldId, 1_000_000, snapshot.characters[0].character_id), "Safe trigger scheduled for character_a at +1s")}>Schedule safe trigger +1s</button>
    </div><p className="notice" role="status">{message}</p>
    <div className="panel-grid"><article><h3>Locations</h3><Table headers={["Name", "ID"]} rows={snapshot.locations.map(item => [item.name, short(item.location_id)])} /></article>
      <article><h3>Placement</h3><Table headers={["Kind", "Name", "Location"]} rows={[...snapshot.players.map(item => ["Player", item.name, short(item.location_id)]), ...snapshot.characters.map(item => ["Character", item.name, item.location_id ? short(item.location_id) : null])]} /></article></div>
    <article><h3>Canonical move_player</h3><div className="controls"><span>{selectedPlayer?.name ?? "No player"}</span><select value={moveDestination} onChange={event => setMoveDestination(event.target.value)}>{snapshot.locations.map(item => <option key={item.location_id} value={item.location_id}>{item.name}</option>)}</select><button disabled={!selectedPlayer || !moveDestination} onClick={() => void act(() => client.movePlayer(worldId, selectedPlayer!.player_id, moveDestination), "Player moved through ActionResolutionService")}>Move player</button></div></article>
    <article><h3>Open Scenes</h3><Table headers={["Scene", "Location", "Participants", "Started"]} rows={snapshot.scenes.map(item => [short(item.scene_id), short(item.location_id), item.participants.map(p => p.name).join(", "), worldTime(item.started_at)])} /></article>
    <article><h3>ScheduledTriggers</h3><Table headers={["ID", "Kind", "Status", "Priority", "Due"]} rows={snapshot.triggers.map(item => [short(item.trigger_id), item.kind, item.status, item.priority, worldTime(item.due_at)])} /></article>
    <article><h3>SimulationActivations</h3><Table headers={["ID", "Target", "Kind", "Priority", "Due", "Fidelity", "Causes"]} rows={snapshot.activations.map(item => [short(item.activation_id), item.target, item.kind, item.priority, worldTime(item.due_at), item.fidelity, item.cause_count])} /></article>
    <article><h3>Recent WorldEvents</h3><Table headers={["Ledger", "Type", "ID", "Occurred"]} rows={snapshot.events.map(item => [item.ledger_position, item.type, short(item.event_id), worldTime(item.occurred_at)])} /></article>
    <article><h3>Event Observations</h3><Table headers={["Observer", "Channel", "Observation", "Event", "Observed"]} rows={snapshot.observations.map(item => [item.principal_name, item.channel, short(item.observation_id), short(item.event_id), worldTime(item.observed_at)])} /></article>
    <article><h3>Explicit EpisodicMemory</h3><div className="controls"><label>Owner <select value={ownerId} onChange={event => { setOwnerId(event.target.value); setObservationId(""); }}>{snapshot.characters.map(item => <option key={item.character_id} value={item.character_id}>{item.name}</option>)}</select></label><label>Authorized Observation <select value={observationId} onChange={event => setObservationId(event.target.value)}><option value="">Select evidence</option>{authorizedObservations.map(item => <option key={item.observation_id} value={item.observation_id}>{short(item.observation_id)} · {item.principal_name}</option>)}</select></label><button disabled={!ownerId || !observationId} onClick={() => void act(() => client.recordMemory(worldId, ownerId, observationId, "I witnessed player_a move between locations."), "EpisodicMemory explicitly recorded")}>Record memory</button></div>
      <Table headers={["Memory", "Owner", "Content", "Experience", "Formed", "Evidence"]} rows={snapshot.memories.map(item => [short(item.memory_id), short(item.owner_character_id), item.content, `${worldTime(item.experienced_from)}–${worldTime(item.experienced_to)}`, worldTime(item.formed_at), item.evidence.map(e => `${short(e.observation_id)} @ ${worldTime(e.observed_at)}`).join(", ")])} /></article>
  </section>;
}
