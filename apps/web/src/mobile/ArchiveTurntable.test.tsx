import {afterAll,afterEach,beforeAll,expect,test,vi} from "vitest";
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {ArchiveTurntable} from "./ArchiveTurntable";
const original=window.PointerEvent;
beforeAll(()=>Object.defineProperty(window,"PointerEvent",{configurable:true,value:class extends MouseEvent{
  pointerId:number;isPrimary:boolean;
  constructor(type:string,init:PointerEventInit){super(type,init);this.pointerId=init.pointerId??1;this.isPrimary=init.isPrimary??true;}
}}));
afterAll(()=>Object.defineProperty(window,"PointerEvent",{configurable:true,value:original}));
afterEach(()=>{cleanup();vi.restoreAllMocks();});
function scene(kind:"book"|"card",onDismiss=vi.fn()){
  render(<ArchiveTurntable id="synthetic-object" kind={kind} label="旋转检查" onDismiss={onDismiss}><span data-face="front">正面</span><span data-face="back">背面</span></ArchiveTurntable>);
  const group=screen.getByRole("group");group.setPointerCapture=vi.fn();
  return{group,mesh:group.querySelector<HTMLElement>(".mobile-archive-inspected-object")!,onDismiss};
}
test("the same card stays present through continuous turns beyond 360 degrees",()=>{
  const{group,mesh}=scene("card");
  for(let i=0;i<4;i++){fireEvent.pointerDown(mesh,{pointerId:i+1,clientX:20,clientY:50,isPrimary:true});fireEvent.pointerMove(group,{pointerId:i+1,clientX:220,clientY:50});fireEvent.pointerUp(group,{pointerId:i+1});}
  expect(Number(mesh.dataset.yaw)).toBeGreaterThan(360);
  expect(group.querySelector(".mobile-archive-inspected-object")).toBe(mesh);
});
test("front and back visibility follows rotation and Home returns the card to the front",()=>{
  const{group,mesh}=scene("card");
  fireEvent.keyDown(group,{key:"ArrowRight"});fireEvent.keyDown(group,{key:"ArrowRight"});
  expect(mesh.dataset.face).toBe("back");
  expect(mesh.querySelector<HTMLElement>("[data-face='front']")!.hidden).toBe(true);
  expect(mesh.querySelector<HTMLElement>("[data-face='back']")!.hidden).toBe(false);
  fireEvent.keyDown(group,{key:"Home"});expect(mesh.dataset.face).toBe("front");
});
test("pitch is constrained and child capture loss cannot terminate object rotation",()=>{
  const{group,mesh}=scene("book");
  fireEvent.pointerDown(mesh,{pointerId:8,clientX:80,clientY:80,isPrimary:true});
  fireEvent(mesh,new PointerEvent("lostpointercapture",{bubbles:true,pointerId:8}));
  fireEvent.pointerMove(group,{pointerId:8,clientX:200,clientY:600});
  expect(Number(mesh.dataset.yaw)).not.toBe(-74);expect(Number(mesh.dataset.pitch)).toBe(-25);
  fireEvent.pointerCancel(group,{pointerId:8});
  const before=mesh.dataset.yaw;fireEvent.pointerMove(group,{pointerId:8,clientX:350,clientY:50});
  expect(mesh.dataset.yaw).toBe(before);
});
test("only a background tap dismisses the inspected object",()=>{
  const{group,mesh,onDismiss}=scene("card");
  fireEvent.pointerDown(mesh,{pointerId:1,clientX:100,clientY:100,isPrimary:true});fireEvent.pointerUp(group,{pointerId:1});
  expect(onDismiss).not.toHaveBeenCalled();
  fireEvent.pointerDown(group,{pointerId:2,clientX:10,clientY:10,isPrimary:true});fireEvent.pointerUp(group,{pointerId:2});
  expect(onDismiss).toHaveBeenCalledTimes(1);
});
