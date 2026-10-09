import {useEffect} from 'react';
import {pollMovements} from '../api/operations';
import {useOperationsStore} from '../store/operationsStore';

// Planner journey playback is retained here. This controller is mounted only
// with the Planning map and is never part of the operational workbook workspace.
export function PlanningMovementsController(){
 const enabled=useOperationsStore(s=>s.enabled);
 const viewMode=useOperationsStore(s=>s.viewMode);
 const hasJourneys=useOperationsStore(s=>s.aiSimulationIds.length>0);
 const generation=useOperationsStore(s=>s.aiSessionGeneration);
 useEffect(()=>{
  if(!enabled||viewMode!=='AI'||!hasJourneys)return;
  let cancelled=false;
  let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{
   try{const movements=await pollMovements();if(!cancelled&&useOperationsStore.getState().aiSessionGeneration===generation)useOperationsStore.getState().patch({movements});}
   catch{/* Keep the latest received planner journey if the backend is unavailable. */}
   finally{if(!cancelled)timer=setTimeout(poll,document.hidden?10000:1000);}
  };
  void poll();
  return()=>{cancelled=true;clearTimeout(timer);};
 },[enabled,viewMode,hasJourneys,generation]);
 return null;
}
