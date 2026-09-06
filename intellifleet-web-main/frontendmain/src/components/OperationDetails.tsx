import { Component, type ReactNode } from 'react';

type Row = Record<string, unknown>;
const rows = (value: unknown): Row[] => Array.isArray(value) ? value.filter((x): x is Row => !!x && typeof x === 'object' && !Array.isArray(x)) : [];
const display = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-IN', {maximumFractionDigits: 2}) : typeof value === 'string' ? value : typeof value === 'boolean' ? (value ? 'Yes' : 'No') : 'Unavailable';
function Table({title, data, columns}: {title: string; data: Row[]; columns: [string, string][]}) {
  if (!data.length) return null;
  return <section className="plan-delta" aria-label={title}><strong>{title}</strong><div style={{overflowX:'auto'}}><table><thead><tr>{columns.map(([key,label])=><th key={key}>{label}</th>)}</tr></thead><tbody>{data.map((row,index)=><tr key={index}>{columns.map(([key])=><td key={key}>{display(row[key])}</td>)}</tr>)}</tbody></table></div></section>;
}
class DetailsBoundary extends Component<{children:ReactNode; result:unknown},{failed:boolean; result:unknown}> {
  state = {failed:false,result:undefined as unknown};
  static getDerivedStateFromProps(props:{result:unknown},state:{result:unknown}) { return props.result !== state.result ? {failed:false,result:props.result} : null; }
  static getDerivedStateFromError() { return {failed:true}; }
  render() { return this.state.failed ? <p role="status">Planning details are unavailable for this result.</p> : this.props.children; }
}
function Details({result}: {result:Row}) {
  const allocations=rows(result.allocation).map(row=>{
    const plan=row.plan && typeof row.plan==='object' ? row.plan as Row : {};
    return {...row,cost:plan.operational_cost,eta:plan.duration_hours,risk:plan.risk_score};
  });
  return <>
    <Table title="Warehouse allocations" data={allocations} columns={[["warehouse","Warehouse"],["allocation","Units"],["weight_kg","kg"],["cost","Cost ₹"],["eta","ETA hours"],["risk","Risk"]]}/>
    <Table title="Affected shipments" data={rows(result.affected_shipments)} columns={[["shipment_id","Shipment"],["before_assignment","Before vehicle"],["after_assignment","After vehicle"],["original_start","Original departure"],["new_start","Revised departure"],["cascading_delay_hours","Delay hours"],["sla_met","SLA met"]]}/>
    <Table title="Consolidation comparison" data={rows(result.consolidation_opportunities)} columns={[["original_cost","Separate cost ₹"],["consolidated_cost","Consolidated cost ₹"],["savings","Savings ₹"],["utilization_before","Before utilization"],["utilization_after","After utilization"]]}/>
    <Table title="Candidate facilities" data={rows(result.candidates).filter(row=>'hub' in row)} columns={[["hub","Hub"],["capacity","Capacity"],["incremental_cost","Estimated cost ₹"],["known_cost_subtotal","Known subtotal ₹"],["weighted_distance_km","Weighted geodesic km"]]}/>
    <Table title="Demand assignments" data={rows(result.assignments)} columns={[["demand","Demand group"],["hub","Hub"],["allocated_demand","Allocated demand"]]}/>
  </>;
}
export function OperationDetails({result}: {result:Row|null}) {
  return result ? <DetailsBoundary result={result}><Details result={result}/></DetailsBoundary> : null;
}
