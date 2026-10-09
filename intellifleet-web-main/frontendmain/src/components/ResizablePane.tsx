import {useRef,useState,type ReactNode} from 'react';
export function ResizablePane({children,label,storageKey,initial=360,min=300,max=560,side='right',vertical=false}:{children:ReactNode;label:string;storageKey:string;initial?:number;min?:number;max?:number;side?:'left'|'right';vertical?:boolean}){
 const clamp=(n:number)=>Math.min(max,Math.max(min,n));
 const [size,setSize]=useState(()=>{try{const n=Number(localStorage.getItem(storageKey));return n?clamp(n):initial;}catch{return initial;}});
 const drag=useRef<{start:number;size:number}|null>(null);
 const save=(n:number)=>{const value=clamp(n);setSize(value);try{localStorage.setItem(storageKey,String(value));}catch{/* Layout remains usable without storage. */}};
 return <div className={`resizable-pane ${vertical?'vertical':''} ${side}`} style={vertical?{height:size}:{width:size}}>
  <div className="resize-handle" role="separator" aria-label={`Resize ${label}`} aria-orientation={vertical?'horizontal':'vertical'} aria-valuemin={min} aria-valuemax={max} aria-valuenow={size} tabIndex={0}
   onDoubleClick={()=>save(initial)} onKeyDown={e=>{if(e.key==='Home'){save(initial);e.preventDefault();}if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){save(size+(['ArrowRight','ArrowDown'].includes(e.key)?20:-20));e.preventDefault();}}}
   onPointerDown={e=>{drag.current={start:vertical?e.clientY:e.clientX,size};e.currentTarget.setPointerCapture(e.pointerId);}}
   onPointerMove={e=>{if(drag.current)save(drag.current.size+((vertical?e.clientY:e.clientX)-drag.current.start)*(vertical||side==='left'?1:-1));}}
   onPointerUp={e=>{drag.current=null;e.currentTarget.releasePointerCapture(e.pointerId);}} onPointerCancel={()=>{drag.current=null;}}/>
  {children}
 </div>;
}
