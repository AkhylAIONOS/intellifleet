import { useEffect, useRef } from 'react';
import { CircleMarker, Polyline, Tooltip, useMap } from 'react-leaflet';
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
    <CircleMarker center={[state.latitude,state.longitude]} radius={11} pathOptions={{color:'#fff',weight:3,fillColor:'#ff6600',fillOpacity:1}}>
      <Tooltip permanent direction="right">{state.mode === 'AIR' ? '✈' : state.mode === 'RAIL' ? 'Rail' : 'Vehicle'} · {state.shipment_id}<br/>{(state.progress*100).toFixed(1)}% · {state.status}<br/>SIMULATED TELEMETRY</Tooltip>
    </CircleMarker>
  </>;
}
