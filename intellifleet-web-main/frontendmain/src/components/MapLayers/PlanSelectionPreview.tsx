import {Polyline,Tooltip} from 'react-leaflet';
import {useAppStore} from '../../store/appStore';
import {useOperationsStore} from '../../store/operationsStore';
import {legPoints} from '../../utils/planVisuals';

// Static approved geometry only. Playback remains owned by the server runtime.
export function PlanSelectionPreview(){
 const plan=useAppStore(s=>s.selectedPlan),state=useOperationsStore();
 if(!plan?.plan_id || (state.viewMode==='AI'&&state.aiDisplayMode==='MULTI_ROUTE') || state.viewMode==='LIVE')return null;
 if(!plan.journey_id && !plan.route_legs.every(l=>['road','ground','surface'].includes(l.route_type)) && !(state.enabled&&state.viewMode==='AI'&&state.aiSimulationIds.length))return null;
 if(state.movements.some(m=>m.plan_id===plan.plan_id&&!m.stopped))return null;
 return <>{plan.route_legs.map((leg,index)=>{const points=legPoints(leg);return points.length<2?null:<Polyline key={`${plan.plan_id}-${index}`} positions={points} pathOptions={{color:leg.route_type==='air'?'#7c3aed':'#3388ff',weight:4,dashArray:leg.route_type==='air'?'10 8':undefined}}><Tooltip>Selected plan · {leg.from_location} → {leg.to_location} · {leg.route_type} · static planned geometry; replay initializing</Tooltip></Polyline>;})}</>;
}
