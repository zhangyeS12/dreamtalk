import {useEffect,useLayoutEffect,useRef,useState} from "react";
import type {CharacterPack,CoreClient,LibraryCardItem} from "@dreamtalk/api-client";
import {CardRing,type Carry} from "../world/cards/CardRing";
export function ArchiveCardDeck({client,cards,pack,disabled,selected,onSelect,onNew,onScope,onFace,faceRequest,onCarry,onDrop,onCancel}:{
  client:CoreClient;cards:LibraryCardItem[];pack:CharacterPack|null;disabled:boolean;selected:string|null;
  onSelect:(id:string|null)=>void;onNew:()=>void;onScope:(pack:CharacterPack|null)=>void;
  faceRequest?:{side:"front"|"back";nonce:number};onFace:(side:"front"|"back")=>void;
  onCarry:(carry:Carry)=>void;onDrop:(carry:Carry)=>void;onCancel:()=>void;
}){
  useEffect(()=>{onScope(pack);return()=>onScope(null);},[pack,onScope]);
  const root=useRef<HTMLDivElement>(null),[width,setWidth]=useState(280);
  useLayoutEffect(()=>{const node=root.current;if(!node)return;
    const measure=()=>setWidth(Math.max(100,Math.min((node.clientWidth||390)*.79,(node.clientHeight||260)*1.18,410)));
    measure();const observer=new ResizeObserver(measure);observer.observe(node);return()=>observer.disconnect();
  },[]);
  const members=pack?new Set(pack.cardIds):null,library=members?cards.filter(card=>members.has(card.card_id)):cards;
  return <div ref={root} className="mobile-native-cards" style={{"--card-w":width+"px"} as React.CSSProperties}>
    <CardRing client={client} cards={library} active={!disabled} locked={disabled} embedded selected={selected}
      onSelect={onSelect} onCreate={onNew} onFace={onFace} faceRequest={faceRequest}
      onCarry={onCarry} onDrop={onDrop} onCancel={onCancel}/>
  </div>;
}
