import {useEffect,useState} from 'react';
import api from '../api/client';

export const formatUploadError=(error:any):string=>{
 const status=error.response?.status;
 if(status===401)return 'Network unavailable: authentication required. Please sign in again.';
 if(status===403)return 'Network unavailable: permission denied.';
 if(status>=500)return 'Schedule workbook unavailable. Check the backend configuration.';
 if(!error.response)return 'Unable to reach the network API. Check that the backend is running and allows this frontend origin.';
 const detail=error.response?.data?.detail;
 if(Array.isArray(detail))return detail.map((item:any)=>`${item.loc?.at(-1)||'request'}: ${item.msg||'Invalid value'}`).join('\n');
 return typeof detail==='string'?detail:'Schedule workbook unavailable. Check the backend configuration.';
};

// Retain the component name for workspace compatibility. Topology is read-only.
export const NetworkUpload=({compact=false}:{compact?:boolean})=>{
 const [search,setSearch]=useState('');
 const [model,setModel]=useState<any>();const [error,setError]=useState('');
 useEffect(()=>{let active=true;api.get('/client-network').then(r=>{if(active)setModel(r.data);}).catch(e=>{if(active)setError(formatUploadError(e));});return()=>{active=false;};},[]);
 const stats=model?.summary;
 return <div className="network-tools" aria-label="Network overview">
 {error&&<p role="alert">{error}</p>}
 <section className="network-summary"><div className="section-title"><span>Network</span><small>Source topology · simulated operational attributes</small></div><dl>
 {stats&&Object.entries({'Services':stats.client_services,'Stations':stats.client_nodes,'Air Runs':stats.air_runs,'Surface Runs':stats.surface_runs,'Train Runs':stats.train_runs,'Resources':stats.generated_resources,'Simulated Shipments':stats.simulated_shipments,'Simulated Volume (kg)':stats.simulated_volume_kg,'Utilization (%)':stats.utilization_percentage}).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{Number(value).toLocaleString('en-IN')}</dd></div>)}
 </dl>{!stats&&!error&&<p>Loading network…</p>}</section>
 {!compact&&model&&<><p>{stats.source_validation_issues} source records require validation. Resource capacities, shipments, costs and risk are simulated. Source schedules remain unchanged.</p><label>Search network<input aria-label="Search network" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Location name, code, lane or service"/></label><div className="operations-table"><table><caption>Supplied services</caption><thead><tr>{['Lane','Origin','Gateway','Mode','Run','Service','Resources','Capacity (kg)','Load (kg)'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{model.routes.filter((route:any)=>[route.from_location,route.to_location,model.locations?.[route.from_location]?.label,model.locations?.[route.to_location]?.label,...(model.locations?.[route.from_location]?.aliases||[]),...(model.locations?.[route.to_location]?.aliases||[]),route.schedule.lane,route.schedule.service].join(" ").toLowerCase().includes(search.toLowerCase())).map((route:any)=>{const resources=model.vehicles.filter((v:any)=>v.service_id===route.route_id);return <tr key={route.route_id}><td>{route.schedule.lane}</td><td>{model.locations?.[route.from_location]?.label||route.from_location}</td><td>{model.locations?.[route.to_location]?.label||route.to_location}</td><td>{route.schedule.source_mode}</td><td>{route.schedule.run}</td><td>{route.schedule.service}</td><td>{resources.length}</td><td>{resources.reduce((sum:number,v:any)=>sum+v.capacity,0).toLocaleString()}</td><td>{resources.reduce((sum:number,v:any)=>sum+v.assigned_load_kg,0).toLocaleString()}</td></tr>;})}</tbody></table></div></>}
 </div>;
};
