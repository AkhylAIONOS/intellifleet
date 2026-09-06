import { useEffect, useReducer, useState } from 'react';
import { planningApi, type PlanningInput } from '../api/planning';
import './PlanningPanel.css';
import { PlanSnapshot, PlanDelta } from './PlanVisuals';
import { useAppStore } from '../store/appStore';

export const planResultPanelReducer=(_visible:boolean,action:'show'|'close')=>action==='show';

export const PlanningPanel = () => {
  const applyPlanningMapPlan=useAppStore(s=>s.applyPlanningMapPlan);
  const [input, setInput] = useState<PlanningInput>({ source: '', destination: '', shipment: { weight_kg: 1000, quantity: 1 }, objective: 'balanced', allowed_modes: ['road', 'air', 'multimodal'], target_margin: .2 });
  const [result, setResult] = useState<any>();
  const [resultVisible,dispatchResultVisibility]=useReducer(planResultPanelReducer,false);
  const [activePlanId,setActivePlanId]=useState<string>();
  const [scenario, setScenario] = useState<any>();
  const [fuelIncrease,setFuelIncrease]=useState(20); const [blockedRoute,setBlockedRoute]=useState('');
  const [busy, setBusy] = useState(false);
  const update = (key: string, value: unknown) => setInput({ ...input, [key]: value });

  const showOnMap=(recommended:any)=>applyPlanningMapPlan({planning_request:input,recommended_plan:recommended});
  const plan = async () => {
    setBusy(true);
    try { const value=await planningApi.createPlan(input); setResult(value); setActivePlanId(value.recommended_plan_id); showOnMap(value.recommended_plan); dispatchResultVisibility('show'); } finally { setBusy(false); }
  };
  const simulate = async () => {
    setBusy(true);
    const changes:any={fuel_cost_multiplier:1+fuelIncrease/100};
    if(blockedRoute.includes('→')) changes.blocked_routes=[blockedRoute.split('→').map(x=>x.trim())];
    try { const value=await planningApi.createScenario(input, changes); setScenario(value); applyPlanningMapPlan(value); } finally { setBusy(false); }
  };
  const act = async (action: 'apply' | 'discard') => { const value=await planningApi.scenarioAction(scenario.scenario_id, action); setScenario({ ...scenario, ...value }); applyPlanningMapPlan(value); };
  const recommended = result?.candidate_plans?.find((x:any)=>x.plan_id===activePlanId) || result?.recommended_plan;
  const scenarioPlan = scenario?.scenario?.recommended_plan;
  useEffect(()=>{
    if(!resultVisible)return;
    const closeOnEscape=(event:KeyboardEvent)=>{if(event.key==='Escape')dispatchResultVisibility('close')};
    window.addEventListener('keydown',closeOnEscape);
    return()=>window.removeEventListener('keydown',closeOnEscape);
  },[resultVisible]);

  return <section className="planning-panel">
    <div className="planner-heading"><div><span>PLAN A SHIPMENT</span><h2>Supply-Chain Planner</h2></div></div>
    <div className="planning-form">
      <label>Source<input placeholder="Delhi" value={input.source} onChange={e => update('source', e.target.value)} /></label>
      <label>Destination<input placeholder="Mumbai" value={input.destination} onChange={e => update('destination', e.target.value)} /></label>
      <label>Weight (kg)<input aria-label="Weight kg" type="number" value={input.shipment.weight_kg} onChange={e => update('shipment', { ...input.shipment, weight_kg: Number(e.target.value) })} /></label>
      <label>Quantity<input aria-label="Quantity" type="number" value={input.shipment.quantity} onChange={e => update('shipment', { ...input.shipment, quantity: Number(e.target.value) })} /></label>
      <label>Objective<select value={input.objective} onChange={e => update('objective', e.target.value)}>
        <option value="balanced">Balanced</option><option value="cheapest">Cheapest</option>
        <option value="fastest">Fastest</option><option value="lowest-risk">Lowest risk</option>
      </select></label>
      <label>Max Risk<input aria-label="Maximum risk" type="number" min="0" max="1" step=".05" placeholder="0–1" onChange={e=>update('max_risk',e.target.value?Number(e.target.value):undefined)}/></label>
      <label>Deadline<input aria-label="Delivery deadline" type="datetime-local" onChange={e=>update('deadline',e.target.value?new Date(e.target.value).toISOString():undefined)}/></label>
      <button className="calculate-plan" disabled={busy || !input.source || !input.destination} onClick={plan}>{busy?'Calculating…':'Calculate Plan'}</button>
    </div>
    <details className="scenario-controls"><summary>What-if scenario controls</summary><div>
      <label>Fuel increase (%)<input aria-label="Fuel increase percent" type="number" value={fuelIncrease} onChange={e=>setFuelIncrease(Number(e.target.value))}/></label>
      <label>Blocked route<input aria-label="Blocked route" placeholder="Delhi → Mumbai" value={blockedRoute} onChange={e=>setBlockedRoute(e.target.value)}/></label>
      <button disabled={busy || !recommended} onClick={simulate}>Run What-if Scenario</button>
    </div></details>
    {recommended && resultVisible && <div className="planner-result" role="dialog" aria-label="Recommended Plan">
      <div className="planner-result-heading"><h3>Recommended Plan</h3><button type="button" className="planner-result-close" aria-label="Close recommended plan" onClick={()=>dispatchResultVisibility('close')}>×</button></div>
      <PlanSnapshot plan={recommended} />
      <div className="plan-metrics">
        <span><b>Mode</b>{recommended.mode}</span><span><b>Cost</b>₹{recommended.operational_cost.toLocaleString()}</span>
        <span><b>ETA</b>{recommended.duration_hours} h</span><span><b>Risk</b>{(recommended.risk_score * 100).toFixed(1)}%</span>
        <span><b>SLA</b>{recommended.sla_met == null ? 'No deadline' : recommended.sla_met ? 'Met' : 'Missed'}</span>
        <span><b>Vehicle utilization</b>{(recommended.vehicle_utilization * 100).toFixed(1)}%</span>
      </div><p>{result.reason}</p>
      <details><summary>Cost, route, vehicles and inventory</summary><pre>{JSON.stringify({cost_breakdown:recommended.cost_breakdown,route_legs:recommended.route_legs,vehicles:recommended.vehicles,inventory_allocation:recommended.inventory_allocation},null,2)}</pre></details>
      <div className="plan-options">{result.candidate_plans.map((plan:any,index:number)=><button key={plan.plan_id} className={plan.plan_id===activePlanId?'selected':''} onClick={()=>{setActivePlanId(plan.plan_id);showOnMap(plan)}}>Plan {String.fromCharCode(65+index)} · {plan.mode}</button>)}</div>
      <details><summary>Alternative plan details</summary><pre>{JSON.stringify(result.candidate_plans, null, 2)}</pre></details>
    </div>}
    {scenarioPlan && <div className="scenario-card"><h3>Draft What-if Scenario</h3>
      {scenario.baseline?.recommended_plan && <PlanDelta comparison={{before:scenario.baseline.recommended_plan,after:scenarioPlan,beforeLabel:'Baseline',afterLabel:'Scenario',differences:scenario.comparison}} />}
      <p>Status: {scenario.status}</p>{scenario.status === 'draft' && <><button onClick={() => act('apply')}>Apply Plan</button><button onClick={() => act('discard')}>Discard</button></>}
    </div>}
  </section>;
};
