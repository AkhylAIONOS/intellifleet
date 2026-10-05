import api from './client';

export interface TowerRun {
 run_id:string;lane_key:string;service_date:string;network_version:string;
 schedule:{origin_city:string;origin_station:string;gateway:string;lane:string;run:string;mode:string;
  service:string;vehicle_count:number|null;cutoff_minutes:number|null;etd_minutes:number|null;
  eta_minutes:number|null;transit_minutes:number|null;source:Record<string,string>;source_formulas?:Record<string,string>;source_value_provenance?:Record<string,string>;warnings:string[];valid:boolean};
 critical:boolean;status:string;planned_etd:string|null;planned_eta:string|null;current_eta:string|null;
 actual_departure_at:string|null;actual_arrival_at:string|null;actual_source:string|null;
 elapsed_hours:number|null;estimated_time_left_hours:number|null;actual_tt_hours:number|null;
 delay_hours:number|null;movement_id:string|null;carrier:string|null;data_source:string;
 location_source:string|null;latest_location:{latitude:number;longitude:number}|null;
 movement?:import('../store/operationsStore').Movement;last_update_at:string;
 events?:Array<{event_id:string;event_type:string;source:string;event_at:string}>;
 cons?:Array<{con_number:string;source:string}>;
}
export interface TowerSummary {total_runs:number;air_runs:number;surface_runs:number;
 statuses:Record<string,number>;critical_lanes:number;critical_lanes_at_risk:number}
export function demoSessionId():string {
 const key='unifleet_demo_session_id';
 let id=localStorage.getItem(key);
 if(!id){id=crypto.randomUUID();localStorage.setItem(key,id);}
 return id;
}
const alertConfig=()=>({headers:{'X-UniFleet-Demo-Session-Id':demoSessionId()}});
export const controlTowerApi={
 importPlan:async(service_date:string)=>(await api.post('/operations/control-tower/import',{service_date})).data,
 runs:async(params:Record<string,unknown>):Promise<{runs:TowerRun[];total:number}>=>(await api.get('/operations/control-tower/runs',{params})).data,
 summary:async(service_date:string):Promise<TowerSummary>=>(await api.get('/operations/control-tower/summary',{params:{service_date}})).data,
 detail:async(id:string):Promise<TowerRun>=>(await api.get(`/operations/control-tower/runs/${encodeURIComponent(id)}`)).data,
 critical:async(id:string,critical:boolean)=>(await api.put(`/operations/critical-lanes/${encodeURIComponent(id)}`,{critical})).data,
 recipients:async():Promise<{emails:string[]}>=>(await api.get('/operations/alerts/recipients',alertConfig())).data,
 saveRecipients:async(emails:string[])=>(await api.put('/operations/alerts/recipients',{emails},alertConfig())).data,
 alerts:async():Promise<{alerts:Array<{id:number;status:string;attempts:number;created_at:string;last_error:string|null}>;delivery_enabled:boolean}>=>(await api.get('/operations/alerts',alertConfig())).data,
 con:async(number:string):Promise<{con:{con_number:string;source:string;event_at:string};run:TowerRun}>=>(await api.get(`/operations/cons/${encodeURIComponent(number)}`)).data,
 syntheticAction:async(id:string,action:'delay10'|'delay30'|'arrive'):Promise<TowerRun>=>(await api.post(`/operations/control-tower/runs/${encodeURIComponent(id)}/synthetic-action`,{action})).data,
 simulate:async(run:TowerRun)=>(await api.post(`/operations/control-tower/runs/${encodeURIComponent(run.run_id)}/simulation`,{
  origin_station:run.schedule.origin_station,gateway:run.schedule.gateway,simulation_date:run.service_date,
  shipment_ready_datetime:`${run.service_date}T00:00:00+05:30`,speed:120,demo_playback:true})).data,
};
