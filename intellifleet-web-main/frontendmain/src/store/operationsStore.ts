import {create} from 'zustand';

export interface Movement {
  business_status?:string;
  baseline_sla_met?:boolean|null;
  current_sla_met?:boolean|null;
  telemetry_source?:string;
  sequence?:number;
  journey_id?:string;
  plan_id?:string;
  revision?:number;
  active_leg_index?:number;
  current_segment?:number;
  segment_progress?:number;
  active_vehicles?:Array<{id:number|string;label?:string;type?:string}>;
  journey_segments?:Array<{start_index:number;end_index:number;mode:string;route_id?:number;
    start_progress?:number;end_progress?:number;duration_hours?:number;
    from_location?:string;to_location?:string;vehicles?:Array<{id:number|string;label?:string;type?:string}>}>;
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

// Revisions share a logical key; independent same-OD shipments never do.
export const movementIdentity=(m:Movement)=>m.journey_id ? `journey:${m.journey_id}` :
  m.shipment_id?.startsWith('PLAN-') ? `journey:${m.shipment_id.slice(5)}` : `movement:${m.simulation_id}`;

export type JourneyDisplayMode = 'SINGLE_ROUTE' | 'MULTI_ROUTE';

export type MovementViewMode = 'OFF' | 'AI' | 'LIVE';

export const movementMatches=(m:Movement,filter:string)=>
  filter==='ALL' ||
  (filter==='FEDEX'
    ? m.data_source==='FEDEX_SOURCE'
    : filter==='SYNTHETIC'
      ? m.data_source.startsWith('SYNTHETIC')
      : filter==='SURFACE'
        ? ['SURFACE','ROAD'].includes(m.mode) || !!m.journey_segments?.some(s=>['SURFACE','ROAD'].includes(s.mode))
        : m.mode===filter || !!m.journey_segments?.some(s=>s.mode===filter));

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
  aiDisplayMode:JourneyDisplayMode;
  pendingPlanId?:string|null;
  aiVisibleSimulationIds:string[];

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
  aiDisplayMode:'SINGLE_ROUTE',
  aiVisibleSimulationIds:[],

  patch:(value)=>set(state=>{
    // Clearing a chat/session always restores the default display mode.
    if(value.aiSimulationIds?.length===0)value={...value,aiDisplayMode:'SINGLE_ROUTE',aiVisibleSimulationIds:[]};
    if(value.viewMode==='AI' && value.selected && !value.aiDisplayMode && state.aiDisplayMode==='MULTI_ROUTE'
       && !state.aiVisibleSimulationIds.includes(value.selected))value={...value,aiDisplayMode:'SINGLE_ROUTE',aiVisibleSimulationIds:[]};
    if(!value.movements)return value;
    const previous=new Map(state.movements.map(m=>[movementIdentity(m),m]));
    const next=new Map<string,Movement>();
    for(const received of value.movements){
      const key=movementIdentity(received), old=next.get(key) || previous.get(key);
      // Legacy telemetry may omit the plan ID. Preserve a known binding only
      // for the exact same movement, shipment and revision.
      const m=old && received.plan_id==null && received.simulation_id===old.simulation_id
        && received.shipment_id===old.shipment_id && received.revision===old.revision
        ? {...received,plan_id:old.plan_id} : received;
      const olderRevision=old && (old.revision || 0)>(m.revision || 0);
      const sameRevision=old && old.revision===m.revision && old.plan_id===m.plan_id;
      if(old && (olderRevision || (sameRevision && old.sequence!=null && m.sequence!=null && old.sequence>m.sequence))){next.set(key,old);continue;}
      // Sequence numbers may restart on a revision. Reuse geometry only for
      // the same revision, never discard a newer plan because of an old counter.
      next.set(key,old && sameRevision && m.route_id && old.route_id===m.route_id ? {...m,route:old.route} : m);
    }
    const replacements=new Map<string,string>();
    for(const [key,m] of next){const old=previous.get(key);if(old)replacements.set(old.simulation_id,m.simulation_id);}
    const selected=value.selected===undefined?state.selected:value.selected;
    return {...value,movements:[...next.values()],
      selected:selected ? replacements.get(selected) || selected : selected,
      aiVisibleSimulationIds:(value.aiVisibleSimulationIds || state.aiVisibleSimulationIds).map(id=>replacements.get(id)||id),
      aiSimulationIds:[...new Set((value.aiSimulationIds || state.aiSimulationIds).map(id=>replacements.get(id)||id))]};
  }),
}));

// Retained session journeys are history, not an instruction to show every route.
export function visibleAiMovement(m:Movement, state:Pick<OperationsState,'aiSimulationIds'|'aiDisplayMode'|'aiVisibleSimulationIds'|'selected'>):boolean {
  if(!state.aiSimulationIds.includes(m.simulation_id))return false;
  if(state.aiDisplayMode==='MULTI_ROUTE')return state.aiVisibleSimulationIds.includes(m.simulation_id);
  const selected=state.selected && state.aiSimulationIds.includes(state.selected) ? state.selected : state.aiSimulationIds.at(-1);
  return m.simulation_id===selected;
}

// Carrier comes from the active leg, never from the overall multimodal service.
export function activeCarrier(m:Movement) {
  const segments=m.journey_segments || [];
  const segment=(m.active_leg_index!=null ? segments[m.active_leg_index] : undefined)
    || segments.find(s=>s.end_progress!=null && (m.progress || 0)<s.end_progress)
    || segments.find(s=>m.current_segment!=null && s.start_index<=m.current_segment && m.current_segment<s.end_index);
  return {mode:segment?.mode || m.mode, vehicles:segment?.vehicles || m.active_vehicles || []};
}
