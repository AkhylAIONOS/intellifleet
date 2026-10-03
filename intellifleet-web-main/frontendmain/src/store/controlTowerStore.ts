import {create} from 'zustand';
import type {TowerRun} from '../api/controlTower';

// Operational selection is separate from planning candidates and AI visibility.
export const useControlTowerStore=create<{selected:TowerRun|null;select:(run:TowerRun|null)=>void}>(set=>({
 selected:null,select:selected=>set({selected})
}));
