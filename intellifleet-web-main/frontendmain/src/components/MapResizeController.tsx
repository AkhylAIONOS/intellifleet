import {useEffect} from 'react';
import {useMap} from 'react-leaflet';

export function MapResizeController(){
  const map=useMap();
  useEffect(()=>{
    const container=map.getContainer();
    let frame:number|null=null;
    const refresh=()=>{
      frame=null;
      if(!container.clientWidth || !container.clientHeight)return;
      const size=map.getSize();
      if(size.x!==container.clientWidth || size.y!==container.clientHeight){
        // Repaint flex-layout changes without fitting a route or changing zoom.
        map.invalidateSize({pan:true,animate:false,debounceMoveend:true});
      }
    };
    const schedule=()=>{
      if(frame===null)frame=window.requestAnimationFrame(refresh);
    };
    const observer=typeof ResizeObserver==='undefined'?null:new ResizeObserver(schedule);
    observer?.observe(container);
    window.addEventListener('resize',schedule);
    refresh();
    return()=>{
      observer?.disconnect();
      window.removeEventListener('resize',schedule);
      if(frame!==null)window.cancelAnimationFrame(frame);
    };
  },[map]);
  return null;
}
