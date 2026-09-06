import { useAppStore } from '../store/appStore';
import { normalizeVisualPlan, planRouteName, type PlanComparison, type VisualPlan } from '../utils/planVisuals';
import './PlanVisuals.css';
import { OperationDetails } from './OperationDetails';
const number = (value: number) => value.toLocaleString('en-IN', {maximumFractionDigits:6});
const money = (value: number) => `₹${value.toLocaleString('en-IN', {maximumFractionDigits:2})}`;
const percent = (value: number) => `${(value * 100).toFixed(2)}%`;
export function PlanSnapshot({plan: rawPlan}: {plan: VisualPlan}) {
  const plan = normalizeVisualPlan(rawPlan);
  const metrics = [['Cost',plan.operational_cost,money], ['ETA',plan.duration_hours,(n:number)=>`${n} h`],
    ['Risk',plan.risk_score,percent], ['Reliability',plan.reliability,percent]] as const;
  return <section className="plan-snapshot" aria-label="Plan Snapshot">
    <div className="snapshot-heading"><strong>Plan Snapshot</strong><span>{plan.mode}</span></div>
    <p className="snapshot-route">{planRouteName(plan)}</p>
    <dl className="snapshot-metrics">{metrics.map(([label,value,format]) => value != null && <div key={label}><dt>{label}</dt><dd>{format(value)}</dd></div>)}</dl>
    {!!plan.vehicles?.length && <div className="snapshot-vehicles">{plan.vehicles.map((v,i) => <div key={`${v.id}-${i}`}><strong>{v.label || v.id}</strong> <span>{v.type}</span>
      {v.assigned_load_kg != null && <span>Load {number(v.assigned_load_kg)}{v.capacity != null ? ` / ${number(v.capacity)}` : ''} kg</span>}
      {v.assigned_load_kg == null && v.capacity != null && <span>Capacity {number(v.capacity)} kg</span>}
      {v.utilization_percentage != null && <span>{number(v.utilization_percentage)}% utilized</span>}</div>)}</div>}
    {plan.route_legs.length > 1 && <ol className="journey-strip" aria-label="Route journey">{plan.route_legs.map((leg,i)=><li key={i}>
      {i === 0 && <span>{leg.from_location}</span>}<small>↓ {leg.route_type}</small><span>{leg.to_location}</span></li>)}</ol>}
  </section>;
}
export function PlanDelta({comparison}: {comparison:PlanComparison}) {
  const {before,after,differences} = comparison;
  const rows = [
    {label:'Cost',a:before.operational_cost,b:after.operational_cost,delta:differences?.cost_difference,format:money,unit:''},
    {label:'ETA',a:before.duration_hours,b:after.duration_hours,delta:differences?.eta_difference_hours,format:(v:number)=>`${v.toFixed(2)} h`,unit:''},
    {label:'Risk',a:before.risk_score,b:after.risk_score,delta:differences?.risk_difference,format:percent,unit:' pp'},
  ];
  return <section className="plan-delta" aria-label="Plan comparison"><strong>{comparison.beforeLabel} → {comparison.afterLabel}</strong>
    <div className="delta-routes"><div><b>{before.mode}</b><small>{planRouteName(before)}</small></div><span>→</span><div><b>{after.mode}</b><small>{planRouteName(after)}</small></div></div>
    <table><thead><tr><th>Metric</th><th>{comparison.beforeLabel}</th><th>{comparison.afterLabel}</th><th>Change</th></tr></thead>
      <tbody>{rows.map(row => {
        if (row.a == null || row.b == null) return null;
        // Display-only subtraction of authoritative totals; never recalculate logistics metrics.
        const delta = row.delta ?? row.b - row.a;
        const change = row.unit ? `${(Math.abs(delta) * 100).toFixed(2)}${row.unit}` : row.format(Math.abs(delta));
        return <tr key={row.label}><th>{row.label}</th><td>{row.format(row.a)}</td><td>{row.format(row.b)}</td><td className={delta < 0 ? 'delta-benefit' : delta > 0 ? 'delta-tradeoff' : ''}>
          {delta > 0 ? '+' : delta < 0 ? '−' : ''}{change}<small>{delta < 0 ? 'Decrease' : delta > 0 ? 'Increase' : 'Unchanged'}</small></td></tr>;
      })}</tbody></table></section>;
}
export function CurrentPlanVisuals() {
  const plan = useAppStore(s=>s.selectedPlan), comparison=useAppStore(s=>s.planComparison), notice=useAppStore(s=>s.planNotice);
  const operation = useAppStore(s=>s.operationResult);
  if (!plan && !comparison && !notice && !operation) return null;
  return <details className="chat-plan-summary" open><summary>Current shipment</summary><div className="current-plan-visuals">{notice && <p className="plan-notice" role="status">{notice}</p>}
    <OperationDetails result={operation}/>
    {plan && <PlanSnapshot plan={plan}/>} {comparison && <PlanDelta comparison={comparison}/>}</div></details>;
}
