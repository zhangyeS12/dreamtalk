import { useEffect,useRef,useState } from "react";
import type {CoreClient,LibraryCardItem} from "@dreamtalk/api-client";
import {CardFace,CardFaces,useCardImages} from "../world/cards/CardFaces";
import {defaultDesign} from "../world/cards/cardDesign";
export function ArchiveCardArt({client,card}:{client:CoreClient;card:LibraryCardItem}){
  const design=defaultDesign(card),images=useCardImages(client,card.card_id,design);
  const node=useRef<HTMLSpanElement>(null),[scale,setScale]=useState(.65);
  useEffect(()=>{const element=node.current;if(!element)return;const measure=()=>setScale(element.clientWidth/410);measure();const observer=new ResizeObserver(measure);observer.observe(element);return()=>observer.disconnect();},[]);
  return <span ref={node} className="mobile-card-art"><span className="mobile-card-paper" style={{transform:"scale("+scale+")"}}><CardFace design={design} face={design.front} image={images[design.front.image_digest??""]} side="front"/></span></span>;
}
export function ArchiveCardObject({client,card}:{client:CoreClient;card:LibraryCardItem}){
  const design=defaultDesign(card),images=useCardImages(client,card.card_id,design);
  return <CardFaces design={design} images={images}/>;
}
