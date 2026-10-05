import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const React=await import('react');
const {render,act,fireEvent,cleanup}=await import('@testing-library/react');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {controlTowerApi:api}=await server.ssrLoadModule('/src/api/controlTower.ts');
 const {ControlTower}=await server.ssrLoadModule('/src/components/ControlTower.tsx');
 let run={run_id:'demo-run',lane_key:'lane',service_date:'2030-01-01',schedule:{origin_city:'Udaipur',origin_station:'UDRPU',gateway:'DELGW',lane:'UDR-DEL',run:'1',mode:'SURFACE',source:{},warnings:[],valid:true,service:'Carrier',cutoff_minutes:10,etd_minutes:20,eta_minutes:200},status:'SCHEDULED',critical:true,actual_source:null,location_source:null,events:[],cons:[],planned_etd:'2030-01-01T01:00:00+05:30',planned_eta:'2030-01-01T04:00:00+05:30'};
 let refreshes=0;
 api.runs=async()=>{refreshes++;return {runs:[run],total:1};};
 api.summary=async()=>({total_runs:38,air_runs:10,surface_runs:28,statuses:{[run.status]:1},critical_lanes:1,critical_lanes_at_risk:['EXPECTED DELAY','DELAYED'].includes(run.status)?1:0});
 api.recipients=async()=>({emails:[]});api.detail=async()=>run;
 api.simulate=async()=>{run={...run,status:'ON TIME',movement_id:'demo-movement',actual_source:'SYNTHETIC_TELEMETRY',location_source:'SYNTHETIC_TELEMETRY',actual_departure_at:run.planned_etd,cons:[{con_number:'CT-SYNTHETIC-demo-run',source:'SYNTHETIC_TELEMETRY'}]};return run;};
 const actions=[];
 api.syntheticAction=async(id,action)=>{assert.equal(id,'demo-run');actions.push(action);run={...run,status:{delay10:'EXPECTED DELAY',delay30:'DELAYED',arrive:'ARRIVED'}[action]};return run;};
 const ui=render(React.createElement(ControlTower));
 await act(async()=>{});
 await act(async()=>fireEvent.click(ui.getByRole('button',{name:'UDR-DEL'})));
 await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Start labelled synthetic playback'})));
 assert.ok(ui.getAllByText(/ON TIME/).length);assert.ok(ui.getByText(/CT-SYNTHETIC-demo-run/));
 for(const [name,status] of [['Synthetic +10 min delay','EXPECTED DELAY'],['Synthetic +30 min delay and advance clock','DELAYED'],['Complete synthetic arrival','ARRIVED']]){
  const before=refreshes;
  await act(async()=>fireEvent.click(ui.getByRole('button',{name})));
  assert.ok(ui.getAllByText(new RegExp(status)).length);assert.ok(refreshes>before,'refresh table and summary after each transition');
 }
 assert.deepEqual(actions,['delay10','delay30','arrive']);
 assert.equal(ui.queryByRole('button',{name:'Complete synthetic arrival'}),null);
 assert.equal(run.planned_eta,'2030-01-01T04:00:00+05:30');
 console.log('PASS: selected-run synthetic controls, state rendering, immediate refresh, CON provenance, completed-run controls hidden');
}finally{cleanup();await server.close();dom.window.close();}
