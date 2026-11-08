import { useEffect, useRef, useState } from "react";
import type { CoreClient, LibraryCardItem, LibraryCardJoinPreview, WorldSettings } from "@dreamtalk/api-client";
import { InitialLocationChoice } from "../../InitialLocationChoice";
import { CardDialog } from "./CardDialog";
import { CardReview } from "./CardAuthor";
import { libraryFailure } from "./libraryFeedback";
import styles from "./Cards.module.css";

export function CardJoin({ client, card, worlds, target, onSaved, onClose }: { client: CoreClient; card: LibraryCardItem; worlds: WorldSettings[]; target?: string; onSaved: (world: string) => void; onClose: () => void }) {
  const [worldId, setWorldId] = useState(target ?? ""), [preview, setPreview] = useState<LibraryCardJoinPreview | null>(null);
  const [location, setLocation] = useState(""), [canPlace, setCanPlace] = useState(false), [busy, setBusy] = useState(false), busyRef = useRef(false);
  const [error, setError] = useState(""), pending = useRef<{ world: string; importId: string } | null>(null);
  useEffect(() => () => { const value = pending.current; if (value) void client.discardWorldContent(value.world, value.importId).catch(() => undefined); }, [client]);
  useEffect(() => { let alive = true; setCanPlace(false); setLocation(""); if (worldId) void client.selectedPlayer(worldId).then(result => { if (alive) setCanPlace(Boolean(result.player_id)); }).catch(() => undefined); return () => { alive = false; }; }, [client, worldId]);
  const work = async (action: () => Promise<void>) => { if (busyRef.current) return; busyRef.current = true; setBusy(true); setError(""); try { await action(); } catch (failure) { setError(libraryFailure(failure)); } finally { busyRef.current = false; setBusy(false); } };
  const world = worlds.find(item => item.world_id === worldId);
  return <CardDialog title={`将「${card.name}」加入世界`} busy={busy} onClose={() => { if (!busyRef.current) onClose(); }} wide>
    <p>原卡保留在角色卡库。加入后，角色在这个世界拥有独立的内容、聊天、记忆和位置。</p>
    <label>目标世界<select value={worldId} disabled={busy || Boolean(preview)} onChange={event => setWorldId(event.target.value)}><option value="">选择一本世界书</option>{worlds.map(item => <option key={item.world_id} value={item.world_id} disabled={card.world_ids.includes(item.world_id)}>{item.name}{card.world_ids.includes(item.world_id) ? "（已加入）" : ""}</option>)}</select></label>
    {!worlds.length && <p>先在世界书架创建一个世界，再将角色卡加入。</p>}
    {preview && <>{canPlace ? <InitialLocationChoice client={client} worldId={worldId} value={location} onChange={setLocation} disabled={busy} /> : <p className={styles.warning}>初始地点：无。角色可以聊天，但不能移动，也不会显示在地点图中。进入世界设定身份后，可以在角色资料中设置地点。</p>}<CardReview item={preview.content} /></>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    <footer><button type="button" disabled={busy} onClick={onClose}>取消</button>{preview ? <button type="button" className={styles.gold} disabled={busy || !world} onClick={() => void work(async () => { await client.confirmLibraryJoin(card.card_id, worldId, preview, location || null); pending.current = null; onSaved(worldId); onClose(); })}>{busy ? "正在加入…" : `确认加入「${world?.name ?? "世界"}」`}</button> : <button type="button" className={styles.gold} disabled={busy || !world || card.world_ids.includes(worldId)} onClick={() => void work(async () => { const value = await client.previewLibraryJoin(card, worldId); pending.current = { world: worldId, importId: value.content.import_id }; setPreview(value); })}>{busy ? "正在准备…" : "预览加入内容"}</button>}</footer>
  </CardDialog>;
}
