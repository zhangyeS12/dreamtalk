import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ArchiveOrigin } from "./ArchiveTurntable";
import { restPose as bookRest } from "../world/archive/ring";
import { restPose as cardRest, clamp } from "../world/cards/cardDesign";

export function ringIndex(value: number, count: number) { return count > 0 ? ((value % count) + count) % count : 0; }
export function ringSlots(position: number, count: number, radius = 2) {
  if (!count) return [];
  const centre = Math.round(position);
  return Array.from({ length: radius * 2 + 1 }, (_, index) => {
    const slot = centre + index - radius; return { slot, index: ringIndex(slot, count) };
  });
}
export function coastFrame(position: number, velocity: number, milliseconds: number) {
  const dt = Math.min(32, Math.max(0, milliseconds)), decay = Math.pow(.94, dt / (1000 / 60));
  return { position: position + velocity * dt, velocity: velocity * decay };
}
type Item = { id: string; name: string; thickness?: number };
type Geometry = { width: number; height: number; step: number; artWidth: number; artHeight: number; scale: number; radius: number };
export function ArchiveRing<T extends Item>({ label, items, renderItem, onOpen, onVisible, disabled = false, kind }: {
  label: string; items: T[]; kind: "books" | "cards" | "packs"; disabled?: boolean;
  renderItem: (item: T, focused: boolean) => ReactNode;
  onOpen: (item: T, origin?: ArchiveOrigin) => void; onVisible?: (ids: string[]) => void;
}) {
  const [anchor, setAnchor] = useState(0), [dragging, setDragging] = useState(false);
  const [geometry, setGeometry] = useState<Geometry>({ width:390,height:240,step:220,artWidth:200,artHeight:150,scale:.4,radius:2 });
  const [reduced, setReduced] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  const surface = useRef<HTMLDivElement>(null), nodes = useRef(new Map<number, HTMLButtonElement>());
  const motion = useRef({ position:0, velocity:0, target:0, mode:"idle" as "idle"|"drag"|"coast"|"snap", frame:0, last:0, elapsed:0 });
  const gesture = useRef<{ id:number; x:number; y:number; base:number; lastX:number; time:number; moved:boolean; slot:number|null } | null>(null);
  const suppress = useRef(false), suppressTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wheelTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const focusedId = useRef<string|null>(null), lastIds = useRef(""), anchorRef = useRef(0);
  const draw = useRef<() => void>(() => {});
  const latest = useRef({ items,geometry,disabled,kind,reduced,onOpen });
  latest.current = { items,geometry,disabled,kind,reduced,onOpen };
  const stop = useCallback(() => {
    const state=motion.current; cancelAnimationFrame(state.frame); state.frame=0; state.mode="idle"; state.velocity=0; state.last=0;
  }, []);
  draw.current = () => {
    const { items:list,geometry:g,kind:mode }=latest.current, state=motion.current;
    const centre=Math.round(state.position);
    if (centre!==anchorRef.current) { anchorRef.current=centre;setAnchor(centre); }
    const root=surface.current;
    if (root) { root.dataset.position=state.position.toFixed(5);root.dataset.motion=state.mode; }
    for (const [slot,node] of nodes.current) {
      const item=list[ringIndex(slot,list.length)]; if (!item) continue;
      const distance=slot-state.position, dx=distance*g.step;
      let y=0,pitch=0,roll=0;
      let z:number,yaw:number;
      if (mode==="books") {
        const pose=bookRest(dx/Math.max(.01,g.scale)); z=pose.pz*g.scale; yaw=pose.yaw;
      } else if(mode==="packs"){
        z=-dx*dx/3000;yaw=clamp(-dx*.018-12,-32,20);roll=[-7,5,-3,8,-5,4][ringIndex(slot,list.length)%6];
      } else {
        const rest=cardRest(item.id), scale=g.artWidth/410;
        y=rest.y*scale; z=-((dx/scale)**2)/3000*scale; yaw=clamp(-(dx/scale)*.018+rest.yaw,-45,45);
        pitch=rest.pitch; roll=rest.roll;
      }
      node.style.transform="translate(-50%,-50%) translate3d("+dx.toFixed(2)+"px,"+y.toFixed(2)+"px,"+z.toFixed(2)+"px) rotateZ("+roll+"deg) rotateX("+pitch+"deg) rotateY("+yaw+"deg)";
      node.style.opacity=String(mode==="books"?1:clamp(1-Math.abs(dx)/(Math.max(1,g.width)*1.3),.28,1));
      node.style.zIndex=String(30-Math.min(25,Math.round(Math.abs(distance))));
      node.dataset.distance=distance.toFixed(5);
      if(mode==="books"){node.style.setProperty("--shade",String(clamp(Math.abs(dx)/Math.max(1,g.width)*.5,0,.5)));node.style.setProperty("--yaw",String(yaw));}
    }
  };
  const animate=useCallback(function tick(now:number) {
    const state=motion.current, p=latest.current;
    state.frame=0;
    if (p.disabled || document.hidden) { stop();draw.current();return; }
    const dt=state.last ? Math.min(32,Math.max(1,now-state.last)) : 16.67;
    state.last=now;state.elapsed+=dt;
    if (state.mode==="coast") {
      const next=coastFrame(state.position,state.velocity,dt);state.position=next.position;state.velocity=next.velocity;
      if (Math.abs(state.velocity*p.geometry.step)<.025 || state.elapsed>1100) { state.mode="snap";state.target=Math.round(state.position); }
    }
    if (state.mode==="snap") {
      const gap=state.target-state.position;state.position+=gap*(1-Math.exp(-dt/55));
      if (Math.abs(gap)*p.geometry.step<.25 || p.reduced) { state.position=state.target;state.mode="idle"; }
    }
    draw.current();
    if (state.mode==="coast" || state.mode==="snap") state.frame=requestAnimationFrame(tick);
  }, [stop]);
  const settle=useCallback((target?:number) => {
    stop();const state=motion.current;state.target=Math.round(target??state.position);state.elapsed=0;
    if (latest.current.reduced) { state.position=state.target;draw.current(); }
    else { state.mode="snap";state.frame=requestAnimationFrame(animate);draw.current(); }
  },[stop,animate]);
  const ids=items.map(item=>item.id).join("|"), widths=items.map(item=>item.thickness??74).join("|");
  useEffect(() => {
    const media=matchMedia("(prefers-reduced-motion: reduce)"), change=()=>setReduced(media.matches);
    media.addEventListener("change",change);return()=>media.removeEventListener("change",change);
  }, []);
  useLayoutEffect(() => {
    if (ids!==lastIds.current) {
      stop();gesture.current=null;setDragging(false);
      const found=latest.current.items.findIndex(item=>item.id===focusedId.current);
      motion.current.position=found>=0 ? found : 0; lastIds.current=ids;draw.current();
    }
  },[ids,stop]);
  useLayoutEffect(() => {
    const node=surface.current;if (!node) return;
    const measure=()=>{
      const width=node.clientWidth||node.getBoundingClientRect().width||390, height=node.clientHeight||node.getBoundingClientRect().height||240;
      if (kind==="books") {
        const scale=Math.max(18,height-26)/540, thickness=Math.max(74,...latest.current.items.map(item=>item.thickness??70)), step=Math.max(56,(thickness+8)*scale);
        setGeometry({width,height,scale,step,artWidth:Math.max(52,thickness*scale),artHeight:540*scale,radius:Math.min(12,Math.max(2,Math.ceil(width/step/2)+2))});
      } else if(kind==="packs"){
        const artWidth=Math.min(210,width*.52,Math.max(45,(height-24)*.7));
        setGeometry({width,height,scale:artWidth/240,step:artWidth*1.3,artWidth,artHeight:artWidth/.7,radius:2});
      } else {
        const artWidth=Math.min(320,width*.7,Math.max(50,(height-26)/1.3));
        setGeometry({width,height,scale:artWidth/410,step:artWidth*(450/410),artWidth,artHeight:artWidth/1.5858,radius:2});
      }
    };
    measure();const observer=new ResizeObserver(measure);observer.observe(node);return()=>observer.disconnect();
  },[kind,widths]);
  useLayoutEffect(() => { draw.current(); },[anchor,geometry,items]);
  useEffect(() => { if (!disabled) focusedId.current=items[ringIndex(anchor,items.length)]?.id??null; },[anchor,disabled,items]);
  useEffect(() => { if (disabled) { stop();gesture.current=null;setDragging(false);draw.current(); } },[disabled,stop]);
  useEffect(() => {
    const hide=()=>{if(document.hidden){stop();gesture.current=null;setDragging(false);draw.current();}};
    document.addEventListener("visibilitychange",hide);
    return()=>{document.removeEventListener("visibilitychange",hide);stop();clearTimeout(suppressTimer.current);clearTimeout(wheelTimer.current);};
  },[stop]);
  useEffect(() => {
    const node=surface.current;if(!node)return;
    const wheel=(event:WheelEvent)=>{
      if(latest.current.disabled||gesture.current||event.ctrlKey)return;
      event.preventDefault();stop();motion.current.position+=(event.deltaX||event.deltaY)*.8/latest.current.geometry.step;draw.current();
      clearTimeout(wheelTimer.current);wheelTimer.current=setTimeout(()=>settle(),140);
    };
    node.addEventListener("wheel",wheel,{passive:false});return()=>node.removeEventListener("wheel",wheel);
  },[stop,settle]);
  const slots=ringSlots(anchor,items.length,geometry.radius);
  const visibleKey=[...new Set(slots.map(({index})=>items[index].id))].sort().join("|");
  const visible=useMemo(()=>visibleKey?visibleKey.split("|"):[],[visibleKey]);
  useEffect(()=>{onVisible?.(visible);},[visible,onVisible]);
  const choose=(slot:number)=>{
    const item=latest.current.items[ringIndex(slot,latest.current.items.length)];if(!item||latest.current.disabled)return;
    const rect=nodes.current.get(slot)?.getBoundingClientRect();
    const origin=rect?{x:rect.x,y:rect.y,width:rect.width,height:rect.height}:undefined;
    stop();motion.current.position=slot;focusedId.current=item.id;draw.current();latest.current.onOpen(item,origin);
  };
  const finish=(cancelled:boolean)=>{
    const current=gesture.current;if(!current)return;
    gesture.current=null;setDragging(false);
    suppress.current=true;clearTimeout(suppressTimer.current);suppressTimer.current=setTimeout(()=>{suppress.current=false;},400);
    if(cancelled){stop();motion.current.position=current.base;draw.current();}
    else if(!current.moved){stop();if(current.slot!==null)choose(current.slot);else settle();}
    else if(latest.current.reduced||performance.now()-current.time>90||Math.abs(motion.current.velocity*latest.current.geometry.step)<.04){settle();}
    else {motion.current.mode="coast";motion.current.last=0;motion.current.elapsed=0;motion.current.frame=requestAnimationFrame(animate);draw.current();}
    if(surface.current?.hasPointerCapture?.(current.id))surface.current.releasePointerCapture(current.id);
  };
  const move=(delta:number)=>{if(!disabled&&items.length)settle(Math.round(motion.current.position)+delta);};
  const centre=ringIndex(anchor,items.length);
  return <div className={"mobile-archive-ring-shell mobile-archive-"+kind}>
    <div ref={surface} className="mobile-archive-ring" role="group" aria-roledescription="循环轮播" aria-label={label} data-items={items.length}
      data-dragging={dragging||undefined} tabIndex={disabled?-1:0}
      style={{"--archive-step":geometry.step+"px","--archive-art-width":geometry.artWidth+"px","--archive-item-height":geometry.artHeight+"px","--book-scale":geometry.scale} as CSSProperties}
      onKeyDown={event=>{
        if(event.key==="ArrowLeft"||event.key==="ArrowRight"){event.preventDefault();event.stopPropagation();move(event.key==="ArrowLeft"?-1:1);}
        else if((event.key==="Enter"||event.key===" ")&&!disabled){
          const slot=(event.target as Element).closest<HTMLElement>("[data-archive-slot]")?.dataset.archiveSlot;
          if(slot!==undefined){event.preventDefault();choose(Number(slot));}
        }
      }}
      onDragStart={event=>event.preventDefault()} onContextMenu={event=>event.preventDefault()}
      onPointerDown={event=>{
        if(disabled||!items.length||!event.isPrimary||event.button!==0||gesture.current)return;
        stop();clearTimeout(wheelTimer.current);clearTimeout(suppressTimer.current);suppress.current=false;
        const slot=(event.target as Element).closest<HTMLElement>("[data-archive-slot]")?.dataset.archiveSlot;
        gesture.current={id:event.pointerId,x:event.clientX,y:event.clientY,lastX:event.clientX,time:performance.now(),base:motion.current.position,moved:false,slot:slot===undefined?null:Number(slot)};
        // Capture immediately, as Windows does. Taps are resolved from the original item.
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={event=>{
        const current=gesture.current;if(!current||current.id!==event.pointerId)return;
        const dx=event.clientX-current.x,dy=event.clientY-current.y;
        if(!current.moved&&Math.hypot(dx,dy)>6){current.moved=true;setDragging(true);suppress.current=true;}
        if(current.moved){
          event.preventDefault();const now=performance.now(),dt=Math.max(8,now-current.time),step=latest.current.geometry.step;
          const velocity=clamp(-(event.clientX-current.lastX)/dt,-3.5,3.5)/step;
          motion.current.velocity=motion.current.velocity*.35+velocity*.65;motion.current.position=current.base-dx/step;motion.current.mode="drag";
          draw.current();current.lastX=event.clientX;current.time=now;
        }
      }}
      onPointerUp={event=>{if(gesture.current?.id===event.pointerId)finish(false);}}
      onPointerCancel={event=>{if(gesture.current?.id===event.pointerId)finish(true);}}
      onLostPointerCapture={event=>{if(event.target===event.currentTarget&&gesture.current?.id===event.pointerId)finish(true);}}
      onClickCapture={event=>{if(disabled||suppress.current){event.preventDefault();event.stopPropagation();}}}>
      {slots.map(({slot,index})=>{
        const item=items[index],focused=slot===anchor;
        return <button key={slot} ref={node=>{if(node)nodes.current.set(slot,node);else nodes.current.delete(slot);}}
          type="button" className="mobile-archive-item" data-archive-slot={slot} data-card-id={kind==="cards"?item.id:undefined} data-focused={focused||undefined}
          tabIndex={focused&&!disabled?0:-1} disabled={disabled} aria-hidden={!focused||undefined} aria-label={item.name}
          onClick={()=>choose(slot)}>{renderItem(item,focused)}</button>;
      })}
    </div>
    <div className="mobile-archive-controls">
      <button type="button" className="mobile-icon-action" aria-label={label+"上一项"} disabled={disabled||!items.length} onClick={()=>move(-1)}><ChevronLeft size={20}/></button>
      <span aria-live="polite" aria-atomic="true">{items[centre]?.name??"尚无收藏"}</span>
      <button type="button" className="mobile-icon-action" aria-label={label+"下一项"} disabled={disabled||!items.length} onClick={()=>move(1)}><ChevronRight size={20}/></button>
    </div>
  </div>;
}
