import {create} from 'zustand';
import type {TowerRun} from '../api/controlTower';
interface TowerState {
 chatSessionId:string|null;setChatSessionId:(id:string|null)=>void;
 workspace:string;setWorkspace:(workspace:string)=>void;reset:()=>void;
 serviceDate:string|null;setServiceDate:(date:string)=>void;
 selected:TowerRun|null;selectedRuns:TowerRun[];
 select:(run:TowerRun|null)=>void;toggleSelection:(run:TowerRun)=>void;
 updateSelection:(run:TowerRun)=>void;refreshSelection:(runs:TowerRun[])=>void;
}
// Focused AI entity and selected map subset remain separate from planning state.
export const useControlTowerStore=create<TowerState>(set=>({
 chatSessionId:null,setChatSessionId:chatSessionId=>set({chatSessionId}),
 workspace:'DASHBOARD',setWorkspace:workspace=>set({workspace}),
 reset:()=>set({chatSessionId:null,serviceDate:null,selected:null,selectedRuns:[],workspace:'DASHBOARD'}),
 serviceDate:null,setServiceDate:serviceDate=>set(state=>({serviceDate,
  selected:state.selected?.service_date===serviceDate?state.selected:null,
  selectedRuns:state.selectedRuns.filter(run=>run.service_date===serviceDate)})),
 selected:null,selectedRuns:[],select:selected=>set({selected,selectedRuns:selected?[selected]:[]}),
 toggleSelection:run=>set(state=>{
  const current=state.selectedRuns.length?state.selectedRuns:state.selected?[state.selected]:[];
  const selectedRuns=current.some(r=>r.run_id===run.run_id)?current.filter(r=>r.run_id!==run.run_id):[...current,run];
  return {selectedRuns,selected:selectedRuns.find(r=>r.run_id===run.run_id)||selectedRuns.find(r=>r.run_id===state.selected?.run_id)||selectedRuns.at(-1)||null};
 }),
 updateSelection:run=>set(state=>({selected:state.selected?.run_id===run.run_id?run:state.selected,
  selectedRuns:state.selectedRuns.map(r=>r.run_id===run.run_id?run:r)})),
 refreshSelection:runs=>set(state=>{
  const update=(run:TowerRun)=>{const fresh=runs.find(r=>r.run_id===run.run_id);return fresh?{...run,...fresh}:null;};
  return {selected:state.selected?update(state.selected):null,selectedRuns:state.selectedRuns.map(update).filter((r):r is TowerRun=>r!==null)};
 })
}));
