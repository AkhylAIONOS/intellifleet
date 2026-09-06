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
  const a={id:1,label:'TRK-001',type:'Truck',capacity:12000,assigned_load_kg:11368.42,utilization_percentage:94.74};
  const b={id:2,label:'TRK-002',type:'Truck',capacity:7000,assigned_load_kg:6631.58,utilization_percentage:94.74};
  const base={plan_id:'two',mode:'road',operational_cost:1003345,duration_hours:21.17,risk_score:.1745,reliability:.94,route_legs:[{from_location:'Delhi',to_location:'Mumbai',route_type:'road',source_coords:start,destination_coords:end}],vehicles:[a,b]};
  const ui=render(React.createElement(React.StrictMode,null,React.createElement(DashboardPage)));await act(async()=>{});
  const assign=async plan=>{await act(async()=>store.applyPlanningMapPlan({recommended_plan:plan}));};
  const count=n=>assert.equal(within(ui.getByLabelText('Network metrics')).getByRole('button',{name:/Assigned Vehicles/}).textContent,`Assigned Vehicles${n}`);
  const alive=()=>{assert.ok(ui.getByRole('button',{name:'+ Add Route'}));assert.ok(ui.getByRole('button',{name:'Calculate Plan'}));assert.match(document.body.textContent,/Network Ready/);};
  const advance=async t=>{time=t;await act(async()=>{const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn(t));});};
  await assign({...base,plan_id:'zero',vehicles:[]});count(0);alive();assert.equal(frames.size,0);
  await assign({...base,plan_id:'one',vehicles:[b]});count(1);assert.equal(frames.size,1);
  await assign({...base,plan_id:'air',mode:'air',vehicles:[{id:3,label:'AIR-1',type:'plane'}],route_legs:base.route_legs.map(l=>({...l,route_type:'air'}))});count(1);assert.equal(frames.size,1);
  await assign(base);count(2);alive();assert.equal(frames.size,1);
  assert.deepEqual(useAppStore.getState().selectedPlan.vehicles,[a,b]);assert.equal(a.assigned_load_kg+b.assigned_load_kg,18000);
  for(const value of ['TRK-001','TRK-002','11,368.42','6,631.58'])assert.match(ui.getByLabelText('Plan Snapshot').textContent,new RegExp(value.replaceAll('.','\\.')));
  assert.match(document.querySelector('.journey-vehicle').textContent,/2/);
  await advance(1000);await advance(6000);await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Replay Journey'})));assert.equal(frames.size,1);
  await assign({...base,plan_id:'optional',vehicles:[{id:1,assigned_load_kg:11368.42},{id:2,assigned_load_kg:6631.58}]});count(2);alive();
  for (const legs of [null,[],[null],[{source_coords:{lat:NaN,lng:0},destination_coords:end}]]) {
    await assign({...base,plan_id:`missing-${Math.random()}`,route_legs:legs});count(2);alive();assert.equal(frames.size,0);assert.ok(ui.getByLabelText('Plan Snapshot'));
  }
  await assign({...base,plan_id:'null-vehicles',vehicles:null});count(0);alive();
  await assign({...base,plan_id:'null-row',vehicles:[null,a,undefined,b]});count(2);alive();
  await assign({...base,plan_id:'road-again',vehicles:[b]});await assign({...base,plan_id:'ground-to-two'});count(2);assert.equal(frames.size,1);
  // Contain a real Leaflet effect failure; keep the whole dashboard usable.
  const originalMarker=L.marker,originalError=console.error;const errors=[];
  console.error=(...args)=>errors.push(args);
  try {
    L.marker=()=>{throw new Error('Injected journey failure');};
    await assign({...base,plan_id:'failed-plan'});
    alive();count(2);assert.match(document.body.textContent,/Journey visualization unavailable for this plan/);assert.ok(ui.getByLabelText('Plan Snapshot'));assert.equal(frames.size,0);assert.ok(errors.length);
  } finally {L.marker=originalMarker;console.error=originalError;}
  await assign({...base,plan_id:'recovered'});assert.doesNotMatch(document.body.textContent,/Journey visualization unavailable/);assert.equal(frames.size,1);
  const originalPosition=L.Marker.prototype.setLatLng;
  console.error=(...args)=>errors.push(args);
  try {
    L.Marker.prototype.setLatLng=function(point){if(this.options.icon.options.className==='journey-vehicle')throw new Error('Injected frame failure');return originalPosition.call(this,point);};
    await advance(7000);alive();count(2);assert.match(document.body.textContent,/Journey visualization unavailable/);assert.equal(frames.size,0);
  }finally{L.Marker.prototype.setLatLng=originalPosition;console.error=originalError;}
  await assign({...base,plan_id:'frame-recovered'});assert.equal(frames.size,1);
  await act(async()=>{reduced=true;motionListeners.forEach(fn=>fn());});assert.equal(frames.size,0);alive();
  let copied;Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{copied=value;}},configurable:true});
  await act(async()=>store.addChatMessage('assistant','Exact complete answer'));
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Copy complete assistant response'})));assert.equal(copied,'Exact complete answer');
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Start a new chat'})));count(0);alive();assert.equal(useAppStore.getState().warehouses.length,30);assert.equal(useAppStore.getState().vehicles.length,97);assert.equal(Object.keys(useAppStore.getState().activeRoutes).length,62);
  await act(async()=>{reduced=false;store.applyPlanningMapPlan({recommended_plan:base});});assert.equal(frames.size,1);
  cleanup();assert.equal(frames.size,0);assert.equal(motionListeners.size,0);
  console.log('PASS: full StrictMode dashboard, 30/97/62 network, exact 18000kg assignments, 0/1/2+, missing metadata/geometry, Road/Air/multi replacement, receiver-aware RAF, replay, error containment/recovery, reduced motion, Copy/New Chat and active unmount');
}finally{cleanup();await server.close();dom.window.close();}
