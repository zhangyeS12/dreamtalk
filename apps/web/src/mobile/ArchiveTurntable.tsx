import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { faceFromYaw, yawToward } from "../world/archive/ring";
import type { ShelfFace } from "../world/archive/bookDesign";
export type ArchiveOrigin = { x:number; y:number; width:number; height:number };
export function ArchiveTurntable({ id, kind, label, thickness=74, origin, faceRequest, onFace, onDismiss, children }: {
  id:string;kind:"book"|"card";label:string;thickness?:number;origin?:ArchiveOrigin;
  faceRequest?:{face:ShelfFace;nonce:number};onFace?:(face:ShelfFace)=>void;onDismiss?:()=>void;children:ReactNode;
}) {
  const root=useRef<HTMLDivElement>(null), mesh=useRef<HTMLDivElement>(null);
  const pose=useRef({yaw:kind==="book"?-74:0,pitch:0}), scale=useRef(.5);
  const drag=useRef<{id:number;x:number;y:number;yaw:number;pitch:number;onObject:boolean;moved:boolean}|null>(null);
  const current=useRef({kind,onFace});current.current={kind,onFace};
  const animation=useRef<Animation|null>(null), lastFace=useRef<ShelfFace|null>(null);
  const [ready,setReady]=useState(false);
  const transform=useCallback((yaw:number,pitch:number,s=scale.current)=>
    "translate(-50%,-50%) scale("+s+") rotateZ("+(current.current.kind==="book"?-3:0)+"deg) rotateX("+pitch+"deg) rotateY("+yaw+"deg)",[]);
  const draw=useCallback(()=>{
    if(!mesh.current)return;
    mesh.current.style.transform=transform(pose.current.yaw,pose.current.pitch);
    mesh.current.dataset.yaw=pose.current.yaw.toFixed(2);mesh.current.dataset.pitch=pose.current.pitch.toFixed(2);
    const face=current.current.kind==="book"?faceFromYaw(pose.current.yaw):Math.cos(pose.current.yaw*Math.PI/180)>=0?"front":"back";
    mesh.current.dataset.face=face;
    if(current.current.kind==="card")for(const node of mesh.current.querySelectorAll<HTMLElement>("[data-face]"))node.hidden=node.dataset.face!==face;
    if(face!==lastFace.current){lastFace.current=face;current.current.onFace?.(face);}
  },[transform]);
  useLayoutEffect(()=>{
    const node=root.current;if(!node)return;
    const resize=()=>{
      const width=node.clientWidth||320,height=node.clientHeight||250;
      scale.current=Math.max(.1,Math.min((width-(kind==="book"?68:28))/(kind==="book"?372:410),(height-20)/(kind==="book"?540:410/1.5858)));
      draw();
    };
    resize();const observer=new ResizeObserver(resize);observer.observe(node);
    return()=>observer.disconnect();
  },[draw,kind,thickness]);
  useLayoutEffect(()=>{
    const node=mesh.current,stage=root.current;if(!node||!stage)return;
    let alive=true;setReady(false);
    const rect=stage.getBoundingClientRect(),target=transform(pose.current.yaw,pose.current.pitch);
    if(!node.animate||matchMedia("(prefers-reduced-motion: reduce)").matches){setReady(true);return;}
    const dx=origin?origin.x+origin.width/2-(rect.x+rect.width/2):0;
    const dy=origin?origin.y+origin.height/2-(rect.y+rect.height/2):24;
    const fromScale=origin?Math.min(scale.current,origin.height/(kind==="book"?540:410/1.5858)):scale.current*.82;
    const from="translate(-50%,-50%) translate("+dx+"px,"+dy+"px) scale("+fromScale+") rotateY("+(kind==="book"?0:-15)+"deg)";
    const anim=node.animate([{transform:from},{transform:target}],{duration:360,easing:"cubic-bezier(.22,1,.36,1)"});
    animation.current=anim;
    void anim.finished.then(()=>{if(alive){animation.current=null;setReady(true);draw();}}).catch(()=>undefined);
    return()=>{alive=false;anim.cancel();animation.current=null;};
    // A selection animates once; resize and face buttons keep the same object.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[id]);
  useEffect(()=>{
    if(!faceRequest)return;
    const base={front:kind==="book"?-90:0,spine:0,back:kind==="book"?90:180,edge:180}[faceRequest.face];
    animation.current?.cancel();animation.current=null;setReady(true);
    pose.current={yaw:yawToward(pose.current.yaw,base),pitch:0};draw();
  },[faceRequest,kind,draw]);
  useEffect(()=>{
    const cancel=()=>{drag.current=null;root.current?.removeAttribute("data-spinning");};
    window.addEventListener("blur",cancel);document.addEventListener("visibilitychange",cancel);
    return()=>{window.removeEventListener("blur",cancel);document.removeEventListener("visibilitychange",cancel);};
  },[]);
  const finish=(pointer:number,cancelled=false)=>{if(drag.current?.id!==pointer)return;const dismiss=!cancelled&&!drag.current.moved&&!drag.current.onObject;drag.current=null;root.current?.removeAttribute("data-spinning");if(root.current?.hasPointerCapture?.(pointer))root.current.releasePointerCapture(pointer);if(dismiss)onDismiss?.();};
  return <div ref={root} className={"mobile-archive-turntable mobile-turntable-"+kind} role="group" aria-label={label} tabIndex={0} data-ready={ready}
    aria-busy={!ready} onContextMenu={event=>event.preventDefault()} onDragStart={event=>event.preventDefault()}
    onPointerDown={event=>{if(!ready||!event.isPrimary||event.button!==0||drag.current)return;event.preventDefault();drag.current={id:event.pointerId,x:event.clientX,y:event.clientY,...pose.current,onObject:Boolean((event.target as Element).closest(".mobile-archive-inspected-object")),moved:false};event.currentTarget.setPointerCapture?.(event.pointerId);event.currentTarget.dataset.spinning="true";}}
    onPointerMove={event=>{const start=drag.current;if(!start||start.id!==event.pointerId)return;event.preventDefault();if(Math.hypot(event.clientX-start.x,event.clientY-start.y)>6)start.moved=true;pose.current={yaw:start.yaw+(event.clientX-start.x)*.65,pitch:Math.max(-25,Math.min(25,start.pitch-(event.clientY-start.y)*.3))};draw();}}
    onPointerUp={event=>finish(event.pointerId)} onPointerCancel={event=>finish(event.pointerId,true)}
    onLostPointerCapture={event=>{if(event.target===event.currentTarget)finish(event.pointerId,true);}}
    onDoubleClick={()=>{pose.current={yaw:kind==="book"?-90:0,pitch:0};draw();}}
    onKeyDown={event=>{const key=event.key;if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home"].includes(key))return;event.preventDefault();event.stopPropagation();if(key==="Home")pose.current={yaw:kind==="book"?-90:0,pitch:0};else if(key==="ArrowLeft"||key==="ArrowRight")pose.current.yaw+=key==="ArrowLeft"?-90:90;else pose.current.pitch=Math.max(-25,Math.min(25,pose.current.pitch+(key==="ArrowUp"?-10:10)));draw();}}>
    <div ref={mesh} className="mobile-archive-inspected-object" style={{width:kind==="book"?thickness:410,height:kind==="book"?540:410/1.5858,"--T":thickness+"px","--C":"372px","--H":"540px","--card-w":"410px"} as CSSProperties}>{children}</div>
    <span className="mobile-archive-spin-hint">{ready?"拖动旋转 · 双击回到正面":"正在展开…"}</span>
  </div>;
}
