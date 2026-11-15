import {afterEach,beforeEach,expect,test,vi} from "vitest";
import {act,cleanup,renderHook,waitFor} from "@testing-library/react";
import {CoreRequestError,type CoreClient,type LibraryCardItem} from "@dreamtalk/api-client";
import {defaultPack} from "../world/cards/packs/packDesign";
import {useMobilePacks} from "./useMobilePacks";
beforeEach(()=>vi.stubGlobal("URL",class extends URL{static createObjectURL=vi.fn(()=>"blob:synthetic");static revokeObjectURL=vi.fn();}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});
const cards:LibraryCardItem[]=[];
test("real pack metadata remains usable while optional artwork is pending, with only two parallel reads",async()=>{
  const pack=defaultPack("合成卡包");pack.revision=1;
  pack.design.front.image="a";pack.design.front.source="b";pack.design.back.image="c";pack.design.back.source="d";
  const signals:AbortSignal[]=[];
  const read=vi.fn((_id:string,_digest:string,signal:AbortSignal)=>new Promise<Blob>((_resolve,reject)=>{signals.push(signal);signal.addEventListener("abort",()=>reject(new DOMException("synthetic","AbortError")),{once:true});}));
  const client={cardPacks:vi.fn(async()=>[pack]),packImage:read} as unknown as CoreClient;
  const view=renderHook(()=>useMobilePacks(client,cards));
  await waitFor(()=>expect(view.result.current.loading).toBe(false));
  expect(view.result.current.packs[0].id).toBe(pack.id);expect(read).not.toHaveBeenCalled();
  act(()=>view.result.current.onVisible([pack]));
  await waitFor(()=>expect(read).toHaveBeenCalledTimes(2));
  expect(view.result.current.loading).toBe(false);
  view.unmount();expect(signals.every(signal=>signal.aborted)).toBe(true);
});
test("a conflicting save preserves the original revision and retries the same pack",async()=>{
  let stored=defaultPack("合成卡包");stored.revision=1;
  const save=vi.fn().mockRejectedValueOnce(new CoreRequestError(409)).mockImplementationOnce(async value=>{stored={...value,revision:2};return stored;});
  const client={cardPacks:vi.fn(async()=>[stored]),saveCardPack:save} as unknown as CoreClient;
  const view=renderHook(()=>useMobilePacks(client,cards));await waitFor(()=>expect(view.result.current.loading).toBe(false));
  const draft={...stored,name:"合成新名称"};
  await act(async()=>{await expect(view.result.current.save(draft)).rejects.toBeInstanceOf(CoreRequestError);});
  expect(view.result.current.packs[0].revision).toBe(1);
  await act(async()=>{await view.result.current.save(draft);});
  await waitFor(()=>expect(view.result.current.packs[0].revision).toBe(2));
  expect(save.mock.calls[1][0]).toBe(save.mock.calls[0][0]);
});
test("including a new card updates pack references and keeps the original card in the library",async()=>{
  let stored=defaultPack("合成卡包");stored.revision=1;
  const card={card_id:"synthetic-card",name:"合成人物",revision:1,world_ids:[],design:null} as LibraryCardItem;
  const library=[card],include=vi.fn(async()=>{stored={...stored,revision:2,cardIds:[card.card_id]};return stored;});
  const client={cardPacks:vi.fn(async()=>[stored]),includeCardInPack:include} as unknown as CoreClient;
  const view=renderHook(()=>useMobilePacks(client,library));await waitFor(()=>expect(view.result.current.loading).toBe(false));
  await act(async()=>{await view.result.current.include(stored,card);});
  await waitFor(()=>expect(view.result.current.packs[0].cardIds).toEqual([card.card_id]));
  expect(include).toHaveBeenCalledWith(expect.objectContaining({revision:1}),card.card_id);
  expect(library).toEqual([card]);expect(card.world_ids).toEqual([]);
});
test("failed pack reads stay explicit and do not create demonstration packs",async()=>{
  const view=renderHook(()=>useMobilePacks({cardPacks:vi.fn(async()=>{throw new Error("synthetic");})} as unknown as CoreClient,cards));
  await waitFor(()=>expect(view.result.current.loading).toBe(false));expect(view.result.current.error).toContain("卡包没有完整读取");expect(view.result.current.packs).toEqual([]);
});
