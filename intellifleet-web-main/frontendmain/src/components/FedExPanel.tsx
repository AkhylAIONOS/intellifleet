import {useOperationsStore} from '../store/operationsStore';
import { useEffect, useState } from 'react';
import { fedexApi, streamTelemetry, type Eligibility, type FedexInput, type ScheduleSummary } from '../api/fedex';
import { useFedexStore } from '../store/fedexStore';
import './FedExPanel.css';

export function fedexTime(value: string | null) {
  return value ? new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata', month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false}).format(new Date(value)) : 'Unavailable';
}
const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Kolkata', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());

export function FedExPanel() {
  const [source,setSource] = useState(()=>window.sessionStorage.getItem('liveScheduleSource') || 'SYNTHETIC');
  const [summary, setSummary] = useState<ScheduleSummary | null>(null);
  const [origin, setOrigin] = useState('UDRPU'); const [gateway, setGateway] = useState('DELGW');
  const [date, setDate] = useState(today); const [ready, setReady] = useState('18:00');
  const [speed, setSpeed] = useState(600); const [delay, setDelay] = useState(30);
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
    fedexApi.summary(source).then(s => {if (live) {setSummary(s);if(useFedexStore.getState().telemetry)return;setOrigin(s.lanes[0]?.origin_station || '');setGateway(s.lanes[0]?.gateway || '');}}).catch(() => {if (live) setError('Schedule workbook unavailable. Configure FEDEX_WORKBOOK_PATH on the backend and restart.');});
    return () => {live=false; useFedexStore.getState().reset();};
  }, [source]);
  useEffect(() => {
    if (!sid) return;
    const controller = new AbortController();
    void streamTelemetry(sid, controller.signal, s => useFedexStore.getState().update(s), setConnection);
    return () => controller.abort();
  }, [sid]);
  useEffect(() => {setEligibility(null);}, [origin, gateway, date, ready]);
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
    <div className="fedex-heading"><strong>Schedules / Live Operations</strong><span>SIMULATED TELEMETRY</span></div>
    <p className="fedex-note">Station → cutoff → ETD → in transit → Gateway · All times IST · Approximate demo locations, synthetic straight-line movement.</p>
    <div className="fedex-controls">
      <label>Schedule source<select value={source} disabled={busy || !!sid} onChange={e=>{setSummary(null);setEligibility(null);setError('');setSource(e.target.value);}}><option value="SYNTHETIC">Synthetic schedules</option><option value="FEDEX">FedEx source workbook</option></select></label>
      <label>Origin Station<select value={origin} disabled={busy || !!sid} onChange={e => {setOrigin(e.target.value); setGateway(summary?.lanes.find(l => l.origin_station===e.target.value)?.gateway || '');}}>{origins.map(o => <option key={o}>{o}</option>)}</select></label>
      <label>Gateway<select value={gateway} disabled={busy || !!sid} onChange={e=>setGateway(e.target.value)}>{gateways.map(g=><option key={g}>{g}</option>)}</select></label>
      <label>Simulation Date<input type="date" value={date} disabled={busy || !!sid} onChange={e=>setDate(e.target.value)}/></label>
      <label>Shipment Ready Time<input type="time" value={ready} disabled={busy || !!sid} onChange={e=>setReady(e.target.value)}/></label>
      <label>Simulation Speed<select value={speed} disabled={busy} onChange={e=>setSpeed(Number(e.target.value))}>{[60,300,600,1200,3600].map(s=><option key={s} value={s}>{s}×</option>)}</select></label>
      <button disabled={busy || !summary || !!sid || !date || !ready} onClick={()=>perform(async()=>setEligibility(await fedexApi.eligible(input(),source)))}>Evaluate Cutoffs</button>
      <button className="fedex-primary" disabled={busy || !supported || !!sid || !date || !ready} onClick={start}>Start Simulation</button>
    </div>
    {!supported && summary && <p className="fedex-note">This lane supports schedule evaluation only; no demo coordinates are mapped.</p>}
    {error && <p role="alert" className="fedex-error">{error}</p>}
    {eligibility && <details open={!sid}><summary>Service eligibility · {eligibility.selection_reason}</summary>
      <div className="fedex-table"><table><thead><tr><th>Mode / Run / Service</th><th>Cutoff</th><th>ETD</th><th>ETA</th><th>Eligibility</th></tr></thead><tbody>{eligibility.candidates.map(c=><tr key={c.schedule_id}><td>{c.mode} / {c.run} / {c.service}</td><td>{fedexTime(c.cutoff)}</td><td>{fedexTime(c.etd)}</td><td>{fedexTime(c.eta)}</td><td>{c.reason}{c.warnings.filter(w=>!w.startsWith('CALENDAR')).map(w=><div key={w}>{w}</div>)}</td></tr>)}</tbody></table></div>
    </details>}
    {telemetry && <div aria-label="FedEx live state">
      <div className="fedex-state"><strong>{telemetry.origin_station} → {telemetry.gateway}</strong><span>{telemetry.mode} · Run {telemetry.run} · {telemetry.service}</span><strong>{telemetry.paused?'PAUSED':telemetry.stopped?'STOPPED':telemetry.status}</strong><span>{connection}</span></div>
      <progress max={1} value={telemetry.progress} aria-label="Shipment progress"/>
      <div className="fedex-state"><span>Clock: {fedexTime(telemetry.simulation_timestamp)}</span><span>Progress: {(telemetry.progress*100).toFixed(1)}%</span><span>Speed: {telemetry.simulation_speed}×</span><span>Cutoff: {fedexTime(telemetry.cutoff)}</span><span>ETD: {fedexTime(telemetry.scheduled_etd)}</span><span>Scheduled ETA: {fedexTime(telemetry.scheduled_eta)}</span><strong>Current ETA: {fedexTime(telemetry.current_eta)}</strong><span>Source retrieval: {fedexTime(telemetry.retrieval)}</span></div>
      <div className="fedex-controls">
        <button disabled={busy || telemetry.stopped || telemetry.status==='ARRIVED_AT_GTW'} onClick={()=>control(telemetry.paused?'resume':'pause')}>{telemetry.paused?'Resume':'Pause'}</button>
        <button disabled={busy || telemetry.stopped} onClick={()=>control('speed')}>Apply Speed</button>
        <button disabled={busy || telemetry.stopped} onClick={()=>control('stop')}>Stop</button>
        <label>Delay Minutes<input type="number" min={1} max={1440} value={delay} onChange={e=>setDelay(Number(e.target.value))}/></label>
        <button disabled={busy || !canInject || delay<=0 || delay>1440} onClick={()=>perform(async()=>useFedexStore.getState().update(await fedexApi.event(sid!,delay)))}>Inject Delay</button>
        <button disabled={busy} onClick={()=>control('reset')}>Reset</button>
      </div>
      {alert && <div role="status" className="fedex-alert"><strong>{alert.severity} · {alert.title}</strong><p>{alert.impact}</p><p>{alert.recommended_action}</p><details><summary>Recommendation basis</summary><p>{alert.reason}</p><p>{alert.alternatives_condition}</p><p>{alert.eligible_alternatives.length} eligible origin services; no action executed.</p></details></div>}
      <p className="fedex-note">Gateway marker is an approximate city location. Onward readiness is unverified; retrieval is a source milestone, not a confirmed onward flight.</p>
    </div>}
    <details><summary>Schedule assumptions</summary><p className="fedex-note">{summary?.schedule_notice || 'Loading schedule…'}</p></details>
  </section>;
}
