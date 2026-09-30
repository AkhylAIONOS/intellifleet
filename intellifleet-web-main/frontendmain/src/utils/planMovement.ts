import api from '../api/client';
import {useAuthStore} from '../store/authStore';
import {fedexApi} from '../api/fedex';
import {useOperationsStore} from '../store/operationsStore';
import {useAppStore} from '../store/appStore';

const pending = new Map<string, Promise<void>>();
export function ensurePlanMovement(plan:any):Promise<void> {
  if(!plan?.plan_id || !plan.vehicles?.length || !plan.route_legs?.length ||
    !plan.route_legs.every((leg:any)=>['road','ground','surface'].includes(String(leg?.route_type).toLowerCase())))return Promise.resolve();
  const id=String(plan.plan_id);
  const existing=useOperationsStore.getState().movements.find(m=>m.shipment_id===`PLAN-${id}`&&!m.stopped);
  if(existing)return Promise.resolve();
  if(pending.has(id))return pending.get(id)!;
  const ownerToken=useAuthStore.getState().token;
  const task=(async()=>{
    try {
      const {data:simulation}=await api.post(`/operations/plan-journeys/${encodeURIComponent(id)}`);
      if(useAuthStore.getState().token!==ownerToken)return;
      const current=useOperationsStore.getState();
      current.patch({enabled:true,viewMode:current.viewMode==='LIVE'?'LIVE':'AI',filter:'ALL',selected:simulation.simulation_id,
        aiSimulationIds:[...new Set([...current.aiSimulationIds,simulation.simulation_id])],
        movements:[...current.movements.filter(m=>m.simulation_id!==simulation.simulation_id),simulation]});
      // Only a newly prepared origin is resumed. A duplicate request must not
      // resume an operator-paused movement that is already in transit.
      if(simulation.paused && simulation.progress===0){
        const updated=await fedexApi.control(simulation.simulation_id,'resume');
        const latest=useOperationsStore.getState();
        latest.patch({movements:latest.movements.map(m=>m.simulation_id===updated.simulation_id?updated:m)});
      }
    } catch(error:any) {
      const detail=error?.response?.data?.detail;
      useAppStore.setState({planNotice:typeof detail==='string'?detail:'Road journey unavailable. Check the routing service and retry.'});
    }
  })().finally(()=>pending.delete(id));
  pending.set(id,task);return task;
}
