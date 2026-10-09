import {Fragment,useEffect,useMemo} from 'react';
import {MapContainer,TileLayer,Polyline,Marker,Tooltip,useMap} from 'react-leaflet';
import L from 'leaflet';
import type {TowerRun} from '../api/controlTower';
import {useControlTowerStore} from '../store/controlTowerStore';
import {MapFitController} from './MapFitController';
import {selectedRouteColor} from '../utils/routePalette';
import {MapResizeController} from './MapResizeController';
import {movementIcon} from './MapLayers/movementIcon';
import 'leaflet/dist/leaflet.css';
import {operationalTime} from '../utils/operationalTime';
function Fit({runs}:{runs:TowerRun[]}){
 const map=useMap();
 // Refreshes can update estimated positions without resetting the operator camera.
 const signature=JSON.stringify(runs.map(r=>[r.run_id,r.visualization?.origin,r.visualization?.destination]));
 const points=useMemo(()=>runs.flatMap(r=>{const g=r.visualization;return g?.origin&&g.destination?[g.origin,g.destination]:r.location_source==='FEDEX_SCAN'&&r.latest_location?[[r.latest_location.latitude,r.latest_location.longitude] as [number,number]]:[];}),[signature]);
 useEffect(()=>{if(points.length)map.fitBounds(L.latLngBounds(points),{padding:[30,30],maxZoom:9,animate:false});},[points,map]);
 return <MapFitController points={points}/>;
}
export function OperationalMap({runs}:{runs:TowerRun[]}){
 const select=useControlTowerStore(s=>s.select),selected=useControlTowerStore(s=>s.selected),selectedRuns=useControlTowerStore(s=>s.selectedRuns);
 const isSelected=(run:TowerRun)=>selectedRuns.some(r=>r.run_id===run.run_id)||selected?.run_id===run.run_id;
 const comparison=selectedRuns.length>1&&runs.every(r=>selectedRuns.some(s=>s.run_id===r.run_id));
 const color=(run:TowerRun)=>comparison?selectedRouteColor(selectedRuns.findIndex(s=>s.run_id===run.run_id)):run.schedule.mode==='AIR'?'#7050d5':'#53667e';
 const mapped=runs.filter(r=>r.visualization?.origin&&r.visualization?.destination||r.location_source==='FEDEX_SCAN'&&r.latest_location);
 return <div className="operational-map"><div className="map-caption">Operational lanes · {mapped.length} of {runs.length} mapped · {comparison?'Selected route colors in legend':'purple Air / slate Surface & Train'}<br/>City-centre lane geometry · schedule estimates are not GPS</div>
 {comparison&&<div className="selected-route-legend" aria-label="Selected route colors">{selectedRuns.map((run,i)=><span key={run.run_id}><i style={{background:selectedRouteColor(i)}}/>{run.schedule.lane} · {run.schedule.service}</span>)}<small>Colors identify routes, not status.</small></div>}
 <MapContainer center={[20.5937,78.9629]} zoom={5} zoomAnimation={false} fadeAnimation={false} markerZoomAnimation={false} style={{height:'100%',width:'100%'}}><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap contributors'/><MapResizeController/><Fit runs={runs}/>
 {mapped.map(run=>{const g=run.visualization;const actual=run.latest_location;const point=actual?[actual.latitude,actual.longitude] as [number,number]:g?.position;return <Fragment key={run.run_id}>{g?.origin&&g.destination&&<Polyline positions={[g.origin,g.destination]} pathOptions={{color:color(run),weight:isSelected(run)?5:2,opacity:.65,dashArray:run.schedule.mode==='AIR'?'7 7':undefined}} eventHandlers={{click:()=>select(run)}}/>}{point&&<Marker position={point} icon={movementIcon(run.schedule.mode,0,isSelected(run))} eventHandlers={{click:()=>select(run)}}><Tooltip>{run.schedule.lane} · {run.schedule.run}<br/>{run.location_source==='FEDEX_SCAN'?'Reported scan location':run.movement?'Simulated movement':'Schedule-derived position'}<br/>ETA {operationalTime(run.current_eta)}</Tooltip></Marker>}</Fragment>;})}
 </MapContainer></div>;
}
