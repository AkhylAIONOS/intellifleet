import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Element','SVGElement','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
Object.defineProperty(HTMLElement.prototype,'clientWidth',{get:()=>900});Object.defineProperty(HTMLElement.prototype,'clientHeight',{get:()=>600});
window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});
const frames=new Map();let frame=0;
window.requestAnimationFrame=fn=>{frames.set(++frame,fn);return frame;};window.cancelAnimationFrame=id=>frames.delete(id);
const L=(await import('leaflet')).default;L.Browser.svg=true;
const React=await import('react');const {render,act,cleanup}=await import('@testing-library/react');const {MapContainer}=await import('react-leaflet');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
 const {useAppStore:app}=await server.ssrLoadModule('/src/store/appStore.ts');
 const {useOperationsStore:ops}=await server.ssrLoadModule('/src/store/operationsStore.ts');
 const components=[];
 for(const name of ['RoutesLayer','VehiclesLayer','SelectedJourneyLayer','NetworkMovementsLayer'])components.push((await server.ssrLoadModule(`/src/components/MapLayers/${name}.tsx`))[name]);
 const {default:api}=await server.ssrLoadModule('/src/api/client.ts');
 const {pollMovements}=await server.ssrLoadModule('/src/api/operations.ts');
 const backend=new Map();let calls=0;
 api.post=async url=>{assert.ok(url.startsWith('/operations/plan-journeys/'),'AI revisions must not initialize Show All');calls++;const plan=app.getState().selectedPlan;return {data:backend.get(plan.journey_id)};};
 app.setState({activeRoutes:{},vehicles:[],warehouses:[],selectedPlan:null});
 const fleet={simulation_id:'fleet',shipment_id:'FLEET-1',mode:'SURFACE',route:[[20,70],[21,71]],latitude:20,longitude:70,status:'IN_TRANSIT'};
 ops.setState({enabled:true,viewMode:'AI',aiSimulationIds:[],movements:[fleet],selected:null});
 let map;
 const ui=render(React.createElement(React.StrictMode,null,React.createElement(MapContainer,{center:[24,74],zoom:5,ref:m=>{if(m)map=m;}},...components.map((C,i)=>React.createElement(C,{key:i})))));
 const layers=kind=>{const result=[];map.eachLayer(l=>{if(l instanceof kind)result.push(l);});return result;};
 const counts=[];
 const verify=n=>{
   const routeCount=Object.values(app.getState().activeRoutes).filter(r=>r.routeData?.planning).length;
   assert.equal(routeCount,n);assert.equal(layers(L.Polyline).length,n);assert.equal(layers(L.Marker).length,n);
   assert.equal(document.querySelectorAll('.journey-vehicle').length,0,'No legacy animation markers remain');
   assert.equal(ops.getState().viewMode,'AI');assert.ok(!ops.getState().aiSimulationIds.includes('fleet'));
   counts.push({routes:routeCount,polylines:layers(L.Polyline).length,markers:layers(L.Marker).length});
 };
 const make=(journey,revision,source='Delhi',vehicle='TRK-001')=>{
   const route=[[28,77],[24+revision/10,75],[13,77]];
   const plan={journey_id:journey,plan_id:`${journey}-revision-${revision}`,revision,mode:'road',vehicles:[{id:revision,label:vehicle}],route_legs:[{route_id:revision,route_type:'road',from_location:source,to_location:'Bengaluru',source_coords:{lat:28,lng:77},destination_coords:{lat:13,lng:77}}]};
   const movement={journey_id:journey,revision,plan_id:plan.plan_id,simulation_id:`movement-${journey}`,shipment_id:`PLAN-${journey}`,route_id:'same-provider-id',sequence:revision===1?100:1,route,latitude:28,longitude:77,heading:0,mode:'SURFACE',service:vehicle,origin_station:source,gateway:'Bengaluru',status:'IN_TRANSIT',progress:0,paused:false,delay_minutes:0,scheduled_etd:'2026-09-30T00:00:00Z',current_eta:'2026-10-02T00:00:00Z',data_source:'SYNTHETIC_NETWORK',location_source:'DEMO_SIMULATION'};
   return {recommended_plan:plan,movement};
 };
 const apply=async result=>{
   backend.set(result.movement.journey_id,result.movement);
   await act(async()=>{
     const state=ops.getState();state.patch({movements:[...state.movements.filter(m=>m.simulation_id!==result.movement.simulation_id),result.movement],aiSimulationIds:[...new Set([...state.aiSimulationIds,result.movement.simulation_id])],selected:result.movement.simulation_id});
     app.getState().applyPlanningMapPlan(result);
   });
   const path=layers(L.Polyline).find(p=>p.getLatLngs()[1]?.lat===result.movement.route[1][0]);
   assert.ok(path,'Current revision coordinates reached a rendered Leaflet polyline');
 };
 await apply(make('a',1));verify(1);let firstPath=layers(L.Polyline)[0],firstMarker=layers(L.Marker)[0];
 const cheapest=make('a',2);delete cheapest.recommended_plan.journey_id;
 await apply(cheapest);verify(1);assert.equal(layers(L.Polyline)[0],firstPath);assert.equal(layers(L.Marker)[0],firstMarker);
 await apply(make('a',3));verify(1);
 const delayed={...backend.get('a'),sequence:2,delay_minutes:30,current_eta:'2026-10-02T00:30:00Z'};backend.set('a',delayed);
 await act(async()=>ops.getState().patch({movements:[fleet,delayed]}));verify(1);
 await apply(make('a',4));verify(1);assert.equal(firstPath.getLatLngs()[1].lat,24.4,'Old geometry replaced');
 await apply(make('a',5,'Delhi','TRK-005'));verify(1);assert.equal(layers(L.Marker)[0],firstMarker,'Vehicle replacement uses one movement marker');
 await apply(make('b',1,'Gujarat'));
 assert.equal(layers(L.Polyline).length,1,'Independent plans do not enable multi display');
 await act(async()=>ops.getState().patch({aiDisplayMode:'MULTI_ROUTE',aiVisibleSimulationIds:['movement-a','movement-b']}));
 firstPath=layers(L.Polyline).find(p=>p.getLatLngs()[1].lat===24.5);
 verify(2);const secondPath=layers(L.Polyline).find(p=>p!==firstPath);const secondCoords=secondPath.getLatLngs();
 await apply(make('a',6));verify(2);assert.ok(layers(L.Polyline).includes(secondPath));assert.deepEqual(secondPath.getLatLngs(),secondCoords,'Unrelated geometry untouched');
 await apply(make('b',2,'Gujarat'));verify(2);
 await apply(make('c',1));
 assert.equal(layers(L.Polyline).length,1,'A new journey outside the comparison is shown alone');
 await act(async()=>ops.getState().patch({aiDisplayMode:'MULTI_ROUTE',aiVisibleSimulationIds:['movement-a','movement-b','movement-c']}));
 verify(3);assert.equal(backend.size,3,'Independent same-OD shipment preserved');
 // Older delayed HTTP/poll responses must not roll back the active revision.
 await act(async()=>ops.getState().patch({movements:[...ops.getState().movements,make('a',2).movement]}));verify(3);
 assert.equal(ops.getState().movements.find(m=>m.journey_id==='a').revision,6);
 // Compact polling must refresh geometry even when the provider route ID is unchanged.
 const newer=make('a',7).movement;let gets=0;
 api.get=async(_url,options)=>{gets++;return {data:{movements:options?.params?.include_geometry===false?[(({route,...facts})=>facts)(newer)]:[newer]}};};
 assert.deepEqual((await pollMovements())[0].route,newer.route);assert.equal(gets,2);
 assert.equal(calls,0,'Already registered results do not create another replay');
 ui.unmount();assert.equal(layers(L.Polyline).length,0);assert.equal(layers(L.Marker).length,0);assert.equal(document.querySelectorAll('.journey-vehicle').length,0);
 assert.equal(frames.size,0,'No stale per-journey animation callback survives replacement/unmount');
 console.log('PASS: rendered journey revision layers '+JSON.stringify(counts));
} finally {cleanup();await server.close();dom.window.close();}
