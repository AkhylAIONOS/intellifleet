import {operationalTime} from '../utils/operationalTime';
import {useEffect,useRef,useState} from 'react';
import {useAppStore} from '../store/appStore';
import {fedexApi} from '../api/fedex';
import api from '../api/client';
import {pollMovements} from '../api/operations';
import {movementMatches,visibleAiMovement,useOperationsStore,type Movement} from '../store/operationsStore';
export function LiveOperations(){
 const warehouses=useAppStore(s=>s.warehouses); const [origin,setOrigin]=useState('');const [destination,setDestination]=useState('');
 const [weight,setWeight]=useState('');const [playback,setPlayback]=useState(120);
 const state=useOperationsStore(); const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
 const showing=useRef(false);
 useEffect(()=>{
  let active=true;
  void api.get('/operations/movements').then(({data})=>{
   if(!active)return;
   // Backend fleet discovery must never recreate a previous chat's AI scope.
   if(!showing.current)useOperationsStore.getState().patch({movements:data.movements});
  }).catch(()=>{});
  return()=>{active=false;};
 },[]);
 useEffect(()=>{
  if(!state.enabled)return;
  let cancelled=false; let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try{const movements=await pollMovements();if(!cancelled){state.patch({movements});setError('');}}
   catch{if(!cancelled)setError('Live network unavailable; last received positions retained.');}
   finally{if(!cancelled)timer=setTimeout(poll,1000);}};
  void poll();return()=>{cancelled=true;clearTimeout(timer);};
 },[state.enabled]);
 const showAll=async()=>{
  if(showing.current)return;
  showing.current=true;setBusy(true);
  try{
   const {data}=await api.post('/operations/movements/initialize');
   state.patch({enabled:true,viewMode:'LIVE',filter:'ALL',movements:data.movements});
   setError(data.skipped?.length ? `${data.skipped.length} loaded vehicles could not be initialized: ${[...new Set(data.skipped.map((s:{reason:string})=>s.reason))].join('; ')}`
    : data.movements.some((m:Movement)=>m.status!=='SCHEDULE_TEMPLATE'&&!m.stopped) ? ''
    : 'No active movements or available loaded vehicles with compatible routes.');
  }catch(e:any){setError(e.response?.data?.detail||'Unable to populate movements. Load the network and retry.');}
  finally{showing.current=false;setBusy(false);}
 };
 const demo=async(count:number)=>{setBusy(true);try{const r=await api.post('/operations/demo',{count,seed:42});state.patch({enabled:true,viewMode:'LIVE',movements:r.data.movements,fit:state.fit+1});setError('');}
 catch(e:any){setError(e.response?.data?.detail||'Unable to start demo');}finally{setBusy(false);}};
 const selected=state.movements.find(m=>m.simulation_id===state.selected);
 const operate=async(action:string)=>{if(!selected)return;setBusy(true);try{if(action==='delay')await fedexApi.event(selected.simulation_id,30);else if(action==='breakdown')await api.post(`/fedex/simulations/${selected.simulation_id}/events`,{event_type:'BREAKDOWN',expected_delay_minutes:30});else await fedexApi.control(selected.simulation_id,action,playback);const r=await api.get('/operations/movements');state.patch({movements:r.data.movements});setError('');}catch(e:any){setError(e.response?.data?.detail||'Action unavailable');}finally{setBusy(false);}};
 const filtered=state.movements.filter(m=>!m.stopped && m.status!=='SCHEDULE_TEMPLATE' && movementMatches(m,state.filter) && (state.viewMode!=='AI'||visibleAiMovement(m,state)));
 return <section className="fedex-panel" aria-label="Live network">
  <div className="fedex-controls"><button
    aria-pressed={state.viewMode==='LIVE'}
    disabled={busy}
    onClick={()=>{
      if(state.viewMode==='LIVE'){
        state.patch({
          enabled:state.aiSimulationIds.length>0,
          viewMode:state.aiSimulationIds.length>0?'AI':'OFF',
          filter:'ALL',
          selected:null
        });
      }else{
        void showAll();
      }
    }}
  >
    {state.viewMode==='LIVE'
      ? 'HIDE ALL MOVEMENTS'
      : 'SHOW ALL MOVEMENTS'}
  </button>
  <label>Filter<select value={state.filter} onChange={e=>state.patch({filter:e.target.value})}>{['ALL','SURFACE','AIR','RAIL','FEDEX','SYNTHETIC'].map(f=><option key={f}>{f}</option>)}</select></label>
  <button onClick={()=>state.patch({fit:state.fit+1})}>Fit network</button>
  <details><summary>Advanced simulation testing</summary>{[10,50,100].map(n=><button disabled={busy} key={n} onClick={()=>demo(n)}>Simulate {n}</button>)}</details></div>
  <div className="fedex-controls"><label>Origin<select value={origin} onChange={e=>setOrigin(e.target.value)}><option value="">Select</option>{warehouses.map(w=><option key={w.name}>{w.name}</option>)}</select></label><label>Destination<select value={destination} onChange={e=>setDestination(e.target.value)}><option value="">Select</option>{warehouses.map(w=><option key={w.name}>{w.name}</option>)}</select></label>
  <label>Shipment weight (kg)<input type="number" min="0.01" step="any" value={weight} onChange={e=>setWeight(e.target.value)}/></label>
  <button disabled={busy||!origin||!destination||origin===destination||!Number.isFinite(Number(weight))||Number(weight)<=0} onClick={async()=>{setBusy(true);try{const r=await api.post('/operations/route-simulation',{origin,destination,weight:Number(weight)});state.patch({enabled:true,viewMode:'LIVE',selected:r.data.simulation_id,fit:state.fit+1});setError('');}catch(e:any){setError(e.response?.data?.detail||'Route unavailable');}finally{setBusy(false);}}}>Plan & simulate</button></div>
  <p className="fedex-note">Python simulated telemetry · Schedule templates are not live vehicles. Network demo runs are hypothetical; they do not reserve fleet capacity.</p>
  {selected&&selected.status!=='SCHEDULE_TEMPLATE'&&<div aria-label="Selected movement"><strong>{selected.shipment_id} · {selected.status} · ETA {operationalTime(selected.current_eta)}</strong><p>{selected.mode} · {selected.origin_station} → {selected.gateway} · Position {selected.latitude?.toFixed(5)}, {selected.longitude?.toFixed(5)} · Progress {((selected.progress||0)*100).toFixed(1)}% · ETD {operationalTime(selected.scheduled_etd)} · Delay {selected.delay_minutes} min</p>{selected.route_source&&<p className="fedex-note">{selected.route_source} · {selected.optimization_mode || 'Mode-specific geometry'} · {selected.route_distance_km?.toFixed(1)} km · Simulated GPS; existing plan/schedule timing retained.</p>}<div className="fedex-controls"><button disabled={busy||selected.stopped} onClick={()=>operate(selected.paused||selected.status==='DELAYED'?'resume':'pause')}>{selected.paused||selected.status==='DELAYED'?'Resume':'Pause'}</button><button disabled={busy||selected.stopped||selected.paused||!['IN_TRANSIT','DELAYED'].includes(selected.status)} onClick={()=>operate('delay')}>Inject 30 minute delay</button>{selected.mode==='SURFACE'&&<button disabled={busy||selected.stopped||selected.paused||selected.status!=='IN_TRANSIT'} onClick={()=>operate('breakdown')}>Breakdown +30 min</button>}<button disabled={busy||selected.stopped} onClick={()=>operate('stop')}>Stop movement</button><label>Playback speed<select value={playback} onChange={e=>setPlayback(Number(e.target.value))}>{[60,120,300,600].map(s=><option key={s} value={s}>{s}×</option>)}</select></label><button disabled={busy||selected.stopped} onClick={()=>operate('speed')}>Apply playback speed</button><span>Current: {selected.simulation_speed || 120}×</span></div>{selected.alerts?.slice(-1).map((a,i)=><p role="status" key={i}>{a.impact} · {a.previous_eta&&<>Previous ETA {operationalTime(a.previous_eta)} · </>}{a.recommended_action}</p>)}</div>}
  {error&&<p role="alert">{error}</p>}
  {state.enabled&&<details><summary>{filtered.length} movements · inspect or select</summary><div style={{maxHeight:180,overflow:'auto'}}>{filtered.map(m=><div key={m.simulation_id}><button onClick={()=>state.patch({selected:m.simulation_id})}>{m.shipment_id} · {m.origin_station} → {m.gateway}</button> {m.mode} · {m.status} · {m.data_source} · ETA {operationalTime(m.current_eta)} · Delay {m.delay_minutes} min</div>)}</div></details>}
 </section>;
}
