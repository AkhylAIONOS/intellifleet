import {create} from 'zustand';
import type {TowerRun} from '../api/controlTower';

// Operational selection is separate from planning candidates and AI visibility.
export const useControlTowerStore=create<{serviceDate:string|null;setServiceDate:(date:string)=>void;selected:TowerRun|null;select:(run:TowerRun|null)=>void}>(set=>({
 serviceDate:null,setServiceDate:serviceDate=>set({serviceDate,selected:null}),selected:null,select:selected=>set({selected})
}));
