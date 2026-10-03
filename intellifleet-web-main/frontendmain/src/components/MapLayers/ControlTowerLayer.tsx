import {useEffect,useRef} from 'react';
import {Marker,Tooltip,useMap} from 'react-leaflet';
import {useControlTowerStore} from '../../store/controlTowerStore';
import {movementIcon} from './movementIcon';
import {operationalTime} from '../../utils/operationalTime';

export function ControlTowerLayer(){
 const run=useControlTowerStore(s=>s.selected),map=useMap(),focused=useRef('');
 useEffect(()=>{
  if(!run?.latest_location || run.movement_id || focused.current===run.run_id)return;
  map.setView([run.latest_location.latitude,run.latest_location.longitude],9,{animate:false});focused.current=run.run_id;
 },[run,map]);
 if(!run?.latest_location || run.movement_id)return null;
 return <Marker position={[run.latest_location.latitude,run.latest_location.longitude]} icon={movementIcon(run.schedule.mode,0,true)}><Tooltip>
  {run.carrier||run.schedule.service} · {run.status}<br/>{run.schedule.lane} · {run.critical?'Critical lane':'Standard lane'}<br/>
  ETA {run.current_eta?operationalTime(run.current_eta):'Unavailable'}<br/>{run.location_source} · Updated {operationalTime(run.last_update_at)}
 </Tooltip></Marker>;
}
