import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { ComponentProps } from "react";
import { WorldShelf } from "../WorldShelf";

/** Only the object stage changes scale; Windows keeps ownership of its actors and motion. */
export function NativeBookShelf(props: ComponentProps<typeof WorldShelf>) {
  const root=useRef<HTMLDivElement>(null);
  const [frame,setFrame]=useState({width:390,height:300,scale:.5});
  useLayoutEffect(()=>{
    const node=root.current;if(!node)return;
    const measure=()=>{const width=node.clientWidth||390,height=node.clientHeight||300;
      setFrame({width,height,scale:Math.max(.12,Math.min((height-40)/540,(width-60)/372))});};
    measure();const observer=new ResizeObserver(measure);observer.observe(node);return()=>observer.disconnect();
  },[]);
  return <div ref={root} className="mobile-native-books" role="group" aria-label={props.selectedKey?"旋转世界书":"世界书架"}>
    <div className="mobile-native-books-frame" style={{zoom:frame.scale,width:frame.width/frame.scale,height:frame.height/frame.scale,"--scene-scale":frame.scale} as CSSProperties}>
      <WorldShelf {...props} embedded frameScale={frame.scale}/>
    </div>
  </div>;
}
