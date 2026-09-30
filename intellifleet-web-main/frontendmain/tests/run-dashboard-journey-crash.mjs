import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
const dom=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Element','SVGElement','Node','navigator','localStorage','getComputedStyle'])
  Object.defineProperty(globalThis,key,{value:key==='getComputedStyle'?dom.window.getComputedStyle.bind(dom.window):dom.window[key],configurable:true});
Object.defineProperty(dom.window.HTMLElement.prototype,'clientWidth',{get:()=>1000});
Object.defineProperty(dom.window.HTMLElement.prototype,'clientHeight',{get:()=>700});
let reduced=false,motionListeners=new Set();
window.matchMedia=()=>({get matches(){return reduced;},addEventListener:(_,fn)=>motionListeners.add(fn),removeEventListener:(_,fn)=>motionListeners.delete(fn)});
const L=(await import('leaflet')).default;
let frames=new Map(),frameId=0;
window.requestAnimationFrame=function(fn){if(this!==window)throw new TypeError('Illegal invocation');frames.set(++frameId,fn);return frameId;};
globalThis.requestAnimationFrame=window.requestAnimationFrame;
window.cancelAnimationFrame=function(id){if(this!==window)throw new TypeError('Illegal invocation');frames.delete(id);};
globalThis.cancelAnimationFrame=window.cancelAnimationFrame;
let time=1000;
Object.defineProperty(globalThis.performance,'now',{value:()=>time,configurable:true});
const React=await import('react');
const {render,act,fireEvent,cleanup}=await import('@testing-library/react');
const {MapContainer}=await import('react-leaflet');
L.Browser.svg=true;
const fitCalls=[],panCalls=[],viewCalls=[];
for(const [method,calls] of [['fitBounds',fitCalls],['panTo',panCalls],['setView',viewCalls]]){
  const original=L.Map.prototype[method];L.Map.prototype[method]=function(...args){calls.push(args);return original.apply(this,args);};
}
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
  globalThis.sessionStorage=window.sessionStorage;HTMLElement.prototype.scrollIntoView=()=>{};
  const {within}=await import('@testing-library/react');
  const {useAppStore}=await server.ssrLoadModule('/src/store/appStore.ts');
  const {DashboardPage}=await server.ssrLoadModule('/src/pages/DashboardPage.tsx');
  const start={lat:28.5355,lng:77.271},end={lat:19.1136,lng:72.8697};
  const warehouses=Array.from({length:30},(_,i)=>({warehouse_id:i+1,name:`Hub ${i}`,latitude:20+i/10,longitude:70+i/10}));
  const vehicles=Array.from({length:97},(_,i)=>({id:i+1,label:i===0?'TRK-001':i===1?'TRK-002':`Vehicle ${i+1}`,type:i===2?'plane':'truck',current_position:start,status:'available',is_available:true}));
  const {warehouseApi}=await server.ssrLoadModule('/src/api/warehouse.ts');warehouseApi.getInventory=async()=>({data:{inventory:[]}});
  const {warehousesApi}=await server.ssrLoadModule('/src/api/warehouses.ts');warehousesApi.getWarehouses=async()=>({warehouses});
  const {vehiclesApi}=await server.ssrLoadModule('/src/api/vehicles.ts');vehiclesApi.getVehicles=async()=>({vehicles});
  const {routesApi}=await server.ssrLoadModule('/src/api/routes.ts');routesApi.getRouteSession=async()=>({success:true,data:{routes:Array.from({length:62},(_,i)=>({route_id:i+1,data:{source:'Origin',destination:'Destination',optimal_routes:[{path:[start,end]}]}}))}});
  const {chatApi}=await server.ssrLoadModule('/src/api/chat.ts');chatApi.clearChat=async()=>{};
  const store=useAppStore.getState();store.resetStore();
  const {default:client}=await server.ssrLoadModule('/src/api/client.ts');
  const {fedexApi}=await server.ssrLoadModule('/src/api/fedex.ts');
  const {useOperationsStore}=await server.ssrLoadModule('/src/store/operationsStore.ts');
  const snapshots=new Map();let starts=0;
  client.get=async()=>({data:{movements:[...snapshots.values()]}});
  client.post=async()=>{const p=useAppStore.getState().selectedPlan;starts++;
    const snapshot={simulation_id:p.plan_id,shipment_id:`PLAN-${p.plan_id}`,sequence:0,route_id:p.plan_id,
      route:[[12,25],[12.2,25.1],[13,26],[14,28]],latitude:12,longitude:25,heading:0,mode:'SURFACE',
      origin_station:'Delhi',gateway:'Mumbai',data_source:'SYNTHETIC_NETWORK',location_source:'DEMO_SIMULATION',
      delay_minutes:0,progress:0,paused:true,status:'IN_TRANSIT',simulation_speed:120,
      scheduled_etd:'2026-09-30T01:00:00+05:30',current_eta:'2026-09-30T12:00:00+05:30'};
    snapshots.set(p.plan_id,snapshot);return {data:snapshot};};
  fedexApi.control=async(id)=>({...snapshots.get(id),paused:false});
  const a={id:1,label:'TRK-001',type:'Truck',capacity:12000,assigned_load_kg:11368.42,utilization_percentage:94.74};
  const b={id:2,label:'TRK-002',type:'Truck',capacity:7000,assigned_load_kg:6631.58,utilization_percentage:94.74};
  const base={plan_id:'two',mode:'road',operational_cost:1003345,duration_hours:21.17,risk_score:.1745,reliability:.94,route_legs:[{from_location:'Delhi',to_location:'Mumbai',route_type:'road',source_coords:start,destination_coords:end}],vehicles:[a,b]};
  const ui=render(React.createElement(React.StrictMode,null,React.createElement(DashboardPage)));await act(async()=>{});
  const assign=async plan=>{await act(async()=>store.applyPlanningMapPlan({recommended_plan:plan}));};
  const count=n=>assert.equal(within(ui.getByLabelText('Network metrics')).getByRole('button',{name:/Assigned Vehicles/}).textContent,`Assigned Vehicles${n}`);
  const alive=()=>{assert.ok(ui.getByRole('button',{name:'+ Add Route'}));assert.ok(ui.getByRole('button',{name:'Calculate Plan'}));assert.match(document.body.textContent,/Network Ready/);};
  const advance=async t=>{time=t;await act(async()=>{const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn(t));});};
  await assign({...base,plan_id:'zero',vehicles:[]});count(0);alive();assert.equal(starts,0);
  await assign({...base,plan_id:'one',vehicles:[b]});count(1);assert.equal(starts,1);assert.equal(frames.size,0);
  await assign(base);count(2);alive();assert.equal(starts,2);
  assert.deepEqual(useAppStore.getState().selectedPlan.vehicles,[a,b]);
  for(const value of ['TRK-001','TRK-002','11,368.42','6,631.58'])assert.ok(ui.getByLabelText('Plan Snapshot').textContent.includes(value));
  for(const id of ['third','fourth'])await assign({...base,plan_id:id});
  assert.equal(document.querySelectorAll('.movement-icon').length,4);
  assert.equal(useOperationsStore.getState().aiSimulationIds.length,4);
  assert.equal(starts,4);assert.equal(frames.size,0,'No separate per-plan RAF/SSE replay');
  await assign({...base,plan_id:'one'});assert.equal(starts,4,'Selecting an existing plan never recreates it');
  assert.equal(document.querySelectorAll('.movement-icon').length,4);
  await assign({...base,plan_id:'missing',route_legs:[]});alive();assert.equal(starts,4);
  let copied;Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{copied=value;}},configurable:true});
  await act(async()=>store.addChatMessage('assistant','Exact complete answer'));
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Copy complete assistant response'})));assert.equal(copied,'Exact complete answer');
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Start a new chat'})));count(0);alive();assert.equal(useAppStore.getState().warehouses.length,30);assert.equal(useAppStore.getState().vehicles.length,97);assert.equal(Object.keys(useAppStore.getState().activeRoutes).length,62);
  await act(async()=>{reduced=false;store.applyPlanningMapPlan({recommended_plan:base});});assert.equal(frames.size,0);
  assert.equal(document.querySelectorAll('.movement-icon').length,4,'New Chat retains runtime fleet');
  cleanup();assert.equal(frames.size,0);assert.equal(motionListeners.size,0);
  console.log('PASS: StrictMode dashboard; exact assignments; four persistent Ground markers; no duplicate starts or per-plan animation loops; selection retention; Copy; New Chat preserves network and fleet; cleanup');
}finally{cleanup();await server.close();dom.window.close();}
