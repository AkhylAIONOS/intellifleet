import {create} from 'zustand';
import type {TowerRun} from '../api/controlTower';

// Operational selection is separate from planning candidates and AI visibility.
export const useControlTowerStore=create<{chatSessionId:string|null;setChatSessionId:(id:string|null)=>void;workspace:string;setWorkspace:(workspace:string)=>void;reset:()=>void;serviceDate:string|null;setServiceDate:(date:string)=>void;selected:TowerRun|null;select:(run:TowerRun|null)=>void}>(set=>({
 chatSessionId:null,setChatSessionId:chatSessionId=>set({chatSessionId}),workspace:'DASHBOARD',setWorkspace:workspace=>set({workspace}),reset:()=>set({chatSessionId:null,serviceDate:null,selected:null,workspace:'DASHBOARD'}),serviceDate:null,setServiceDate:serviceDate=>set(state=>({serviceDate,selected:state.selected?.service_date===serviceDate?state.selected:null})),selected:null,select:selected=>set({selected})
}));
