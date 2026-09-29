import {operationalTime} from '../utils/operationalTime';
import {useEffect,useState} from 'react';
import {useAppStore} from '../store/appStore';
import {fedexApi} from '../api/fedex';
import api from '../api/client';
import {movementMatches,useOperationsStore} from '../store/operationsStore';
export function LiveOperations(){
 const warehouses=useAppStore(s=>s.warehouses); const [origin,setOrigin]=useState('');const [destination,setDestination]=useState('');
 const state=useOperationsStore(); const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
 useEffect(()=>{
  if(!state.enabled)return;
  let cancelled=false; let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try{const r=await api.get('/operations/movements');if(!cancelled){state.patch({movements:r.data.movements});setError('');}}
   catch{if(!cancelled)setError('Live network unavailable; last received positions retained.');}
   finally{if(!cancelled)timer=setTimeout(poll,1000);}};
  void poll();return()=>{cancelled=true;clearTimeout(timer);};
 },[state.enabled]);
 const demo=async(count:number)=>{setBusy(true);try{const r=await api.post('/operations/demo',{count,seed:42});state.patch({enabled:true,movements:r.data.movements,fit:state.fit+1});setError('');}
 catch(e:any){setError(e.response?.data?.detail||'Unable to start demo');}finally{setBusy(false);}};
 const selected=state.movements.find(m=>m.simulation_id===state.selected);
 const operate=async(action:string)=>{if(!selected)return;setBusy(true);try{if(action==='delay')await fedexApi.event(selected.simulation_id,30);else await fedexApi.control(selected.simulation_id,action);const r=await api.get('/operations/movements');state.patch({movements:r.data.movements});setError('');}catch(e:any){setError(e.response?.data?.detail||'Action unavailable');}finally{setBusy(false);}};
 const filtered=state.movements.filter(m=>movementMatches(m,state.filter));
 return <section className="fedex-panel" aria-label="Live network">
  <div className="fedex-controls"><button aria-pressed={state.enabled} onClick={()=>state.patch({enabled:!state.enabled,fit:state.fit+1})}>SHOW ALL MOVEMENTS</button>
  <label>Filter<select value={state.filter} onChange={e=>state.patch({filter:e.target.value})}>{['ALL','SURFACE','AIR','RAIL','FEDEX','SYNTHETIC'].map(f=><option key={f}>{f}</option>)}</select></label>
  <button onClick={()=>state.patch({fit:state.fit+1})}>Fit network</button>
  {[10,50,100].map(n=><button disabled={busy} key={n} onClick={()=>demo(n)}>Simulate {n}</button>)}</div>
  <div className="fedex-controls"><label>Origin<select value={origin} onChange={e=>setOrigin(e.target.value)}><option value="">Select</option>{warehouses.map(w=><option key={w.name}>{w.name}</option>)}</select></label><label>Destination<select value={destination} onChange={e=>setDestination(e.target.value)}><option value="">Select</option>{warehouses.map(w=><option key={w.name}>{w.name}</option>)}</select></label>
  <button disabled={busy||!origin||!destination||origin===destination} onClick={async()=>{setBusy(true);try{const r=await api.post('/operations/route-simulation',{origin,destination,weight:6000});state.patch({enabled:true,selected:r.data.simulation_id,fit:state.fit+1});setError('');}catch(e:any){setError(e.response?.data?.detail||'Route unavailable');}finally{setBusy(false);}}}>Plan & simulate 6000 kg</button></div>
  <p className="fedex-note">Python demo telemetry · Schedule templates are not live vehicles. Network demo runs are hypothetical; they do not reserve fleet capacity.</p>
  {selected&&selected.status!=='SCHEDULE_TEMPLATE'&&<div aria-label="Selected movement"><strong>{selected.shipment_id} · {selected.status} · ETA {operationalTime(selected.current_eta)}</strong><div className="fedex-controls"><button disabled={busy||selected.stopped} onClick={()=>operate(selected.paused?'resume':'pause')}>{selected.paused?'Resume':'Pause'}</button><button disabled={busy||selected.stopped||selected.paused||!['IN_TRANSIT','DELAYED'].includes(selected.status)} onClick={()=>operate('delay')}>Inject 30 minute delay</button><button disabled={busy||selected.stopped} onClick={()=>operate('stop')}>Stop movement</button></div>{selected.alerts?.slice(-1).map((a,i)=><p role="status" key={i}>{a.impact} · {a.recommended_action}</p>)}</div>}
  {error&&<p role="alert">{error}</p>}
  {state.enabled&&<details><summary>{filtered.length} movements / templates · inspect or select</summary><div style={{maxHeight:180,overflow:'auto'}}>{filtered.map(m=><div key={m.simulation_id}><button onClick={()=>state.patch({selected:m.simulation_id})}>{m.shipment_id} · {m.origin_station} → {m.gateway}</button> {m.mode} · {m.status} · {m.data_source} · ETA {operationalTime(m.current_eta)} · Delay {m.delay_minutes} min</div>)}</div></details>}
 </section>;
}
