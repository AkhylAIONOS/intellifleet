import {create} from 'zustand';

export interface Movement {
  sequence?:number;
  simulation_speed?:number;
  route_id?:string;
  route_source?:string;
  route_distance_km?:number;
  road_estimated_duration_minutes?:number;
  road_routing_status?:string;
  optimization_mode?:string;
  location_notice?:string;
  paused?:boolean;
  stopped?:boolean;
  alerts?:Array<{
    previous_eta?:string;
    revised_eta?:string;
    impact:string;
    recommended_action:string;
    reason:string
  }>;

  simulation_id:string;
  shipment_id:string;
  mode:string;
  origin_station:string;
  gateway:string;
  status:string;
  progress:number|null;
  latitude:number|null;
  longitude:number|null;
  heading:number;
  data_source:string;
  location_source:string;
  scheduled_etd:string|number;
  current_eta:string|number;
  delay_minutes:number;
  route:[number,number][];
}

export type MovementViewMode = 'OFF' | 'AI' | 'LIVE';

export const movementMatches=(m:Movement,filter:string)=>
  filter==='ALL' ||
  (filter==='FEDEX'
    ? m.data_source==='FEDEX_SOURCE'
    : filter==='SYNTHETIC'
      ? m.data_source.startsWith('SYNTHETIC')
      : filter==='SURFACE'
        ? ['SURFACE','ROAD'].includes(m.mode)
        : m.mode===filter);

interface OperationsState {
  enabled:boolean;
  filter:string;
  movements:Movement[];
  fit:number;
  selected:string|null;

  // Controls WHAT the map is allowed to display.
  viewMode:MovementViewMode;

  // Only simulations created from AI planning questions.
  aiSimulationIds:string[];
  aiSessionGeneration:number;

  patch:(value:Partial<Omit<OperationsState,'patch'>>) => void;
}

export const useOperationsStore=create<OperationsState>((set)=>({
  enabled:false,
  filter:'ALL',
  movements:[],
  fit:0,
  selected:null,

  // Normal map starts with no operations overlay.
  viewMode:'OFF',

  // AI journeys are accumulated here for the current frontend session.
  aiSimulationIds:[],
  aiSessionGeneration:0,

  patch:(value)=>set(state=>{
    if(!value.movements)return value;
    const previous=new Map(state.movements.map(m=>[m.simulation_id,m]));
    return {...value,movements:value.movements.map(m=>{
      const old=previous.get(m.simulation_id);
      if(old && old.sequence!=null && m.sequence!=null && old.sequence>m.sequence)return old;
      // Geometry identity changes on reroute; telemetry alone retains the
      // reference so Leaflet does not rebuild every route each second.
      return old && m.route_id && old.route_id===m.route_id ? {...m,route:old.route} : m;
    })};
  }),
}));
