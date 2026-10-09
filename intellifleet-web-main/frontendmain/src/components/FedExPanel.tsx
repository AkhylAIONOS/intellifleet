import {useOperationsStore} from '../store/operationsStore';
import { useEffect, useState } from 'react';
import { fedexApi, streamTelemetry, type Eligibility, type FedexInput, type ScheduleSummary } from '../api/fedex';
import { useFedexStore } from '../store/fedexStore';
import './FedExPanel.css';
import {LocationInput} from './LocationInput';
import {operationalTime} from '../utils/operationalTime';

export function fedexTime(value: string | null) {
  return operationalTime(value);
}
const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Kolkata', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());

export function FedExPanel() {
  const [source,setSource] = useState('FEDEX');
  const [summary, setSummary] = useState<ScheduleSummary | null>(null);
  const [origin, setOrigin] = useState('UDRPU'); const [gateway, setGateway] = useState('DELGW');
  const [date, setDate] = useState(today); const [ready, setReady] = useState('18:00');
  const [speed, setSpeed] = useState(120); const [delay, setDelay] = useState(30);
  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [connection, setConnection] = useState('Idle');
  const telemetry = useFedexStore(s => s.telemetry);
  const sid = telemetry?.simulation_id;
  useEffect(() => {
    const saved=window.sessionStorage.getItem('liveSimulationId');
    if(!saved || useFedexStore.getState().telemetry)return;
    let active=true;
    fedexApi.state(saved).then(state=>{if(active){useFedexStore.getState().begin(state);useOperationsStore.getState().patch({selected:state.simulation_id});setOrigin(state.origin_station);setGateway(state.gateway);}}).catch(()=>{window.sessionStorage.removeItem('liveSimulationId');setError('Previous simulation is unavailable. Evaluate a service to start again.');});
    return()=>{active=false;};
  }, []);
  useEffect(() => {
    let live = true;
    fedexApi.summary(source).then(s => {if (live) {setSummary(s);if(s.playback_speed)setSpeed(s.playback_speed);if(useFedexStore.getState().telemetry)return;setOrigin(s.lanes[0]?.origin_station || '');setGateway(s.lanes[0]?.gateway || '');}}).catch(() => {if (live) setError('Schedule workbook unavailable. Check the backend connection.');});
    return () => {live=false;};
  }, [source]);
  useEffect(() => {
    if (!sid) return;
    const controller = new AbortController();
    void streamTelemetry(sid, controller.signal, s => useFedexStore.getState().update(s), setConnection);
    return () => controller.abort();
  }, [sid]);
  useEffect(() => {setEligibility(null);}, [source, origin, gateway, date, ready]);
  const input = (): FedexInput => ({origin_station:origin, gateway, simulation_date:date, shipment_ready_datetime:`${date}T${ready}:00+05:30`});
  const perform = async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try {await fn();} catch (e: unknown) {
      const detail = (e as {response?: {data?: {detail?: unknown}}}).response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Action failed. Check inputs and backend connection.');
    } finally {setBusy(false);}
  };
  const start = () => perform(async () => {
    const result = await fedexApi.eligible(input(),source); setEligibility(result);
    if (!result.selected) {setError(result.selection_reason); return;}
    const state = await fedexApi.create({...input(), speed, schedule_id:result.selected.schedule_id},source);
    window.sessionStorage.setItem('liveSimulationId',state.simulation_id);
    window.sessionStorage.setItem('liveScheduleSource',source);
    useFedexStore.getState().begin(state);
    useOperationsStore.getState().patch({selected:state.simulation_id});
  });
  const control = (action: string) => perform(async () => {
    if (!sid) return;
    let state;
    try {state = await fedexApi.control(sid, action, speed);}
    catch (e: unknown) {
      if (action !== 'reset' || (e as {response?: {status?: number}}).response?.status !== 404) throw e;
    }
    if (action === 'reset') {window.sessionStorage.removeItem('liveSimulationId');if(useOperationsStore.getState().selected===sid)useOperationsStore.getState().patch({selected:null});useFedexStore.getState().reset(); setConnection('Idle');}
    else useFedexStore.getState().update(state);
  });
  const supported = summary?.lanes.some(l => l.origin_station===origin && l.gateway===gateway && l.simulation_supported);
  const origins = [...new Set(summary?.lanes.map(l => l.origin_station) || [])];
  const gateways = summary?.lanes.filter(l => l.origin_station===origin).map(l => l.gateway) || [];
  const alert = telemetry?.alerts.at(-1);
  const canInject = telemetry && !telemetry.stopped && !telemetry.paused && ['IN_TRANSIT', 'DELAYED'].includes(telemetry.status);
  return <section className="fedex-panel" aria-label="Schedules and simulations">
    <div className="fedex-heading"><strong>Service schedules & evaluation</strong><span>SIMULATED TELEMETRY</span></div>
    <p className="fedex-note">All times IST · Surface follows map-derived roads. Air/Rail geometry remains approximate. Telemetry is simulated, not actual GPS.</p>
    <div className="fedex-controls">
      <label>Schedule source<select value={source} disabled={busy || !!sid} onChange={e=>{setSummary(null);setEligibility(null);setError('');setSource(e.target.value);}}><option value="FEDEX">Network Schedule</option></select></label>
      <label>Origin Station<LocationInput label="Origin Station" value={origin} disabled={busy||!!sid} locations={origins} onChange={value=>{setOrigin(value);const first=summary?.lanes.find(l=>l.origin_station===value);if(first)setGateway(first.gateway);}}/></label>
      <label>Gateway<LocationInput label="Gateway" value={gateway} disabled={busy||!!sid} locations={[...new Set(gateways)]} onChange={setGateway}/></label>
      <label>Simulation Date<input type="date" value={date} disabled={busy || !!sid} onChange={e=>setDate(e.target.value)}/></label>
      <label>
        Shipment Ready Time
        <input type="time" value={ready} disabled={busy||!!sid} onChange={e=>setReady(e.target.value)}/>

      </label>
      <label>Simulation Speed<select value={speed} disabled={busy} onChange={e=>setSpeed(Number(e.target.value))}>{[...new Set([60,120,300,600,speed])].sort((a,b)=>a-b).map(s=><option key={s} value={s}>{s}×</option>)}</select></label>
      <button disabled={busy || !summary || !!sid || !date || !ready || !origins.includes(origin) || !gateways.includes(gateway)} onClick={()=>perform(async()=>setEligibility(await fedexApi.eligible(input(),source)))}>Evaluate Cutoffs</button>
      <button className="fedex-primary" disabled={busy || !supported || !!sid || !date || !ready} onClick={start}>Start Simulation</button>
    </div>
    {!supported && summary && <p className="fedex-note">This lane supports schedule evaluation only; no demo coordinates are mapped.</p>}
    {error && <p role="alert" className="fedex-error">{error}</p>}
    {eligibility && <details open={!sid}><summary>Service eligibility · {eligibility.selection_reason}</summary>
      <div className="fedex-table"><table><thead><tr><th>Mode / Run / Service</th><th>Cutoff</th><th>ETD</th><th>ETA</th><th>Eligibility</th></tr></thead><tbody>{eligibility.candidates.map(c=><tr key={c.schedule_id}><td>{c.mode} / {c.run} / {c.service}</td><td>{fedexTime(c.cutoff)}</td><td>{fedexTime(c.etd)}</td><td>{fedexTime(c.eta)}</td><td>{c.reason}{c.warnings.filter(w=>!w.startsWith('CALENDAR')).map(w=><div key={w}>{w}</div>)}</td></tr>)}</tbody></table></div>
      {eligibility.next_eligible&&<p className="fedex-note">Next supplied schedule template: {eligibility.next_eligible.service} · Handover {fedexTime(eligibility.next_eligible.cutoff)} · ETD {fedexTime(eligibility.next_eligible.etd)} · ETA {fedexTime(eligibility.next_eligible.eta)}. Operating days are not supplied; availability requires confirmation.</p>}
    </details>}
    {telemetry && <div aria-label="Schedule simulation state">
      <div className="fedex-state"><strong>{telemetry.origin_station} → {telemetry.gateway}</strong><span>{telemetry.mode} · Run {telemetry.run} · {telemetry.service}</span><strong>{telemetry.paused?'PAUSED':telemetry.stopped?'STOPPED':telemetry.status}</strong><span>{connection}</span></div>
      {telemetry.road_routing_status==='READY'&&<p className="fedex-note" aria-label="Road route details">Road-network route · {telemetry.optimization_mode} · {telemetry.route_distance_km?.toFixed(1)} km · Map travel estimate {telemetry.road_estimated_duration_minutes?.toFixed(0)} min. Schedule ETA remains authoritative for this simulation. Shortest/cheapest and verified toll costs are unavailable from this provider.</p>}
      <progress max={1} value={telemetry.progress} aria-label="Shipment progress"/>
      <div className="fedex-state"><span>Clock: {fedexTime(telemetry.simulation_timestamp)}</span><span>Progress: {(telemetry.progress*100).toFixed(1)}%</span><span>Speed: {telemetry.simulation_speed}×</span><span>Cutoff: {fedexTime(telemetry.cutoff)}</span><span>ETD: {fedexTime(telemetry.scheduled_etd)}</span><span>Scheduled ETA: {fedexTime(telemetry.scheduled_eta)}</span><strong>Current ETA: {fedexTime(telemetry.current_eta)}</strong><span>Source retrieval: {fedexTime(telemetry.retrieval)}</span></div>
      <div className="fedex-controls">
        <button disabled={busy || telemetry.stopped || telemetry.status==='ARRIVED_AT_GTW'} onClick={()=>control(telemetry.paused||telemetry.status==='DELAYED'?'resume':'pause')}>{telemetry.paused||telemetry.status==='DELAYED'?'Resume':'Pause'}</button>
        <button disabled={busy || telemetry.stopped} onClick={()=>control('speed')}>Apply Speed</button>
        <button disabled={busy || telemetry.stopped} onClick={()=>control('stop')}>Stop</button>
        <label>Delay Minutes<input type="number" min={1} max={1440} value={delay} onChange={e=>setDelay(Number(e.target.value))}/></label>
        <button disabled={busy || !canInject || delay<=0 || delay>1440} onClick={()=>perform(async()=>useFedexStore.getState().update(await fedexApi.event(sid!,delay)))}>Inject Delay</button>
        <button disabled={busy} onClick={()=>control('reset')}>Reset</button>
      </div>
      {alert && <div role="status" className="fedex-alert"><strong>{alert.severity} · {alert.title}</strong><p>{alert.impact}</p><p>{alert.recommended_action}</p><details><summary>Recommendation basis</summary><p>{alert.reason}</p><p>{alert.alternatives_condition}</p><p>{alert.eligible_alternatives.length} eligible origin services; no action executed.</p></details></div>}
      <p className="fedex-note">Facility coordinates are approximate city locations; Surface endpoints are snapped to roads. Onward readiness is unverified; retrieval is a source milestone, not a confirmed onward flight.</p>
    </div>}
    <details><summary>Schedule assumptions</summary><p className="fedex-note">{summary?.schedule_notice || 'Loading schedule…'}</p></details>
  </section>;
}
