import {act} from "react";
import {afterEach,beforeEach,expect,test,vi} from "vitest";
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import type {LibraryCardItem} from "@dreamtalk/api-client";
import {CardPackLibrary} from "./CardPackLibrary";
import {defaultPack} from "./packDesign";

vi.mock("../../useWindowStill",()=>({useWindowStill:()=>true}));
const originalPointer=window.PointerEvent;
const card={card_id:"synthetic-seal-card",name:"合成角色",revision:1,design:null,world_ids:[]} as unknown as LibraryCardItem;
beforeEach(()=>{
  vi.useFakeTimers();
  Object.defineProperty(window,"PointerEvent",{configurable:true,value:class extends MouseEvent{
    pointerId:number;isPrimary:boolean;
    constructor(type:string,init:PointerEventInit){super(type,init);this.pointerId=init.pointerId??1;this.isPrimary=init.isPrimary??true;}
  }});
  Object.defineProperty(window,"matchMedia",{configurable:true,value:vi.fn(()=>({matches:true,addEventListener(){},removeEventListener(){}}))});
  for(const name of ["setPointerCapture","releasePointerCapture","hasPointerCapture"])Object.defineProperty(HTMLElement.prototype,name,{configurable:true,value:vi.fn(()=>false)});
  Object.defineProperty(HTMLDialogElement.prototype,"showModal",{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=true;})});
  Object.defineProperty(HTMLDialogElement.prototype,"close",{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=false;})});
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();Object.defineProperty(window,"PointerEvent",{configurable:true,value:originalPointer});});
function setup(empty=false){
  const pack={...defaultPack("合成封口"),cardIds:empty?[]:[card.card_id]},save=vi.fn();
  render(<CardPackLibrary packs={[pack]} cards={[card]} images={{url:()=>"",upload:vi.fn(async()=>"synthetic-image"),crop:vi.fn(async()=>"synthetic-image")}} active embedded onSave={save} onEditingChange={vi.fn()}
    renderCards={scope=><div role="region" aria-label="包内角色">{scope?.cardIds.join(",")}</div>}/>);
  fireEvent.click(screen.getByRole("button",{name:"选择卡包：合成封口"}));
  act(()=>{vi.advanceTimersByTime(700);});
  const seal=screen.getByRole("slider");
  vi.spyOn(seal,"getBoundingClientRect").mockReturnValue(new DOMRect(40,400,200,44));
  return{pack,save,seal};
}
test("an empty pack states why it cannot open and keeps design available",()=>{
  const{seal}=setup(true);
  expect(seal.getAttribute("aria-disabled")).toBe("true");
  expect(screen.getByText("空卡包 · 先装卡")).toBeTruthy();
  const message=screen.getAllByText("卡包还没有角色卡，先点“设计与装卡”挑选角色。").find(node=>node.hasAttribute("data-pack-feedback"));
  expect(message).toBeTruthy();
  fireEvent.keyDown(seal,{key:"Enter"});
  expect(screen.queryByRole("region",{name:"包内角色"})).toBeNull();
  const design=screen.getByRole("button",{name:"设计与装卡"});
  expect(design.hasAttribute("disabled")).toBe(false);fireEvent.click(design);
  expect(screen.getByRole("textbox",{name:"卡包名称"})).toBeTruthy();
});
test.each([false,true])("loaded pack gives endpoint feedback, cancels safely, and opens from front/back=%s",back=>{
  const{seal,pack,save}=setup();
  if(back)fireEvent.click(screen.getByRole("button",{name:"背面"}));
  expect(seal.getAttribute("aria-disabled")).toBe("false");
  expect(screen.getByText("从封口一端 · 划到另一端")).toBeTruthy();
  fireEvent.pointerDown(seal,{pointerId:1,button:0,clientX:140,clientY:422});
  expect(screen.getAllByText("从封口任意一端按住，横向划到另一端。").some(node=>node.hasAttribute("data-pack-feedback"))).toBe(true);
  const start=back?232:48,end=back?42:238;
  fireEvent.pointerDown(seal,{pointerId:2,button:0,clientX:start,clientY:422});
  fireEvent.pointerMove(seal,{pointerId:2,clientX:(start+end)/2,clientY:422});
  expect(Number(seal.getAttribute("aria-valuenow"))).toBeGreaterThan(0);
  fireEvent.pointerCancel(seal,{pointerId:2});
  expect(seal.getAttribute("aria-valuenow")).toBe("0");
  fireEvent.pointerDown(seal,{pointerId:3,button:0,clientX:start,clientY:422});
  fireEvent.pointerMove(seal,{pointerId:3,clientX:end,clientY:422});
  act(()=>{vi.advanceTimersByTime(500);});
  expect(screen.getByRole("region",{name:"包内角色"}).textContent).toBe(card.card_id);
  expect(pack.cardIds).toEqual([card.card_id]);expect(save).not.toHaveBeenCalled();
});
