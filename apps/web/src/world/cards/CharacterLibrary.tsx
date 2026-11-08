import { useCallback, useEffect, useRef, useState } from "react";
import type { CoreClient, LibraryCardItem, LibraryCardRemoval, WorldSettings } from "@dreamtalk/api-client";
import { useDesktopUpdateBlock } from "../../DesktopUpdates";
import { CardRing, CardGhost, type Carry } from "./CardRing";
import { CardAuthor } from "./CardAuthor";
import { CardDesigner } from "./CardDesigner";
import { CardShare } from "./CardShare";
import { CardJoin } from "./CardJoin";
import { CardDialog } from "./CardDialog";
import { DeleteConfirmation } from "./DeleteConfirmation";
import styles from "./Cards.module.css";

export function CharacterLibrary({ client, worlds, active, onBrowseWorlds, onCarryChange, onJoined, onEditingChange, onCountChange, cardIds, initialCards, onCardCreated, onCardSaved, onCardRemoved }: {
  client: CoreClient; worlds: WorldSettings[]; active: boolean; onBrowseWorlds: () => void; onCarryChange: (value: boolean) => void; onJoined: () => void;
  onEditingChange: (value: boolean) => void;
  onCountChange: (value: number) => void;
  cardIds?: string[]; onCardCreated?: (card: LibraryCardItem) => Promise<void>;
  initialCards?: LibraryCardItem[];
  onCardSaved?: (card: LibraryCardItem) => void;
  onCardRemoved?: (cardId: string, result: LibraryCardRemoval) => void;
}) {
  const [cards, setCards] = useState<LibraryCardItem[]>(initialCards ?? []), [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(initialCards === undefined), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [author, setAuthor] = useState<{ card: LibraryCardItem | null } | null>(null), [designer, setDesigner] = useState<LibraryCardItem | null>(null), [join, setJoin] = useState<{ card: LibraryCardItem; world?: string } | null>(null);
  const [share, setShare] = useState<LibraryCardItem | null>(null);
  const [deleting, setDeleting] = useState<LibraryCardItem | null>(null), [removing, setRemoving] = useState<{ card: LibraryCardItem; result: LibraryCardRemoval } | null>(null);
  const [carry, setCarry] = useState<Carry | null>(null), [over, setOver] = useState(false);
  const [faceRequest, setFaceRequest] = useState<{ side: "front" | "back"; nonce: number }>();
  const hoverTimer = useRef(0), hovering = useRef(false), targetNode = useRef<HTMLElement | null>(null);
  const alive = useRef(true), read = useRef(0);
  const scopeKey = cardIds?.join(",");
  const seeded = initialCards !== undefined;
  const worldKeys = worlds.map(item => item.world_id).join(",");
  useEffect(() => onCountChange(cards.length), [cards.length, onCountChange]);
  const refresh = useCallback(async () => {
    const epoch = ++read.current; setLoading(!seeded);
    try { const result = await client.libraryCards(); if (alive.current && epoch === read.current) { const visible = scopeKey === undefined ? result : scopeKey.split(",").flatMap(id => { const card = result.find(item => item.card_id === id); return card ? [card] : []; }); setCards(visible); setSelected(current => visible.some(item => item.card_id === current) ? current : null); setError(""); } }
    catch { if (alive.current && epoch === read.current) setError("角色卡库未能读取，请重新读取。原有卡片不会因此丢失。"); }
    finally { if (alive.current && epoch === read.current) setLoading(false); }
  }, [client, scopeKey, seeded]);
  useEffect(() => { alive.current = true; void refresh(); return () => { alive.current = false; }; }, [refresh, worldKeys]);
  const endCarry = useCallback(() => { window.clearTimeout(hoverTimer.current); hovering.current = false; setCarry(null); setOver(false); onCarryChange(false); targetNode.current?.removeAttribute("data-card-drop"); targetNode.current = null; }, [onCarryChange]);
  useEffect(() => () => { window.clearTimeout(hoverTimer.current); targetNode.current?.removeAttribute("data-card-drop"); }, []);
  const carrying = (value: Carry) => {
    setCarry(value); onCarryChange(true);
    const node = document.elementFromPoint(value.x, value.y);
    const switchOver = Boolean(node?.closest("[data-collection-switch]")); setOver(switchOver);
    if (active && switchOver && !hovering.current) { hovering.current = true; hoverTimer.current = window.setTimeout(() => { onBrowseWorlds(); setSelected(null); }, 550); }
    else if (!switchOver) { hovering.current = false; window.clearTimeout(hoverTimer.current); }
    const book = node?.closest<HTMLElement>("[data-book-key^='world:']") ?? null;
    if (book !== targetNode.current) { targetNode.current?.removeAttribute("data-card-drop"); targetNode.current = book; book?.setAttribute("data-card-drop", ""); }
  };
  const drop = (value: Carry) => {
    const key = document.elementFromPoint(value.x, value.y)?.closest<HTMLElement>("[data-book-key]")?.dataset.bookKey;
    endCarry();
    const world = worlds.find(item => `world:${item.world_id}` === key);
    if (world) { if (value.card.world_ids.includes(world.world_id)) setNotice(`「${value.card.name}」已加入「${world.name}」。`); else setJoin({ card: value.card, world: world.world_id }); }
  };
  const saved = async (card: LibraryCardItem) => {
    onCardSaved?.(card);
    if (cardIds && !cardIds.includes(card.card_id) && !cards.some(item => item.card_id === card.card_id) && onCardCreated) {
      try { await onCardCreated(card); }
      catch { setNotice("角色卡已保存到“全部角色卡”，但装包结果待核对。可返回卡包后在“设计与装卡”中重新选择；不会丢失原卡。"); return; }
    }
    setCards(current => current.some(item => item.card_id === card.card_id) ? current.map(item => item.card_id === card.card_id ? card : item) : [...current, card]); setSelected(card.card_id); setNotice("角色卡已保存。原卡保留在卡库中。"); };
  const card = cards.find(item => item.card_id === selected);
  const modal = Boolean(author || designer || join || share || deleting || removing);
  const finishRemoval = useCallback(() => {
    if (!removing) return;
    ++read.current; setLoading(false);
    setCards(current => current.filter(item => item.card_id !== removing.card.card_id)); setSelected(null); setRemoving(null);
    onCardRemoved?.(removing.card.card_id, removing.result); setNotice("角色卡已删除。已加入世界的角色与聊天仍保留。");
  }, [removing, onCardRemoved]);
  useEffect(() => { onEditingChange(Boolean(designer || deleting || removing)); return () => onEditingChange(false); }, [designer, deleting, removing, onEditingChange]);
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(""), 3400); return () => window.clearTimeout(timer); }, [notice]);
  useDesktopUpdateBlock(modal ? "角色卡正在编辑或确认。" : carry ? "正在拖动角色卡。" : null);
  return <>
    <section className={styles.library} data-active={active || undefined} data-designing={Boolean(designer) || undefined} aria-label="角色卡库" aria-hidden={!active} inert={!active || Boolean(designer || removing)}>
      <div className={styles.sky} aria-hidden="true"><div className={styles.moon} /><div className={styles.hills} /><div className={styles.frontHill} /></div>
      <div className={styles.collectionLabel}><span>角色卡</span><small>{loading ? "正在读取…" : `${cards.length} 张卡 · 首尾相接`}</small></div>
      <CardRing client={client} cards={cards} active={active && !modal} selected={selected} onSelect={setSelected} onCreate={() => setAuthor({ card: null })} locked={loading || modal || Boolean(error)} onCarry={carrying} onDrop={drop} onCancel={endCarry} faceRequest={faceRequest} removingId={removing?.card.card_id} onRemovalComplete={finishRemoval} />
      {card ? <><div className={styles.selectedInfo}><div><h2>{card.design?.display_name || card.name}</h2><p>{card.design?.subtitle || "角色档案"}</p></div>
        <div className={styles.row}><button type="button" onClick={() => setDesigner(card)}>✧ <span>设计卡面</span></button><button type="button" className={styles.gold} onClick={() => setJoin({ card })}>加入世界 <span aria-hidden="true">↗</span></button></div>
      </div><div className={styles.faceControls}>{(["front", "back"] as const).map(side => <button key={side} type="button" onClick={() => setFaceRequest(current => ({ side, nonce: (current?.nonce ?? 0) + 1 }))}>{side === "front" ? "正面" : "背面"}</button>)}<button type="button" onClick={() => setSelected(null)}>归位 <span aria-hidden="true">×</span></button></div><div className={styles.secondaryActions}><button className={styles.settingsLink} type="button" onClick={() => setAuthor({ card })}>角色设定</button><button className={styles.settingsLink} type="button" onClick={() => setShare(card)}>分享角色卡</button><button className={styles.settingsLink} data-delete type="button" onClick={() => setDeleting(card)}>删除角色卡</button></div></> : null}
      <p className={styles.hint}>{card ? "拖动卡片转动查看 · Esc 或点击空白处收起" : "左右拖动空白处浏览卡片 · 拖动悬浮卡到下方胶囊，再放到世界书上"}</p>
      <div className={styles.libraryNotices}>{error && <p role="alert">{error}<button type="button" disabled={loading} onClick={() => void refresh()}>重新读取</button></p>}{notice && <p role="status">{notice}</p>}</div>
    </section>
    {carry && <><CardGhost client={client} carry={carry} /><div className={styles.dragCaption} style={{ left: carry.x - 110, top: carry.y + 90 }}>{active ? over ? "稍等片刻，切换到世界书…" : "拖到下方切换胶囊" : "放到一本世界书上 · Esc取消"}</div></>}
    {over && carry && <div className={styles.switchGlow} aria-hidden="true" />}
    {author && <CardAuthor client={client} editing={author.card} onSaved={saved} onClose={() => setAuthor(null)} />}
    {designer && <CardDesigner client={client} card={designer} onSaved={saved} onClose={() => setDesigner(null)} />}
    {share && <CardShare client={client} card={share} onClose={() => setShare(null)} />}
    {deleting && <DeleteConfirmation kind="角色卡" name={deleting.name} onClose={() => setDeleting(null)} onReload={() => { setDeleting(null); void refresh(); }} onConfirm={async () => { const result = await client.deleteLibraryCard(deleting); ++read.current; setRemoving({ card: deleting, result }); setDeleting(null); }} />}
    {removing && <p className={styles.removalStatus} role="status">角色卡正在化作粒子消散…</p>}
    {join && <CardJoin client={client} card={join.card} worlds={worlds} target={join.world} onClose={() => setJoin(null)} onSaved={worldId => { setCards(current => current.map(item => item.card_id === join.card.card_id ? { ...item, world_ids: [...new Set([...item.world_ids, worldId])] } : item)); setNotice(`「${join.card.name}」已加入世界，原卡仍在卡库。`); onJoined(); }} />}
    {!active && notice && <p className={styles.crossNotice} role="status">{notice}</p>}
  </>;
}

export function CardGuide({ onClose }: { onClose: () => void }) {
  return <CardDialog title="从一张卡，到一个世界" onClose={onClose} className={styles.guideDialog}>
    <ol className={styles.guideSteps}><li><strong>挑选角色卡</strong><p>切到角色卡，选择卡包，横向划开顶部封口；也可点“全部角色卡”。新卡可从空白卡位创建，再在“设计与装卡”中装包。卡片弹出后可转动、设计或加入世界。</p></li><li><strong>拿起，再跨页</strong><p>在自然悬浮状态下按住卡片，拖到下方胶囊并稍作停留。展开查看或DIY时，卡片主体固定。切回世界书后，继续按住拖动。</p></li><li><strong>放进某本书里</strong><p>目标世界书亮起金色边缘时松手，选择初始地点并确认。默认地点为“无”。</p></li></ol><p>卡库中的原卡始终保留。也可使用“加入世界”按钮完成相同操作。</p><p>左右方向键切换；Esc取消拖动、退出查看或关闭面板。</p><footer><button type="button" className={styles.gold} onClick={onClose}>开始体验</button></footer>
  </CardDialog>;
}
