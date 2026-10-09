import {useRef,useState,type ReactNode} from 'react';
export function WorkspaceSplitLayout({left,right,overlay,label="planning",storageKey="unifleet-planning-split"}:{left:ReactNode;right:ReactNode;overlay?:ReactNode;label?:string;storageKey?:string}){
 const container=useRef<HTMLDivElement>(null),drag=useRef(false);
 const clamp=(v:number)=>Math.min(65,Math.max(35,v));
 const [ratio,setRatio]=useState(()=>{try{return clamp(Number(localStorage.getItem(storageKey))||50);}catch{return 50;}});
 const save=(v:number)=>{const n=clamp(v);setRatio(n);try{localStorage.setItem(storageKey,String(n));}catch{/* optional */}};
 return <div ref={container} className="planning-split workspace-split" style={{gridTemplateColumns:`minmax(0,${ratio}fr) 8px minmax(0,${100-ratio}fr)`}}><div className="planning-left workspace-content">{left}{overlay}</div><div className="planning-divider" role="separator" aria-label={`Resize ${label} and map`} aria-orientation="vertical" aria-valuemin={35} aria-valuemax={65} aria-valuenow={ratio} tabIndex={0} onDoubleClick={()=>save(50)} onKeyDown={e=>{if(e.key==='Home')save(50);if(e.key==='ArrowLeft')save(ratio-2);if(e.key==='ArrowRight')save(ratio+2);if(['Home','ArrowLeft','ArrowRight'].includes(e.key))e.preventDefault();}} onPointerDown={e=>{drag.current=true;e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(drag.current&&container.current){const box=container.current.getBoundingClientRect();save((e.clientX-box.left)/box.width*100);}}} onPointerUp={e=>{drag.current=false;e.currentTarget.releasePointerCapture(e.pointerId);}} onPointerCancel={()=>{drag.current=false;}}/><div className="planning-map workspace-map">{right}</div></div>;
}

export const PlanningSplit=WorkspaceSplitLayout;
