import {operationalTime} from '../../utils/operationalTime';
import {useEffect,useRef} from 'react';
import {Marker,Polyline,Tooltip,useMap} from 'react-leaflet';
import {useOperationsStore,movementMatches} from '../../store/operationsStore';
import {useFedexStore} from '../../store/fedexStore';
import {movementIcon} from './movementIcon';
export function NetworkMovementsLayer(){
 const state=useOperationsStore();const current=useFedexStore(s=>s.telemetry?.simulation_id);const map=useMap();const fitted=useRef(-1);const selected=useRef<string|null>(null);
 const entities=state.movements.filter(m=>!m.stopped&&m.status!=='SCHEDULE_TEMPLATE'&&m.simulation_id!==current&&movementMatches(m,state.filter)&&m.latitude!=null&&m.longitude!=null);
 useEffect(()=>{if(!state.enabled||!entities.length)return;
  if(fitted.current!==state.fit){map.fitBounds(entities.map(m=>[m.latitude!,m.longitude!] as [number,number]),{padding:[40,40],maxZoom:8});fitted.current=state.fit;}
 },[state.enabled,state.fit,entities,map]);
 useEffect(()=>{if(selected.current===state.selected)return;const m=entities.find(m=>m.simulation_id===state.selected);if(m?.route.length){map.fitBounds(m.route,{padding:[40,40],maxZoom:8});selected.current=state.selected;}},[state.selected,entities,map]);
 if(!state.enabled)return null;
 return <>{entities.map(m=><Marker key={m.simulation_id} position={[m.latitude!,m.longitude!]} icon={movementIcon(m.mode,m.heading,m.simulation_id===state.selected,m.status==='SCHEDULE_TEMPLATE')} eventHandlers={{click:()=>state.patch({selected:m.simulation_id})}}>
  <Tooltip><strong>{m.shipment_id} · {m.mode}</strong><br/>{m.origin_station} → {m.gateway}<br/>{m.status} {m.progress==null?'':`${(m.progress*100).toFixed(1)}%`}<br/>ETD {operationalTime(m.scheduled_etd)} · ETA {operationalTime(m.current_eta)}<br/>Delay {m.delay_minutes} min<br/>{m.data_source} / {m.location_source}</Tooltip>
 </Marker>)}{entities.filter(m=>m.simulation_id===state.selected&&m.route.length>1).map(m=><Polyline key={`route-${m.simulation_id}`} positions={m.route} pathOptions={{color:'#ff6600',dashArray:'6 6'}}/>)}</>;
}
