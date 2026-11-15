import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CoreClient, WorldSettings } from "@dreamtalk/api-client";
import { MobileWorldCards } from "./WorldCards";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const world=(id: string):WorldSettings=>({world_id:id,name:"合成世界"+id,world_time:"0",time_scale:"1",clock_state:"running",runtime_state:"ready"} as WorldSettings);
test("unavailable artwork cannot block names or world navigation and does not invent a cover", async () => {
  const list=vi.fn(async()=>{throw new Error("synthetic");}), enter=vi.fn();
  render(<MobileWorldCards client={{listWorldCovers:list} as unknown as CoreClient} worlds={[world("a")]} onEnter={enter}/>);
  fireEvent.click(screen.getByRole("button",{name:/合成世界a/}));
  expect(enter).toHaveBeenCalledWith(world("a"));
  await waitFor(()=>expect(list).toHaveBeenCalledTimes(1));
  expect(document.querySelector(".mobile-world-art")).toBeNull();
});
test("cover reads stay at two concurrent images and abort when leaving the world list", async () => {
  const items=Array.from({length:15},(_,i)=>world(String(i))), signals:AbortSignal[]=[];
  const covers=items.map(w=>({world_id:w.world_id,faces:{front:{display:{digest:w.world_id}}}}));
  const read=vi.fn((_world:string,_digest:string,signal:AbortSignal)=>new Promise<Blob>((_resolve,reject)=>{
    signals.push(signal);signal.addEventListener("abort",()=>reject(new DOMException("synthetic","AbortError")),{once:true});
  }));
  const client={listWorldCovers:vi.fn(async()=>covers),coverImage:read} as unknown as CoreClient;
  const view=render(<MobileWorldCards client={client} worlds={items} onEnter={vi.fn()}/>);
  await waitFor(()=>expect(read).toHaveBeenCalledTimes(2));
  view.unmount();expect(signals.every(signal=>signal.aborted)).toBe(true);
  expect(read).toHaveBeenCalledTimes(2);
});
