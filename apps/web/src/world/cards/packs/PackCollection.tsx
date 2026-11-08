import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import type { CharacterPack, LibraryCardItem, LibraryCardRemoval } from "@dreamtalk/api-client";
import { CharacterLibrary } from "../CharacterLibrary";
import { CardPackLibrary } from "./CardPackLibrary";
import type { PackImages } from "./packDesign";
import styles from "./Packs.module.css";

/** Data/resource adapter only. The approved preview uses the same presentation components. */
export function PackCollection(props: ComponentProps<typeof CharacterLibrary>) {
  const { client, onCountChange, onCardRemoved } = props;
  const [packs, setPacks] = useState<CharacterPack[]>([]), [cards, setCards] = useState<LibraryCardItem[]>([]);
  const [ready, setReady] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [imageVersion, setImageVersion] = useState(0);
  const resources = useRef(new Map<string, string>()), pending = useRef(new Map<string, Promise<string>>());
  const controller = useRef(new AbortController()), epoch = useRef(0);
  const loadImage = useCallback((owner: string, digest: string, kind: "pack" | "card" = "pack") => {
    const existing = resources.current.get(digest); if (existing) return Promise.resolve(existing);
    const key = `${kind}:${owner}:${digest}`, waiting = pending.current.get(key); if (waiting) return waiting;
    const signal = controller.current.signal;
    const task = (async () => {
      const blob = await (kind === "pack" ? client.packImage(owner, digest, signal) : client.libraryImage(owner, digest, signal));
      signal.throwIfAborted();
      const cached = resources.current.get(digest); if (cached) return cached;
      const url = URL.createObjectURL(blob); resources.current.set(digest, url); setImageVersion(value => value + 1); return url;
    })().finally(() => { if (pending.current.get(key) === task) pending.current.delete(key); });
    pending.current.set(key, task); return task;
  }, [client]);
  const preload = useCallback(async (items: CharacterPack[], library: LibraryCardItem[]) => {
    await Promise.all([
      ...items.flatMap(pack => [pack.design.front, pack.design.back].flatMap(face => [face.image, face.source].flatMap(ref => ref ? [loadImage(pack.id, ref)] : []))),
      ...library.flatMap(card => card.design?.front.image_digest ? [loadImage(card.card_id, card.design.front.image_digest, "card")] : []),
    ]);
  }, [loadImage]);
  const refresh = useCallback(async () => {
    const read = ++epoch.current, signal = controller.current.signal; setLoading(true); setError("");
    try {
      const [nextPacks, nextCards] = await Promise.all([client.cardPacks(signal), client.libraryCards(signal)]);
      await preload(nextPacks, nextCards);
      if (read !== epoch.current || signal.aborted) return;
      setPacks(nextPacks); setCards(nextCards); setReady(true);
    } catch { if (!signal.aborted && read === epoch.current) setError("卡包或图片未能完整读取，请重新读取。已保存的卡包和角色卡会保留。"); }
    finally { if (!signal.aborted && read === epoch.current) setLoading(false); }
  }, [client, preload]);
  useEffect(() => {
    controller.current = new AbortController(); void refresh();
    const urls = resources.current, requests = pending.current;
    const abort = controller.current;
    return () => { abort.abort(); urls.forEach(url => URL.revokeObjectURL(url)); urls.clear(); requests.clear(); };
  }, [refresh]);
  useEffect(() => onCountChange(cards.length), [cards.length, onCountChange]);
  const countAll = useCallback(() => onCountChange(cards.length), [cards.length, onCountChange]);
  const savedCard = useCallback((card: LibraryCardItem) => {
    setCards(current => current.some(item => item.card_id === card.card_id) ? current.map(item => item.card_id === card.card_id ? card : item) : [...current, card]);
    if (card.design?.front.image_digest) void loadImage(card.card_id, card.design.front.image_digest, "card").catch(() => setError("角色卡已保存，散出预览图片未能读取。请重新读取。"));
  }, [loadImage]);
  const removedCard = useCallback((cardId: string, result: LibraryCardRemoval) => {
    ++epoch.current; setLoading(false); setCards(current => current.filter(item => item.card_id !== cardId)); setPacks(result.packs);
    onCardRemoved?.(cardId, result);
  }, [onCardRemoved]);
  const images = useMemo<PackImages>(() => ({
    url: ref => { void imageVersion; return resources.current.get(ref) ?? ""; },
    upload: async (file, owner) => { if (!owner) throw new Error("未选定卡包，请重新打开设计器。"); const image = await client.uploadPackImage(owner, file); await loadImage(owner, image.digest); return image.digest; },
    crop: async (ref, crop, _ratio, owner) => { if (!owner) throw new Error("未选定卡包，请重新打开设计器。"); const image = await client.cropPackImage(owner, ref, crop); await loadImage(owner, image.digest); return image.digest; },
  }), [client, loadImage, imageVersion]);
  return <>
    {ready && <CardPackLibrary packs={packs} cards={cards} images={images} active={props.active} onEditingChange={props.onEditingChange}
      onSave={async pack => { try { const saved = await client.saveCardPack(pack); setPacks(current => current.some(item => item.id === saved.id) ? current.map(item => item.id === saved.id ? saved : item) : [...current, saved]); setError(""); } catch (failure) { setError("卡包保存结果待核对。可以在设计器内重试同一次保存，或关闭后重新读取。"); throw failure; } }}
      onDiscard={pack => { void client.discardPackDraft(pack.id).catch(() => { /* Unsaved image staging also expires; saved packs are never deleted. */ }); }}
      onDelete={async pack => { await client.deleteCardPack(pack); }} onDeleted={packId => { ++epoch.current; setLoading(false); setPacks(current => current.filter(item => item.id !== packId)); }} onReload={() => void refresh()}
      renderCards={pack => <CharacterLibrary {...props} key={pack?.id ?? "all"} cardIds={pack?.cardIds} initialCards={pack ? pack.cardIds.flatMap(id => { const card = cards.find(item => item.card_id === id); return card ? [card] : []; }) : cards} onCountChange={countAll} onCardSaved={savedCard} onCardRemoved={removedCard}
        onCardCreated={pack ? async card => { const saved = await client.includeCardInPack(pack, card.card_id); setPacks(current => current.map(item => item.id === saved.id ? saved : item)); } : undefined} />} />}
    {props.active && (!ready || error) && <div className={styles.loadState} role={error ? "alert" : "status"}><p>{error || "正在读取你的卡包…"}</p>{error && <button type="button" disabled={loading} onClick={() => void refresh()}>{loading ? "正在读取…" : "重新读取"}</button>}</div>}
  </>;
}
