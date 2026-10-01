import L from 'leaflet';

// One camera owner per map, shared by plan replay and operational vehicles.
const followers = new WeakMap<L.Map, ReturnType<typeof createFollower>>();
function createFollower(map:L.Map) {
  let key='',following=false,close=false,position:L.LatLngExpression=[0,0];
  const control=new L.Control({position:'bottomright'});
  const button=document.createElement('button');button.type='button';button.textContent='Follow Vehicle';
  control.onAdd=()=>{const box=L.DomUtil.create('div','journey-controls');L.DomEvent.disableClickPropagation(box);box.append(button);return box;};
  control.addTo(map);
  const stop=(event?:Event)=>{if(event?.target instanceof Element&&event.target.closest('.journey-controls'))return;following=false;map.stop();button.setAttribute('aria-pressed','false');};
  map.getContainer().addEventListener('pointerdown',stop);
  map.getContainer().addEventListener('wheel',stop,{passive:true});
  map.getContainer().addEventListener('keydown',stop);
  map.on('dragstart',()=>stop());
  button.onclick=()=>{if(!key)return;following=true;close=true;map.setView(position,11,{animate:false});button.setAttribute('aria-pressed','true');};
  return {
    select(id:string,point:L.LatLngExpression){if(key!==id){following=false;close=false;button.setAttribute('aria-pressed','false');}key=id;position=point;},
    focus(id:string,route:L.LatLngExpression[],point:L.LatLngExpression){key=id;position=point;following=true;close=false;map.stop();map.fitBounds(L.latLngBounds(route),{padding:[45,45],maxZoom:10,animate:false});button.setAttribute('aria-pressed','true');},
    update(id:string,point:L.LatLngExpression,moving:boolean){if(id!==key)return;position=point;if(!following || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)return;if(moving&&!close){close=true;map.setView(point,11,{animate:false});}else if(close)map.panTo(point,{animate:false});},
    release(id:string){if(key===id){key='';following=false;}},
  };
}
export function vehicleFollower(map:L.Map){let follower=followers.get(map);if(!follower){follower=createFollower(map);followers.set(map,follower);}return follower;}
