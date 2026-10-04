import api from '../api/client';
import {useAuthStore} from '../store/authStore';
import {fedexApi} from '../api/fedex';
import {useOperationsStore} from '../store/operationsStore';
import {useAppStore} from '../store/appStore';
import {useControlTowerStore} from '../store/controlTowerStore';

const pending = new Map<string, Promise<void>>();
export function ensurePlanMovement(plan:any):Promise<void> {
  if(!plan?.plan_id || !plan.vehicles?.length || !plan.route_legs?.length ||
    !plan.route_legs.every((leg:any)=>['road','ground','surface','air'].includes(String(leg?.route_type).toLowerCase())))return Promise.resolve();
  const id=String(plan.plan_id);
  useControlTowerStore.getState().select(null);
  const journeyId=String(plan.journey_id || id);
  const scope=useOperationsStore.getState();
  if(useAppStore.getState().selectedPlan?.plan_id===id)scope.patch({pendingPlanId:id,enabled:true,viewMode:'AI',filter:'ALL'});
  const generation=scope.aiSessionGeneration;
  const existing=scope.movements.find(m =>
    m.shipment_id===`PLAN-${journeyId}` &&
    String(m.plan_id || '')===id
  );
  if(existing && (!plan.revision || existing.revision===plan.revision)){
    if(!existing.stopped)scope.patch({pendingPlanId:null,enabled:true,viewMode:'AI',filter:'ALL',selected:existing.simulation_id,
      aiSimulationIds:[...new Set([...scope.aiSimulationIds,existing.simulation_id])]});
    return Promise.resolve();
  }
  const key=`${generation}:${id}`;
  if(pending.has(key))return pending.get(key)!;
  const ownerToken=useAuthStore.getState().token;
  const selectionAtStart=useAppStore.getState().selectedPlan?.plan_id;
  const task=(async()=>{
    try {
      const {data:received}=await api.post(`/operations/plan-journeys/${encodeURIComponent(id)}`);
      // Older replay responses omit revision metadata. The requested plan ID
      // is authoritative at this boundary, never inferred from an OD pair.
      const simulation={...received,plan_id:received.plan_id || id};
      if(useAuthStore.getState().token!==ownerToken || useOperationsStore.getState().aiSessionGeneration!==generation)return;
      const selectedId=useAppStore.getState().selectedPlan?.plan_id;
      if(selectedId!==selectionAtStart && selectedId && String(selectedId)!==id)return;
      const current=useOperationsStore.getState();
      current.patch({pendingPlanId:null,enabled:true,viewMode:'AI',filter:'ALL',selected:simulation.simulation_id,
        aiSimulationIds:[...new Set([...current.aiSimulationIds,simulation.simulation_id])],
        movements:[...current.movements.filter(m=>m.simulation_id!==simulation.simulation_id),simulation]});
      if(simulation.journey_id && useAppStore.getState().selectedPlan?.plan_id===id){
        useAppStore.getState().applyPlanningMapPlan({recommended_plan:{...plan,journey_id:simulation.journey_id,revision:simulation.revision},movement:simulation});
      }
      // Only a newly prepared origin is resumed. A duplicate request must not
      // resume an operator-paused movement that is already in transit.
      if(simulation.paused && simulation.progress===0){
        const updated=await fedexApi.control(simulation.simulation_id,'resume');
        if(useAuthStore.getState().token!==ownerToken || useOperationsStore.getState().aiSessionGeneration!==generation || (useAppStore.getState().selectedPlan?.plan_id!==selectionAtStart && useAppStore.getState().selectedPlan?.plan_id && String(useAppStore.getState().selectedPlan?.plan_id)!==id))return;
        const latest=useOperationsStore.getState();
        latest.patch({movements:latest.movements.map(m=>m.simulation_id===updated.simulation_id?{...updated,plan_id:updated.plan_id || id}:m)});
      }
    } catch(error:any) {
      const detail=error?.response?.data?.detail;
      if(useAuthStore.getState().token===ownerToken && useOperationsStore.getState().aiSessionGeneration===generation && (useAppStore.getState().selectedPlan?.plan_id===selectionAtStart || useAppStore.getState().selectedPlan?.plan_id===id))useAppStore.setState({planNotice:typeof detail==='string'?detail:'Plan journey unavailable. Check the routing service and retry.'});
    }
  })().finally(()=>pending.delete(key));
  pending.set(key,task);return task;
}
