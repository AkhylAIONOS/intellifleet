import { useMemo, useState } from 'react';
import { useAppStore } from '../store/appStore';
import { routesApi } from '../api/routes';
import { formatDuration } from '../utils/formatDuration';
import { RouteUploadTable } from './RouteUploadTable';
import './RouteDashboard.css';

const ROAD_MODES=new Set(['road','ground','truck']);
const AIR_MODES=new Set(['air','express','flight','plane','aviation']);
export const routeMode=(route:any)=>{
  if(route?.routeData?.multimodal)return 'multimodal';
  const raw=String(route?.routeData?.route_type??route?.routeData?.mode??route?.routeData?.legs?.[0]?.route_type??route?.route_type??route?.mode??'road').trim().toLowerCase();
  if(ROAD_MODES.has(raw))return 'road';
  if(AIR_MODES.has(raw))return 'air';
  return raw;
};
export const isPersistedRoute=(route:any)=>route?.routeData?.planning!==true;
export const filterRoutes=(routes:any[],query:string,mode:string)=>routes.filter(route=>isPersistedRoute(route)&&(!query.trim()||`${route.id} ${route.source} ${route.destination}`.toLowerCase().includes(query.trim().toLowerCase()))&&(mode==='all'||routeMode(route)===mode));

export const RouteDashboard = ({ onClose }: { onClose?: () => void }) => {
  const activeRoutes=useAppStore(s=>s.activeRoutes), updateActiveRoute=useAppStore(s=>s.updateActiveRoute), setLastCreatedRouteId=useAppStore(s=>s.setLastCreatedRouteId);
  const [query,setQuery]=useState(''),[mode,setMode]=useState('all'),[selectedId,setSelectedId]=useState<number>(),[adding,setAdding]=useState(false),[editing,setEditing]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const persistedRoutes=useMemo(()=>Object.values(activeRoutes).filter(isPersistedRoute),[activeRoutes]);
  const routes=useMemo(()=>filterRoutes(persistedRoutes,query,mode),[persistedRoutes,query,mode]);
  const selected=routes.find(route=>route.id===selectedId)??routes[0], optimal=selected?.routeData?.optimal_routes?.[0];
  const distance=optimal?.distance??selected?.routeData?.total_distance??selected?.routeData?.distance, duration=optimal?.duration??selected?.routeData?.total_duration??selected?.routeData?.duration, cost=selected?.routeData?.route_cost;
  const save=async()=>{if(!selected)return;setSaving(true);setError('');try{const updated=await routesApi.updateRoute(selected.id,{is_active:selected.isActive!==false,distance:Number(distance),duration:Number(duration),cost:Number(cost)});updateActiveRoute(selected.id,{...selected,isActive:updated.is_active,routeData:{...selected.routeData,...updated.route_data}});setEditing(false)}catch(e:any){setError(e.response?.data?.detail||e.message)}finally{setSaving(false)}};
  return <div className="route-management"><div className="route-management-toolbar"><div><h3>Route Management</h3><span>{routes.length} of {persistedRoutes.length} routes</span></div><div className="route-management-controls"><input aria-label="Search routes" placeholder="Search ID, source or destination" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Filter route mode" value={mode} onChange={e=>setMode(e.target.value)}><option value="all">All modes</option><option value="road">Road</option><option value="air">Air</option><option value="multimodal">Multimodal</option></select><button className="route-modal-close" onClick={onClose} aria-label="Close route management">×</button></div></div>
    <div className="route-management-body"><aside className="route-list">{routes.map(route=><button key={route.id} className={selected?.id===route.id?'selected':''} onClick={()=>{setSelectedId(route.id);setEditing(false)}}><strong>Route {route.id}</strong><span>{route.source} → {route.destination}</span><small>{routeMode(route)} · {route.isActive===false?'Inactive':'Active'}</small></button>)}{!routes.length&&<p className="route-list-empty">No matching routes.</p>}</aside>
      <section className="route-detail">{selected?<><div className="route-detail-heading"><div><span>SELECTED ROUTE</span><h4>Route {selected.id}</h4></div><i className={selected.isActive===false?'inactive':''}>{selected.isActive===false?'Inactive':'Active'}</i></div><dl><div><dt>Source</dt><dd>{selected.source}</dd></div><div><dt>Destination</dt><dd>{selected.destination}</dd></div><div><dt>Mode</dt><dd>{routeMode(selected)}</dd></div><div><dt>Distance</dt><dd>{distance!=null?`${distance} km`:'Not available'}</dd></div><div><dt>Duration / ETA</dt><dd>{duration!=null?formatDuration(duration):'Not available'}</dd></div><div><dt>Route cost</dt><dd>{cost!=null?`₹${Number(cost).toLocaleString()}`:'Not available'}</dd></div><div><dt>Stops</dt><dd>{selected.waypoints?.length||2}</dd></div><div><dt>Created</dt><dd>{selected.created?new Date(selected.created).toLocaleString():'Not available'}</dd></div></dl>
        {editing&&<div className="route-edit-fields"><label>Status<select value={selected.isActive===false?'inactive':'active'} onChange={e=>updateActiveRoute(selected.id,{...selected,isActive:e.target.value==='active'})}><option value="active">Active</option><option value="inactive">Inactive</option></select></label><p>Source, destination and geometry remain read-only to preserve validated map coordinates.</p></div>}{error&&<p className="route-management-error">{error}</p>}<div className="route-management-actions"><button className="primary" onClick={()=>setAdding(true)}>+ Add New Route</button>{editing?<><button onClick={save} disabled={saving}>{saving?'Saving…':'Save Changes'}</button><button onClick={()=>setEditing(false)}>Cancel</button></>:<button onClick={()=>setEditing(true)}>Edit Route</button>}<button onClick={()=>setLastCreatedRouteId(selected.id)}>Show on Map</button></div></>:<div className="route-detail-empty">Select a route to inspect its details.</div>}</section></div><RouteUploadTable isOpen={adding} onClose={()=>setAdding(false)}/></div>;
};
