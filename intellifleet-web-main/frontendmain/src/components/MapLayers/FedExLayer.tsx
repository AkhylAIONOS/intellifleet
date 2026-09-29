import {operationalTime} from '../../utils/operationalTime';
import { useEffect, useRef } from 'react';
import { CircleMarker, Marker, Polyline, Tooltip, useMap } from 'react-leaflet';
import { movementIcon } from './movementIcon';
import { useFedexStore } from '../../store/fedexStore';

export function FedExLayer() {
  const state = useFedexStore(s=>s.telemetry);
  const map = useMap();
  const fitted = useRef<string | null>(null);
  useEffect(() => {
    if (!state) {fitted.current=null; return;}
    if (fitted.current === state.simulation_id) return;
    fitted.current = state.simulation_id;
    map.fitBounds(state.route, {padding:[50,50], maxZoom:8});
  }, [state, map]);
  if (!state) return null;
  return <>
    <Polyline positions={state.route} pathOptions={{color:'#4d148c',weight:4,dashArray:'8 8'}}>
      <Tooltip>SIMULATED TELEMETRY · Demo straight-line route</Tooltip>
    </Polyline>
    <CircleMarker center={state.route[0]} radius={8} pathOptions={{color:'#4d148c',fillOpacity:1}}>
      <Tooltip permanent direction="top">{state.origin_station} · DEMO origin</Tooltip>
    </CircleMarker>
    <CircleMarker center={state.route[state.route.length-1]} radius={8} pathOptions={{color:'#4d148c',fillOpacity:1}}>
      <Tooltip permanent direction="top">{state.gateway} · DEMO gateway</Tooltip>
    </CircleMarker>
    <Marker position={[state.latitude,state.longitude]} icon={movementIcon(state.mode,state.heading || 0,true)}>
      <Tooltip direction="right">{state.shipment_id} · {state.mode}<br/>{state.origin_station} → {state.gateway}<br/>{state.status} · {(state.progress*100).toFixed(1)}%<br/>ETD {operationalTime(state.scheduled_etd)}<br/>ETA {operationalTime(state.current_eta)}<br/>Delay {state.delay_minutes || 0} min<br/>{state.data_source || 'FEDEX_SOURCE'} / SIMULATED TELEMETRY</Tooltip>
    </Marker>
  </>;
}
