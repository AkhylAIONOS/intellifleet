import api from './client';
import {useOperationsStore,type Movement} from '../store/operationsStore';

// Poll facts only. Fetch geometry on first sight or a changed road route.
export async function pollMovements():Promise<Movement[]> {
  const {data}=await api.get('/operations/movements',{params:{include_geometry:false}});
  const previous=new Map(useOperationsStore.getState().movements.map(m=>[m.simulation_id,m]));
  if(data.movements.some((m:Movement)=>!previous.has(m.simulation_id)||previous.get(m.simulation_id)?.route_id!==m.route_id||previous.get(m.simulation_id)?.plan_id!==m.plan_id||previous.get(m.simulation_id)?.revision!==m.revision)){
    return (await api.get('/operations/movements')).data.movements;
  }
  return data.movements.map((m:Movement)=>({...m,route:previous.get(m.simulation_id)!.route}));
}
