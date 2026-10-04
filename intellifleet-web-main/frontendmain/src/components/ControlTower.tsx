import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {controlTowerApi,type TowerRun,type TowerSummary} from '../api/controlTower';
import {useControlTowerStore} from '../store/controlTowerStore';
import {useOperationsStore} from '../store/operationsStore';
import {operationalTime} from '../utils/operationalTime';
import './ControlTower.css';

const hours=(n:number|null|undefined)=>n==null?'—':n.toFixed(2);
const clock=(n:number|null)=>n==null?'—':`${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const displayLane=(s:TowerRun['schedule'])=>s.lane==='UNSUPPORTED_FORMULA'?`${s.origin_station} → ${s.gateway}`:s.lane;
export function ControlTower(){
 const [date,setDate]=useState(today),[mode,setMode]=useState('SURFACE'),[status,setStatus]=useState(''),[critical,setCritical]=useState(false);
 const [search,setSearch]=useState(''),[query,setQuery]=useState(''),[page,setPage]=useState(0),[sort,setSort]=useState('lane');
 const [runs,setRuns]=useState<TowerRun[]>([]),[total,setTotal]=useState(0),[summary,setSummary]=useState<TowerSummary|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [loading,setLoading]=useState(true);
 const [con,setCon]=useState(''),[emails,setEmails]=useState(''),[alerts,setAlerts]=useState<Awaited<ReturnType<typeof controlTowerApi.alerts>>|null>(null);
 const selected=useControlTowerStore(s=>s.selected),select=useControlTowerStore(s=>s.select);
 const movement=useOperationsStore(s=>s.selected);
 const requestEpoch=useRef(0);
 const lastMapSelection=useRef<string|null>(null);
 const refresh=useCallback(async()=>{
  const epoch=requestEpoch.current;
  setLoading(true);
  try{
  const [data,kpis]=await Promise.all([controlTowerApi.runs({service_date:date,mode,status:status||undefined,critical:critical||undefined,search:query,sort,offset:page*25,limit:25}),controlTowerApi.summary(date)]);
  if(epoch===requestEpoch.current){setRuns(data.runs);setTotal(data.total);setSummary(kpis);setError('');}
  }finally{if(epoch===requestEpoch.current)setLoading(false);}
 },[date,mode,status,critical,query,page,sort]);
 useEffect(()=>{const timer=setTimeout(()=>{setQuery(search);setPage(0);},250);return()=>clearTimeout(timer);},[search]);
 useEffect(()=>{
  requestEpoch.current++;
  setLoading(true);
  let cancelled=false;
  void Promise.all([controlTowerApi.runs({service_date:date,mode,status:status||undefined,critical:critical||undefined,search:query,sort,offset:page*25,limit:25}),controlTowerApi.summary(date)])
   .then(([data,kpis])=>{if(!cancelled){setRuns(data.runs);setTotal(data.total);setSummary(kpis);setError('');}})
   .catch(()=>{if(!cancelled)setError('Control Tower unavailable. Check the backend connection.');})
   .finally(()=>{if(!cancelled)setLoading(false);});
  return()=>{cancelled=true;requestEpoch.current++;};
 },[date,mode,status,critical,query,page,sort]);
 useEffect(()=>{let cancelled=false;void controlTowerApi.recipients().then(r=>{if(!cancelled)setEmails(r.emails.join(', '));}).catch(()=>{});return()=>{cancelled=true;};},[]);
 useEffect(()=>{
  let cancelled=false;let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try{
   if(!document.hidden){await refresh();const current=useControlTowerStore.getState().selected;
    if(current){const detail=await controlTowerApi.detail(current.run_id);if(!cancelled && useControlTowerStore.getState().selected?.run_id===current.run_id)select(detail);}}
  }catch{if(!cancelled)setError('Updates unavailable; last received operational facts retained.');}
   finally{if(!cancelled)timer=setTimeout(poll,10000);}};
  timer=setTimeout(poll,10000);return()=>{cancelled=true;clearTimeout(timer);};
 },[refresh,select]);
 useEffect(()=>{
  if(!movement){lastMapSelection.current=null;return;}
  if(movement===lastMapSelection.current)return;
  const run=runs.find(r=>r.movement_id===movement);
  if(run)lastMapSelection.current=movement;
  if(run && run.run_id!==selected?.run_id)select(run);
 },[movement,runs,selected?.run_id,select]);
 const perform=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');setNotice('');try{await fn();}catch(e:any){const d=e.response?.data?.detail;setError(e.response?.status>=500?'The operation could not be completed. Existing data retained.':typeof d==='string'?d:'Check the request and backend connection.');}finally{setBusy(false);}};
 const focus=(run:TowerRun)=>{
  select(run);
  const state=useOperationsStore.getState();
  if(run.movement){state.patch({enabled:true,viewMode:'LIVE',filter:'FEDEX',selected:run.movement_id,
   movements:[...state.movements.filter(m=>m.simulation_id!==run.movement_id),run.movement],fit:state.fit+1});}
  else {state.patch({selected:null});setNotice('No live movement is linked to this run. Schedule and scan facts remain available.');}
 };
 const ordered=useMemo(()=>[...runs].sort((a,b)=>sort==='status'?a.status.localeCompare(b.status):sort==='eta'?String(a.current_eta).localeCompare(String(b.current_eta)):a.schedule.lane.localeCompare(b.schedule.lane)),[runs,sort]);
 const cards=summary?[
  ['Total Runs',summary.total_runs],['Air Runs',summary.air_runs],['Surface Runs',summary.surface_runs],
  ['On Time',summary.statuses['ON TIME']||0],['Expected Delay',summary.statuses['EXPECTED DELAY']||0],['Delayed',summary.statuses.DELAYED||0],
  ['Critical Lanes',summary.critical_lanes],['Critical At Risk',summary.critical_lanes_at_risk]]:[];
 return <section className="control-tower" aria-label="FedEx Control Tower">
  <header><div><h2>FedEx Control Tower</h2><p>FedEx Network Plan · operational runs and source timings · all times IST</p></div><span className="ct-source">FEDEX_SOURCE</span></header>
  <div className="ct-toolbar"><label>Service date<input type="date" value={date} onChange={e=>{setDate(e.target.value);setPage(0);select(null);}}/></label>
   <button disabled={busy} onClick={()=>perform(async()=>{await controlTowerApi.importPlan(date);await refresh();setNotice('Provided workbook loaded. Planning alternatives remain separate.');})}>Load FedEx Network Plan</button>
   <button disabled={busy} onClick={()=>perform(refresh)}>Refresh operations</button></div>
  <div className="ct-kpis">{cards.map(([label,value])=><div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
  <nav className="ct-toolbar" aria-label="Linehaul mode">{['SURFACE','AIR'].map(value=><button key={value} aria-pressed={mode===value} onClick={()=>{setMode(value);setPage(0);}}>{value} LINEHAUL</button>)}</nav>
  <div className="ct-toolbar"><label>Search network<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="City, station, lane, run or carrier"/></label>
   <label>Operational status<select value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}>{['','SCHEDULED','ON TIME','EXPECTED DELAY','DELAYED','ARRIVED'].map(s=><option key={s} value={s}>{s||'ALL'}</option>)}</select></label>
   <label className="ct-check"><input type="checkbox" checked={critical} onChange={e=>{setCritical(e.target.checked);setPage(0);}}/>Critical lanes only</label>
   <label>Sort runs<select value={sort} onChange={e=>setSort(e.target.value)}><option value="lane">Lane</option><option value="status">Status</option><option value="eta">Current ETA</option></select></label></div>
 {error&&<p role="alert" className="ct-error">{error}</p>}{notice&&<p role="status">{notice}</p>}
  {loading&&<p role="status">Loading operational runs…</p>}
  <div className="ct-table-wrap" aria-busy={loading}><table><caption>{mode==='AIR'?'Air':'Surface'} linehaul · {total} matching runs · source cells preserved</caption><thead><tr>
   {['Origin City','Origin Station','Transit Hub / GTW','Lane','Run','Mode','Details','No. of Vehicles','Handover at Origin','ETD','ETA','TT (hours)','Status','Elapsed Time (hours)','Estimated Time Left (hours)','Actual Departure Time','Actual Arrival Time','Actual TT (hours)','Critical'].map(h=><th key={h}>{h}</th>)}
  </tr></thead><tbody>{ordered.map(run=>{const s={...run.schedule,lane:displayLane(run.schedule)};return <tr key={run.run_id} className={selected?.run_id===run.run_id?'ct-selected':''}>
   <td>{s.source['Origin City']??s.origin_city}</td><td>{s.source['Origin Station']??s.origin_station}</td><td>{s.source['Transit Hub/GTW']??s.source['Transit GTW']??s.gateway}</td><td><button disabled={busy} onClick={()=>perform(async()=>focus(await controlTowerApi.detail(run.run_id)))}>{s.lane||'Unnamed lane'}</button></td><td>{s.source.Run??s.run}</td><td>{s.source.Mode??s.mode}</td><td>{s.source.Details??s.source.Flight??s.service}</td><td>{s.source['No of Vechiles']??s.vehicle_count??'—'}</td>
   <td>{clock(s.cutoff_minutes)}</td><td>{clock(s.etd_minutes)}</td><td>{clock(s.eta_minutes)}</td><td>{s.transit_minutes==null?'—':hours(s.transit_minutes/60)}</td><td><span className={`ct-status ct-${run.status.toLowerCase().replaceAll(' ','-')}`}>{run.status}</span>{!s.valid&&<small>Source validation required</small>}</td>
   <td>{hours(run.elapsed_hours)}</td><td>{hours(run.estimated_time_left_hours)}</td><td>{run.actual_departure_at?operationalTime(run.actual_departure_at):'—'}</td><td>{run.actual_arrival_at?operationalTime(run.actual_arrival_at):'—'}</td><td>{hours(run.actual_tt_hours)}</td>
   <td><button aria-label={`${run.critical?'Unmark':'Mark'} critical ${s.lane} ${s.mode}`} aria-pressed={run.critical} disabled={busy} onClick={()=>perform(async()=>{const updated=await controlTowerApi.critical(run.run_id,!run.critical);if(selected?.run_id===run.run_id)select(updated);else if(selected?.lane_key===run.lane_key)select({...selected,critical:updated.critical});await refresh();})}>{run.critical?'★ Critical':'☆ Mark'}</button></td>
  </tr>;})}</tbody></table></div>
  {!loading&&!error&&!runs.length&&<p className="ct-empty">No matching operational runs. Load the provided workbook for this date or adjust filters.</p>}
  <div className="ct-toolbar"><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>Previous</button><span>Page {page+1} · 25 rows per page</span><button disabled={(page+1)*25>=total} onClick={()=>setPage(p=>p+1)}>Next</button></div>
  <form className="ct-toolbar" onSubmit={e=>{e.preventDefault();void perform(async()=>{const r=await controlTowerApi.con(con.trim());focus(r.run);setNotice(`${r.con.con_number} · ${r.con.source} · updated ${operationalTime(r.con.event_at)}`);});}}><label>Search CON<input value={con} onChange={e=>setCon(e.target.value)} placeholder="FedEx CON or labelled synthetic CON"/></label><button disabled={busy||!con.trim()}>Locate package</button></form>
  {selected&&<aside className="ct-details" aria-label="Lane details"><header><h3>{displayLane(selected.schedule)} · Run {selected.schedule.run}</h3><button onClick={()=>select(null)}>Close details</button></header>
   <p>{selected.schedule.origin_station} → {selected.schedule.gateway} · {selected.schedule.mode} · {selected.carrier||selected.schedule.service}</p>
   <p><strong>{selected.status}</strong> · Current ETA {selected.current_eta?operationalTime(selected.current_eta):'—'} · Delay {hours(selected.delay_hours)} hours · {selected.critical?'Critical lane':'Standard lane'}</p>
   <p>Execution source: {selected.actual_source||'No departure/arrival event received'} · Location: {selected.location_source||'Unavailable'}</p>
   {selected.latest_location&&<p>{selected.latest_location.latitude.toFixed(5)}, {selected.latest_location.longitude.toFixed(5)} · Updated {operationalTime(selected.last_update_at)}</p>}
   <button disabled={busy||!!selected.movement_id||selected.actual_source==='FEDEX_SCAN'} onClick={()=>perform(async()=>{const run=await controlTowerApi.simulate(selected);focus(run);setNotice('SYNTHETIC_TELEMETRY: demo clock starts at scheduled ETD, using approximate city centres. Source schedule retained; not FedEx GPS or scans.');})}>Start labelled synthetic playback</button>
   <details><summary>Events and packages</summary>{selected.events?.map(e=><p key={e.event_id}>{e.event_type} · {operationalTime(e.event_at)} · {e.source}</p>)}{selected.cons?.map(c=><p key={c.con_number}>{c.con_number} · {c.source}</p>)}</details>
   <details><summary>Original workbook cells and validation</summary><dl>{Object.entries(selected.schedule.source).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v==='UNSUPPORTED_FORMULA'?'Cached value unavailable; reload workbook':v||'—'}</dd></div>)}{Object.entries(selected.schedule.source_formulas||{}).map(([k,v])=><div key={'formula-'+k}><dt>{k} formula</dt><dd>{v} · {selected.schedule.source_value_provenance?.[k]}</dd></div>)}</dl>{selected.schedule.warnings.map(w=><p key={w}>{w}</p>)}</details>
  </aside>}
  <details className="ct-details"><summary>Alert recipients and delivery history</summary><p>Email delivery requires server SMTP configuration and explicit delivery enablement. Alerts are queued on status transitions, never each telemetry tick.</p>
   <label>Selected email recipients<input value={emails} onChange={e=>setEmails(e.target.value)} placeholder="Comma-separated email addresses"/></label>
   <button disabled={busy} onClick={()=>perform(async()=>{await controlTowerApi.saveRecipients(emails.split(',').map(x=>x.trim()).filter(Boolean));setNotice('Alert recipients saved.');})}>Save recipients</button>
   <button onClick={()=>perform(async()=>setAlerts(await controlTowerApi.alerts()))}>Load alert history</button>
   {alerts&&<><p>Delivery {alerts.delivery_enabled?'enabled':'disabled'} on server</p>{alerts.alerts.map(a=><p key={a.id}>#{a.id} · {a.status} · attempts {a.attempts} · {operationalTime(a.created_at)} {a.last_error}</p>)}</>}
  </details>
 </section>;
}
