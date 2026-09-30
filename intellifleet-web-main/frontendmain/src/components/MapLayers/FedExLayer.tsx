import {operationalTime} from '../../utils/operationalTime';
import { useEffect, useRef, useMemo } from 'react';
import { CircleMarker, Marker, Polyline, Tooltip, useMap } from 'react-leaflet';
import { movementIcon } from './movementIcon';
import { useFedexStore } from '../../store/fedexStore';
import {useOperationsStore} from '../../store/operationsStore';
import {vehicleFollower} from '../../utils/vehicleFollow';

export function FedExLayer() {
  const state = useFedexStore(s=>s.telemetry);
  const map = useMap();
  const route = useMemo(()=>state?.route,[state?.simulation_id,state?.route_id]);
  const fitted = useRef<string | null>(null);
  useEffect(() => {
    if (!state) {fitted.current=null; return;}
    const key = `${state.simulation_id}:${state.route_id || ''}`;
    if (fitted.current === key) return;
    fitted.current = key;
    if(useOperationsStore.getState().viewMode!=='LIVE')vehicleFollower(map).focus(state.simulation_id,state.route,[state.latitude,state.longitude]);
  }, [state, map]);
  useEffect(()=>{if(state)vehicleFollower(map).update(state.simulation_id,[state.latitude,state.longitude],state.progress>0);},[state,map]);
  if (!state) return null;
  return <>
    <Polyline positions={route!} pathOptions={{color:'#4d148c',weight:4,dashArray:'8 8'}}>
      <Tooltip>SIMULATED TELEMETRY · {state.road_routing_status==='READY'?'Road-network route · OpenStreetMap / OSRM':'Approximate Air/Rail demo geometry'}</Tooltip>
    </Polyline>
    <CircleMarker center={state.route[0]} radius={8} pathOptions={{color:'#4d148c',fillOpacity:1}}>
      <Tooltip permanent direction="top">{state.origin_station} · Origin</Tooltip>
    </CircleMarker>
    <CircleMarker center={state.route[state.route.length-1]} radius={8} pathOptions={{color:'#4d148c',fillOpacity:1}}>
      <Tooltip permanent direction="top">{state.gateway} · Gateway</Tooltip>
    </CircleMarker>
    <Marker position={[state.latitude,state.longitude]} icon={movementIcon(state.mode,state.heading || 0,true)}>
      <Tooltip direction="right">{state.shipment_id} · {state.mode}<br/>{state.origin_station} → {state.gateway}<br/>{state.status} · {(state.progress*100).toFixed(1)}%<br/>ETD {operationalTime(state.scheduled_etd)}<br/>ETA {operationalTime(state.current_eta)}<br/>Delay {state.delay_minutes || 0} min<br/>{state.data_source || 'FEDEX_SOURCE'} / SIMULATED TELEMETRY<br/>{state.route_source || 'Approximate demo geometry'}</Tooltip>
    </Marker>
  </>;
}
