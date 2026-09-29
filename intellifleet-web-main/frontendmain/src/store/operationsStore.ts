import {create} from 'zustand';
export interface Movement {
  paused?:boolean; stopped?:boolean; alerts?:Array<{impact:string;recommended_action:string;reason:string}>;
  simulation_id:string; shipment_id:string; mode:string; origin_station:string; gateway:string;
  status:string; progress:number|null; latitude:number|null; longitude:number|null; heading:number;
  data_source:string; location_source:string; scheduled_etd:string|number; current_eta:string|number;
  delay_minutes:number; route:[number,number][];
}
export const movementMatches=(m:Movement,filter:string)=>filter==='ALL'||(filter==='FEDEX'?m.data_source==='FEDEX_SOURCE':
  filter==='SYNTHETIC'?m.data_source.startsWith('SYNTHETIC'):filter==='SURFACE'?['SURFACE','ROAD'].includes(m.mode):m.mode===filter);
export const useOperationsStore=create<{enabled:boolean; filter:string; movements:Movement[]; fit:number; selected:string|null;
  patch:(value:Partial<{enabled:boolean;filter:string;movements:Movement[];fit:number;selected:string|null}>)=>void}>(set=>({
    enabled:false,filter:'ALL',movements:[],fit:0,selected:null,patch:value=>set(value),
}));
