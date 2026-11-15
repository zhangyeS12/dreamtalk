import { useCallback, useEffect, useRef, useState, useMemo, type FormEvent } from "react";
import type { CharacterPack, CoreClient, LibraryCardItem, WorldSettings } from "@dreamtalk/api-client";
import { ArrowLeft, MoreHorizontal, Plus, Settings2, X, ChevronDown, Palette, RotateCcw } from "lucide-react";
import { Brand } from "../Brand";
import { ExampleWorldPanel } from "../ExampleWorldPanel";
import { useWorldCovers } from "../useWorldCovers";
import { type ShelfAppearance } from "../world/archive/Book3D";
import { shelfAppearance } from "../world/archive/bookLook";
import { type ShelfFace } from "../world/archive/bookDesign";
import { BookDesigner } from "../world/archive/BookDesigner";
import { skyAt, skyOf, worldClock, formatClock } from "../world/sky";
import { CardDialog } from "../world/cards/CardDialog";
import { CardAuthor } from "../world/cards/CardAuthor";
import { CardDesigner } from "../world/cards/CardDesigner";
import { CardJoin } from "../world/cards/CardJoin";
import { CardShare } from "../world/cards/CardShare";
import { DeleteConfirmation } from "../world/cards/DeleteConfirmation";
import { libraryFailure } from "../world/cards/libraryFeedback";
import { MobileSettings } from "./Settings";
import { mobileInvoke } from "./native";
import { NativeBookShelf } from "./NativeBookShelf";
import { CardGhost, type Carry } from "../world/cards/CardRing";
import { ArchiveRoom, archiveSky } from "../world/archive/ArchiveRoom";
import cardStyles from "../world/cards/Cards.module.css";
import { CardPackLibrary } from "../world/cards/packs/CardPackLibrary";
import { useMobilePacks } from "./useMobilePacks";
import { ArchiveCardDeck } from "./ArchiveCardDeck";

type CardModal = {kind:"view"|"edit"|"design"|"join"|"share"|"delete";card:LibraryCardItem;target?:string}|{kind:"create"};
type FaceRequest={face:ShelfFace;nonce:number};
export function MobileArchiveHome({client,onEnter,reconnect,onDirtyRoot}:{
  client:CoreClient;onEnter:(world:WorldSettings)=>void;reconnect:()=>Promise<void>;onDirtyRoot:(dirty:boolean)=>void;
}){
  const [worlds,setWorlds]=useState<WorldSettings[]>([]),[cards,setCards]=useState<LibraryCardItem[]>([]);
  const [loading,setLoading]=useState(true),[cardsLoading,setCardsLoading]=useState(true);
  const [error,setError]=useState(""),[cardError,setCardError]=useState(""),[notice,setNotice]=useState("");
  const [reload,setReload]=useState(0),[cardReload,setCardReload]=useState(0);
  const [settings,setSettings]=useState(false),[settingsDirty,setSettingsDirty]=useState(false);
  const [createWorld,setCreateWorld]=useState(false),[example,setExample]=useState(false),[exampleBusy,setExampleBusy]=useState(false);
  const [name,setName]=useState(""),[creating,setCreating]=useState(false);
  const creation=useRef<{id:string;name:string}|null>(null),createLock=useRef(false);
  const [selectedWorld,setSelectedWorld]=useState<WorldSettings|null>(null);
  const [bookReady,setBookReady]=useState(false),[carry,setCarry]=useState<Carry|null>(null);
  const dropNode=useRef<HTMLElement|null>(null);
  const [bookFace,setBookFace]=useState<ShelfFace>("front"),[bookRequest,setBookRequest]=useState<FaceRequest>();
  const [designingBook,setDesigningBook]=useState(false),[bookDraft,setBookDraft]=useState<ShelfAppearance|null>(null);
  const [bookDirty,setBookDirty]=useState(false),[bookBusy,setBookBusy]=useState(false);
  const [modal,setModal]=useState<CardModal|null>(null);
  const [cardSide,setCardSide]=useState<ShelfFace>("front"),[cardRequest,setCardRequest]=useState<FaceRequest>();
  const [visibleWorlds,setVisibleWorlds]=useState<string[]>([]);
  const [packPhase,setPackPhase]=useState("browse"),[packEditing,setPackEditing]=useState(false),[packScope,setPackScope]=useState<CharacterPack|null>(null);
  const [newCardPack,setNewCardPack]=useState<CharacterPack|null>(null),[entering,setEntering]=useState(false);
  const [revealLibraryRequest,setRevealLibraryRequest]=useState<number>();
  const enterTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const [lastWorldId]=useState(()=>{try{return localStorage.getItem("livingworld.lastWorldId");}catch{return null;}});
  const showWorlds=useCallback((ids:string[])=>setVisibleWorlds(ids.filter(id=>!id.startsWith("blank:"))),[]);
  const coverIds=selectedWorld?[...visibleWorlds,selectedWorld.world_id]:visibleWorlds;
  const covers=useWorldCovers(client,undefined,!settings,coverIds),packs=useMobilePacks(client,cards);
  const [defaultBudget,setDefaultBudget]=useState(()=>Number(localStorage.getItem("livingworld.turnTokenCeiling"))||131072);
  const selectedCard=modal&&"card" in modal?modal.card:null;
  const nativeCardRequest=useMemo(()=>cardRequest?{side:cardRequest.face==="back"?"back" as const:"front" as const,nonce:cardRequest.nonce}:undefined,[cardRequest]);
  const businessModal=Boolean(modal&&modal.kind!=="view");
  const globallyBlocked=businessModal||createWorld||example||designingBook||packEditing||entering;
  const viewedWorld=worlds.find(world=>world.world_id===selectedWorld?.world_id)??selectedWorld;
  const sky=archiveSky(worlds.find(world=>world.world_id===lastWorldId));
  useEffect(()=>{onDirtyRoot(settingsDirty||createWorld&&Boolean(name||creation.current)||example||businessModal||bookDirty||bookBusy||packEditing);},[onDirtyRoot,settingsDirty,createWorld,name,example,businessModal,bookDirty,bookBusy,packEditing]);
  useEffect(()=>()=>{onDirtyRoot(false);clearTimeout(enterTimer.current);},[onDirtyRoot]);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);
    client.listProductWorlds(controller.signal).then(value=>{if(!controller.signal.aborted){setWorlds(value);setError("");}})
      .catch(()=>{if(!controller.signal.aborted)setError("世界列表没有读取成功，请重试。");})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[client,reload]);
  useEffect(()=>{
    const abort=new AbortController();const timer=setInterval(()=>{
      if(document.hidden)return;
      void client.listProductWorlds(abort.signal).then(value=>{if(!abort.signal.aborted)setWorlds(value);}).catch(()=>{/* Retain the last confirmed sky and world state. */});
    },15000);return()=>{clearInterval(timer);abort.abort();};
  },[client]);
  useEffect(()=>{
    const controller=new AbortController();setCardsLoading(true);
    client.libraryCards(controller.signal).then(value=>{if(!controller.signal.aborted){setCards(value);setCardError("");}})
      .catch(failure=>{if(!controller.signal.aborted)setCardError(libraryFailure(failure));})
      .finally(()=>{if(!controller.signal.aborted)setCardsLoading(false);});
    return()=>controller.abort();
  },[client,cardReload]);
  const viewCard=useCallback((card:LibraryCardItem)=>{setNotice("");setCardSide("front");setCardRequest(undefined);setModal({kind:"view",card});},[]);
  const endCarry=useCallback(()=>{dropNode.current?.removeAttribute("data-card-drop");dropNode.current=null;setCarry(null);},[]);
  useEffect(()=>()=>dropNode.current?.removeAttribute("data-card-drop"),[]);
  const changePackPhase=useCallback((phase:string)=>{
    setPackPhase(phase);
    if(phase==="cards"||phase==="opening"||phase==="spilling")return;
    setModal(current=>current?.kind==="view"?null:current);
    setCardSide("front");setCardRequest(undefined);endCarry();
  },[endCarry]);

  const carrying=(value:Carry)=>{
    setCarry(value);const node=document.elementFromPoint(value.x,value.y)?.closest<HTMLElement>("[data-book-key^='world:']")??null;
    if(node!==dropNode.current){dropNode.current?.removeAttribute("data-card-drop");dropNode.current=node;node?.setAttribute("data-card-drop","");}
  };
  const drop=(value:Carry)=>{
    const key=document.elementFromPoint(value.x,value.y)?.closest<HTMLElement>("[data-book-key]")?.dataset.bookKey;
    endCarry();const world=worlds.find(item=>"world:"+item.world_id===key);
    if(world){if(value.card.world_ids.includes(world.world_id))setNotice("这位角色已加入该世界，原卡仍保留。");else setModal({kind:"join",card:value.card,target:world.world_id});}
  };
  const newCard=()=>{setNewCardPack(packScope);setModal({kind:"create"});};
  const saveCard=async(card:LibraryCardItem)=>{
    let outcome="角色卡已保存。",inclusionFailed=false;
    setCards(current=>current.some(item=>item.card_id===card.card_id)?current.map(item=>item.card_id===card.card_id?card:item):[...current,card]);
    setCardReload(value=>value+1);
    if(modal?.kind==="create"&&newCardPack){
      try{await packs.include(newCardPack,card);outcome="角色卡已保存并装入卡包，原卡保留。";}
      catch{inclusionFailed=true;packs.refresh();outcome="原卡已保存，装包结果待核对。请重新读取或从设计与装卡中确认。";}
    }
    if(modal?.kind==="create"&&(packPhase!=="cards"||inclusionFailed))setRevealLibraryRequest(value=>(value??0)+1);
    setNewCardPack(null);viewCard(card);setNotice(outcome);
  };
  const returnToCard=(card:LibraryCardItem)=>setModal(current=>current?.kind==="view"?current:{kind:"view",card});
  const closeCreate=()=>{
    if(createLock.current)return;
    if(name&&!window.confirm("世界名称尚未保存，暂时收起？"))return;setCreateWorld(false);
  };
  const create=async(event:FormEvent)=>{
    event.preventDefault();if(createLock.current||!name.trim())return;
    createLock.current=true;setCreating(true);setError("");creation.current??={id:crypto.randomUUID(),name:name.trim()};
    try{await client.createWorld(creation.current.name,creation.current.id);creation.current=null;setName("");setCreateWorld(false);setReload(value=>value+1);setNotice("世界已放上书架，点开书本即可进入。");}
    catch{setError("创建结果尚未确认。重试会核对同一次创建，不会重复新建。");}
    finally{createLock.current=false;setCreating(false);}
  };
  const closeBook=()=>{if(!entering&&!bookBusy&&(!bookDirty||window.confirm("书本设计尚未保存，放弃修改？"))){setSelectedWorld(null);setDesigningBook(false);setBookDraft(null);setBookDirty(false);}};
  const enter=(world:WorldSettings)=>{
    if(entering)return;
    try{localStorage.setItem("livingworld.lastWorldId",world.world_id);}catch{/* Optional last view only. */}
    if(matchMedia("(prefers-reduced-motion: reduce)").matches){onEnter(world);return;}
    setEntering(true);enterTimer.current=setTimeout(()=>onEnter(world),180);
  };
  if(settings)return <div className="mobile-world-list"><header className="mobile-top"><button className="mobile-icon-action" aria-label="返回书架" onClick={()=>{if(!settingsDirty||window.confirm("有未保存的设置，确定离开吗？")){setSettingsDirty(false);setSettings(false);}}}><ArrowLeft size={21}/></button><h1>应用设置</h1></header><main className="mobile-page"><MobileSettings client={client} onConfigured={reconnect} budget={defaultBudget} onBudget={value=>{setDefaultBudget(value);try{localStorage.setItem("livingworld.turnTokenCeiling",String(value));}catch{/* Session value remains applied. */}}} onDirtyChange={setSettingsDirty}/></main></div>;
  const shelfAppearances=Object.fromEntries(worlds.map(world=>[world.world_id,bookDraft&&viewedWorld?.world_id===world.world_id?bookDraft:shelfAppearance(covers.appearances[world.world_id],world.name)]));
  return <main className="mobile-archive-home" aria-label="书架与角色卡">
    <section className="mobile-archive-half mobile-archive-upper" aria-labelledby="mobile-books-heading" data-expanded={Boolean(selectedWorld)||undefined} data-entering={entering||undefined}>
      <div className="mobile-archive-room" style={sky.style}><ArchiveRoom body={sky.body}/></div>
      <header className="mobile-archive-brand">
        <div className="mobile-archive-identity"><Brand/><h2 id="mobile-books-heading">世界书架</h2><small>{viewedWorld?<><span>{viewedWorld.name}</span><span className="mobile-world-clock">{viewedWorld.clock_state==="paused"?"暂停 · ":""}{worldClock(viewedWorld.world_time)?formatClock(worldClock(viewedWorld.world_time)!):viewedWorld.world_time}</span></>:worlds.length+" 个世界 · 首尾相接"}</small></div>
        <div><button className="mobile-icon-action" aria-label="新世界" disabled={globallyBlocked} onClick={()=>setCreateWorld(true)}><Plus size={19}/></button><button className="mobile-icon-action" aria-label="应用设置" disabled={globallyBlocked} onClick={()=>setSettings(true)}><Settings2 size={19}/></button></div>
      </header>
      <div className="mobile-book-scene" data-entering={entering||undefined}>
        <NativeBookShelf worlds={worlds} appearances={shelfAppearances} selectedKey={viewedWorld?"world:"+viewedWorld.world_id:null} initialWorldId={lastWorldId}
          loading={loading} disabled={globallyBlocked||Boolean(carry)} onVisible={showWorlds}
          onSelect={id=>{const world=worlds.find(item=>item.world_id===id);if(world){setBookReady(false);setSelectedWorld(world);setBookFace("front");setBookRequest(undefined);}}}
          onCreate={()=>setCreateWorld(true)} onClose={closeBook} onSettled={key=>setBookReady(Boolean(key))} faceRequest={bookRequest} onFace={setBookFace}/>
      </div>
      <footer className="mobile-book-dock">
        {viewedWorld?<div className="mobile-object-actions" role="group" aria-label={"世界书操作："+viewedWorld.name}>
          <details className="mobile-face-menu"><summary aria-label="切换书本面">{{front:"正面",spine:"书脊",back:"背面",edge:"书口"}[bookFace]}<ChevronDown size={12}/></summary><div>{(["front","spine","back","edge"] as const).map((face,index)=><button key={face} aria-pressed={bookFace===face} onClick={event=>{setBookRequest({face,nonce:performance.now()});event.currentTarget.closest("details")?.removeAttribute("open");}}>{["正面","书脊","背面","书口"][index]}</button>)}</div></details>
          <button aria-label="设计书本" disabled={!bookReady||globallyBlocked} onClick={()=>setDesigningBook(true)}><Palette size={15}/><span>设计</span></button>
          <button aria-label="进入世界" className="mobile-object-primary" disabled={!bookReady||globallyBlocked} onClick={()=>enter(viewedWorld)}>进入世界<span aria-hidden="true">↗</span></button>
          <button aria-label="归位世界书" disabled={entering} onClick={closeBook}><X size={16}/><span>归位</span></button>
        </div>:<div className="mobile-archive-caption"><span>{loading?"正在读取档案…":"拖动书列 · 轻点抽出"}</span><button disabled={globallyBlocked} onClick={()=>setExample(true)}>案例世界 ↗</button></div>}
      </footer>
      {error&&<p className="mobile-archive-feedback" role="alert">{error}<button onClick={()=>setReload(value=>value+1)}>重试</button></p>}
    </section>
    <section className="mobile-archive-half mobile-archive-lower" aria-labelledby="mobile-cards-heading" data-expanded={Boolean(selectedCard)||undefined} data-pack-phase={packPhase}>
      <div className={"mobile-archive-card-sky "+cardStyles.sky} aria-hidden="true"><div className={cardStyles.moon}/><div className={cardStyles.hills}/><div className={cardStyles.frontHill}/></div>
      <header className="mobile-card-heading"><div><h2 id="mobile-cards-heading">角色卡与卡包</h2><small>{selectedCard?selectedCard.design?.display_name||selectedCard.name:cardsLoading||packs.loading?"正在读取收藏…":packs.packs.length+" 个卡包 · "+cards.length+" 张角色卡"}</small></div><button className="mobile-archive-add" disabled={cardsLoading||globallyBlocked} onClick={newCard}><Plus size={17}/>新卡／导入</button></header>
      <div className="mobile-pack-region">
        <CardPackLibrary packs={packs.packs} cards={cards} images={packs.images} active={!createWorld&&!example&&!designingBook}
          embedded revealLibraryRequest={revealLibraryRequest} onPhaseChange={changePackPhase} onEditingChange={setPackEditing} onVisiblePacks={packs.onVisible}
          onSave={packs.save} onDiscard={pack=>{void client.discardPackDraft(pack.id).catch(()=>undefined);}} onDelete={pack=>client.deleteCardPack(pack).then(()=>undefined)} onDeleted={packs.removed} onReload={packs.refresh}
          renderCards={pack=><ArchiveCardDeck client={client} cards={cards} pack={pack} disabled={globallyBlocked||cardsLoading||!!cardError} selected={selectedCard?.card_id??null}
            onSelect={id=>{const card=cards.find(item=>item.card_id===id);if(card)viewCard(card);else setModal(null);}} onNew={()=>{setNewCardPack(pack);setModal({kind:"create"});}} onScope={setPackScope}
            faceRequest={nativeCardRequest} onFace={setCardSide} onCarry={carrying} onDrop={drop} onCancel={endCarry}/>}/>
      </div>
      {selectedCard?<footer className="mobile-card-dock"><div className="mobile-object-actions" role="group" aria-label={"角色卡操作："+selectedCard.name}>
        <button aria-label={cardSide==="back"?"正面":"背面"} onClick={()=>setCardRequest({face:cardSide==="back"?"front":"back",nonce:performance.now()})}><RotateCcw size={15}/><span>翻面</span></button>
        <button aria-label="设计卡面" onClick={()=>setModal({kind:"design",card:selectedCard})}><Palette size={15}/><span>设计</span></button>
        <button aria-label="加入世界" className="mobile-object-primary" onClick={()=>setModal({kind:"join",card:selectedCard})}>加入世界 ↗</button>
        <details className="mobile-archive-more"><summary aria-label="角色卡更多操作"><MoreHorizontal size={19}/></summary><div><button onClick={()=>setModal({kind:"edit",card:selectedCard})}>编辑角色设定</button><button onClick={()=>setModal({kind:"share",card:selectedCard})}>分享 CHARX</button><button onClick={()=>setModal({kind:"delete",card:selectedCard})}>删除角色卡</button></div></details>
        <button aria-label="归位角色卡" onClick={()=>setModal(null)}><X size={16}/></button>
      </div></footer>:packPhase==="cards"?<p className="mobile-card-browse-hint">左右滑动浏览 · 上拖角色卡加入世界</p>:null}
      {(cardError||packs.error)?<p className="mobile-archive-feedback" role="alert">{cardError||packs.error}<button onClick={()=>{setCardReload(value=>value+1);packs.refresh();}}>重试</button></p>:notice?<p className="mobile-scene-notice" role="status">{notice}</p>:null}
    </section>
    {carry&&<><CardGhost client={client} carry={carry}/><div className="mobile-card-carry-label">放到上半屏的一本世界书上 · 松手后预览确认</div></>}
    {covers.error&&<span className="mobile-archive-art-warning" role="status">{covers.error}</span>}
    {createWorld&&<CardDialog title="开启一个新世界" onClose={closeCreate} busy={creating}><form className="mobile-form" onSubmit={event=>void create(event)}><label>新世界名称<input required maxLength={120} disabled={creating||!!creation.current} value={name} onChange={event=>setName(event.target.value)}/></label>{error&&<p role="alert">{error}</p>}<footer><button type="button" onClick={closeCreate} disabled={creating}>取消</button><button className="primary-button" disabled={creating}>{creating?"正在创建…":creation.current?"核对并重试创建":"创建世界"}</button></footer></form></CardDialog>}
    {example&&<CardDialog title="案例世界" onClose={()=>{if(!exampleBusy)setExample(false);}} busy={exampleBusy} wide><ExampleWorldPanel client={client} onBusy={setExampleBusy} onClose={()=>setExample(false)} onCreated={async id=>{const all=await client.listProductWorlds();setWorlds(all);setExample(false);const next=all.find(item=>item.world_id===id);if(next)enter(next);}}/></CardDialog>}
    {designingBook&&viewedWorld&&<CardDialog title="设计世界书" onClose={()=>{if(!bookBusy&&(!bookDirty||window.confirm("书本设计尚未保存，放弃修改？"))){setDesigningBook(false);setBookDraft(null);}}} busy={bookBusy} wide><div className="mobile-book-designer"><BookDesigner client={client} world={viewedWorld} sky={skyOf(viewedWorld)??skyAt(0)} face={bookFace} onFaceRequest={face=>setBookRequest({face,nonce:performance.now()})} onDraft={setBookDraft} onDirty={setBookDirty} onBusy={setBookBusy} onSaved={cover=>{covers.saved(cover);setBookDirty(false);setNotice("书本设计已保存。");}} onClose={()=>{setDesigningBook(false);setBookDraft(null);}}/></div></CardDialog>}
    {modal&&(modal.kind==="create"||modal.kind==="edit")&&<CardAuthor client={client} editing={modal.kind==="edit"?modal.card:null} onSaved={saveCard} onClose={()=>{if(modal.kind==="edit")returnToCard(modal.card);else setModal(current=>current?.kind==="view"?current:null);}}/>}
    {modal?.kind==="design"&&<CardDesigner client={client} card={modal.card} onSaved={saveCard} onClose={()=>returnToCard(modal.card)}/>}
    {modal?.kind==="share"&&<CardShare client={client} card={modal.card} nativeInvoke={mobileInvoke} onClose={()=>returnToCard(modal.card)}/>}
    {modal?.kind==="join"&&<CardJoin client={client} card={modal.card} worlds={worlds} target={modal.target} onClose={()=>returnToCard(modal.card)} onSaved={worldId=>{const card={...modal.card,world_ids:[...new Set([...modal.card.world_ids,worldId])]};setCards(current=>current.map(item=>item.card_id===card.card_id?card:item));setModal({kind:"view",card});setNotice("角色已加入世界，原卡保留在卡库。");}}/>}
    {modal?.kind==="delete"&&<DeleteConfirmation kind="角色卡" name={modal.card.name} onClose={()=>returnToCard(modal.card)} onReload={()=>{setModal(null);setCardReload(value=>value+1);packs.refresh();}} onConfirm={async()=>{const result=await client.deleteLibraryCard(modal.card);setCards(current=>current.filter(card=>card.card_id!==modal.card.card_id));for(const pack of result.packs)packs.saved(pack);packs.refresh();setModal(null);setNotice("库卡已删除，各世界副本保留。");}}/>}
  </main>;
}
