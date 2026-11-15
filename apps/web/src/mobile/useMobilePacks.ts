import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CharacterPack, CoreClient, LibraryCardItem } from "@dreamtalk/api-client";
import type { PackImages } from "../world/cards/packs/packDesign";

/** Android data adapter; the pack geometry, seal, editor and CAS APIs remain shared. */
export function useMobilePacks(client:CoreClient,cards:LibraryCardItem[]) {
  const [packs,setPacks]=useState<CharacterPack[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState("");
  const [reload,setReload]=useState(0),[visible,setVisible]=useState<CharacterPack[]>([]),[version,setVersion]=useState(0);
  const epoch=useRef(0),alive=useRef(false),controller=useRef(new AbortController());
  const resources=useRef(new Map<string,string>()),pending=useRef(new Map<string,Promise<string>>());
  const required=useRef(new Set<string>()),queue=useRef<Array<()=>void>>([]),running=useRef(0);
  useEffect(()=>{
    alive.current=true;controller.current=new AbortController();
    const cache=resources.current,requests=pending.current,waiting=queue.current;
    return()=>{alive.current=false;controller.current.abort();cache.forEach(url=>URL.revokeObjectURL(url));cache.clear();requests.clear();waiting.splice(0).forEach(start=>start());};
  },[]);
  useEffect(()=>{
    const abort=new AbortController(),read=++epoch.current;setLoading(true);
    client.cardPacks(abort.signal).then(value=>{if(!abort.signal.aborted&&read===epoch.current){setPacks(value);setError("");}})
      .catch(()=>{if(!abort.signal.aborted&&read===epoch.current)setError("卡包没有完整读取，已保留现有内容。可以重新读取或查看全部角色卡。");})
      .finally(()=>{if(!abort.signal.aborted&&read===epoch.current)setLoading(false);});
    return()=>abort.abort();
  },[client,reload]);
  const load=useCallback((owner:string,digest:string,kind:"pack"|"card"="pack",force=false)=>{
    const cached=resources.current.get(digest);if(cached)return Promise.resolve(cached);
    const key=kind+":"+owner+":"+digest,existing=pending.current.get(key);if(existing)return existing;
    const signal=controller.current.signal;
    const promise=new Promise<string>((resolve,reject)=>{
      const start=()=>{
        if(signal.aborted||!alive.current||!force&&!required.current.has(digest)){reject(new DOMException("cancelled","AbortError"));return;}
        running.current++;
        void (kind==="pack"?client.packImage(owner,digest,signal):client.libraryImage(owner,digest,signal)).then(blob=>{
          if(signal.aborted||!alive.current)throw new DOMException("cancelled","AbortError");
          const known=resources.current.get(digest);if(known)return known;
          const url=URL.createObjectURL(blob);resources.current.set(digest,url);
          for(const [oldKey,oldUrl] of resources.current){
            if(resources.current.size<=32)break;
            if(oldKey!==digest&&!required.current.has(oldKey)){URL.revokeObjectURL(oldUrl);resources.current.delete(oldKey);}
          }
          setVersion(value=>value+1);return url;
        }).then(resolve,reject).finally(()=>{
          running.current--;const next=queue.current.shift();if(next)next();
        });
      };
      if(running.current<2)start();else queue.current.push(start);
    }).finally(()=>{if(pending.current.get(key)===promise)pending.current.delete(key);});
    pending.current.set(key,promise);return promise;
  },[client]);
  const onVisible=useCallback((next:CharacterPack[])=>setVisible(current=>{
    const identity=(items:CharacterPack[])=>items.map(item=>item.id+":"+item.revision).join("|");
    return identity(current)===identity(next)?current:next;
  }),[]);
  useEffect(()=>{
    const refs:Array<{owner:string;digest:string;kind:"pack"|"card"}>=visible.flatMap(pack=>[pack.design.front,pack.design.back].flatMap(face=>[face.image,face.source].flatMap(digest=>digest?[{owner:pack.id,digest,kind:"pack" as const}]:[])));
    const members=new Set(visible.flatMap(pack=>pack.cardIds.slice(0,16)));
    refs.push(...cards.filter(card=>members.has(card.card_id)).flatMap(card=>card.design?.front.image_digest?[{owner:card.card_id,digest:card.design.front.image_digest,kind:"card" as const}]:[]));
    required.current=new Set(refs.map(ref=>ref.digest));
    for(const ref of refs)void load(ref.owner,ref.digest,ref.kind).catch(()=>{/* Optional artwork keeps its saved text and design. */});
  },[visible,cards,load]);
  const images=useMemo<PackImages>(()=>({
    url:ref=>{void version;return resources.current.get(ref)??"";},
    upload:async(file,owner)=>{if(!owner)throw new Error("请先选择卡包。");const image=await client.uploadPackImage(owner,file);await load(owner,image.digest,"pack",true);return image.digest;},
    crop:async(ref,crop,_ratio,owner)=>{if(!owner)throw new Error("请先选择卡包。");const image=await client.cropPackImage(owner,ref,crop);await load(owner,image.digest,"pack",true);return image.digest;},
  }),[client,load,version]);
  const saved=useCallback((pack:CharacterPack)=>{++epoch.current;setPacks(current=>current.some(item=>item.id===pack.id)?current.map(item=>item.id===pack.id?pack:item):[...current,pack]);setError("");setLoading(false);},[]);
  const save=useCallback(async(pack:CharacterPack)=>{saved(await client.saveCardPack(pack));setReload(value=>value+1);},[client,saved]);
  const include=useCallback(async(pack:CharacterPack,card:LibraryCardItem)=>{saved(await client.includeCardInPack(pack,card.card_id));setReload(value=>value+1);},[client,saved]);
  const removed=useCallback((id:string)=>{++epoch.current;setLoading(false);setPacks(current=>current.filter(pack=>pack.id!==id));},[]);
  const refresh=useCallback(()=>setReload(value=>value+1),[]);
  return {packs,loading,error,images,onVisible,save,saved,include,removed,refresh};
}
