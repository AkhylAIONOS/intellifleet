import {operationalTime} from '../../utils/operationalTime';
import {useEffect,useRef} from 'react';
import {Marker,Polyline,Tooltip,useMap} from 'react-leaflet';
import {useOperationsStore,movementMatches,movementIdentity,visibleAiMovement} from '../../store/operationsStore';
import {useFedexStore} from '../../store/fedexStore';
import {movementIcon} from './movementIcon';
import {vehicleFollower} from '../../utils/vehicleFollow';
export function NetworkMovementsLayer(){
 const state=useOperationsStore();const current=useFedexStore(s=>s.telemetry?.simulation_id);const map=useMap();const fitted=useRef(state.fit);const selected=useRef<string|null>(null);
 const entities=state.movements.filter(m=>{
  if(m.stopped || m.status==='SCHEDULE_TEMPLATE') return false;
  if(state.viewMode!=='AI' && m.simulation_id===current) return false;
  if(m.latitude==null || m.longitude==null) return false;
  if(!movementMatches(m,state.filter)) return false;

  // AI planning must NEVER expose the wider Live Operations fleet.
  if(state.viewMode==='AI'){
    return visibleAiMovement(m,state);
  }

  // Live Operations deliberately exposes the wider operational fleet.
  if(state.viewMode==='LIVE'){
    return true;
  }

  return false;
});
 useEffect(()=>{if(!state.enabled||!entities.length)return;
  if(fitted.current!==state.fit){map.fitBounds(entities.flatMap(m=>m.route.length?m.route:[[m.latitude!,m.longitude!] as [number,number]]),{padding:[40,40],maxZoom:8});fitted.current=state.fit;}
 },[state.enabled,state.fit,entities,map]);
 useEffect(()=>{const m=entities.find(m=>m.simulation_id===state.selected);if(!m?.route.length)return;if(selected.current!==state.selected){vehicleFollower(map).select(m.simulation_id,[m.latitude!,m.longitude!]);selected.current=state.selected;}vehicleFollower(map).update(m.simulation_id,[m.latitude!,m.longitude!],(m.progress||0)>0);},[state.selected,entities,map]);
 if(!state.enabled || state.viewMode==='OFF')return null;
 return <>{entities.map(m=><Marker key={movementIdentity(m)} position={[m.latitude!,m.longitude!]} icon={movementIcon(m.mode,m.heading,m.simulation_id===state.selected,m.status==='SCHEDULE_TEMPLATE')} eventHandlers={{click:()=>state.patch({selected:m.simulation_id})}}>
  <Tooltip><strong>{m.shipment_id} · {m.mode}</strong><br/>{m.origin_station} → {m.gateway}<br/>{m.status} {m.progress==null?'':`${(m.progress*100).toFixed(1)}%`}<br/>ETD {operationalTime(m.scheduled_etd)} · ETA {operationalTime(m.current_eta)}<br/>Delay {m.delay_minutes} min<br/>{m.data_source} / {m.location_source}<br/>{m.route_source || 'Approximate demo geometry'}</Tooltip>
 </Marker>)}{entities.filter(m=>m.route.length>1).flatMap(m=>(m.journey_segments?.length ? m.journey_segments : [{start_index:0,end_index:m.route.length-1,mode:m.mode}]).map((segment,index)=><Polyline
   key={`route-${movementIdentity(m)}-${index}`}
   positions={m.route.slice(segment.start_index,segment.end_index+1)}
   pathOptions={{
     color:m.simulation_id===state.selected?'#ff6600':segment.mode==='AIR'?'#7c3aed':segment.mode==='RAIL'?'#059669':'#3388ff',
     dashArray:segment.mode==='AIR'?'10 8':segment.mode==='RAIL'?'4 5':undefined,
     weight:m.simulation_id===state.selected?4:2,
     opacity:m.simulation_id===state.selected?1:0.45
   }}
  />))}</>;
}
