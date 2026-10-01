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
 const {useRouteAgent}=await server.ssrLoadModule('/src/hooks/useRouteAgent.ts');
 const {chatApi}=await server.ssrLoadModule('/src/api/chat.ts');
 const {default:api}=await server.ssrLoadModule('/src/api/client.ts');
 const {renderHook}=await import('@testing-library/react');
 const components=[];
 for(const name of ['RoutesLayer','VehiclesLayer','SelectedJourneyLayer','NetworkMovementsLayer','FedExLayer'])components.push((await server.ssrLoadModule(`/src/components/MapLayers/${name}.tsx`))[name]);
 let response,posts=0;
 chatApi.sendMessage=async()=>response;
 api.post=async()=>{posts++;throw new Error('Display/registered revisions must not start simulations or initialize fleet');};
 app.setState({activeRoutes:{},vehicles:[],warehouses:[],selectedPlan:null});
 const fleet={simulation_id:'fleet',shipment_id:'FLEET-1',mode:'SURFACE',route:[[20,70],[21,71]],latitude:20,longitude:70,status:'IN_TRANSIT'};
 ops.setState({enabled:false,viewMode:'OFF',aiSimulationIds:[],movements:[fleet],selected:null});
 const hook=renderHook(()=>useRouteAgent());
 let map;
 const ui=render(React.createElement(React.StrictMode,null,React.createElement(MapContainer,{center:[24,74],zoom:5,ref:m=>{if(m)map=m;}},...components.map((C,i)=>React.createElement(C,{key:i})))));
 const layers=kind=>{const result=[];map.eachLayer(l=>{if(l instanceof kind)result.push(l);});return result;};
 const counts=[];
 const verify=(step,n)=>{
   assert.equal(layers(L.Polyline).length,n,step);assert.equal(layers(L.Marker).length,n,step);
   assert.equal(document.querySelectorAll('.journey-vehicle').length,0);
   assert.equal(ops.getState().viewMode,'AI');assert.equal(posts,0);
   counts.push({step,polylines:layers(L.Polyline).length,markers:layers(L.Marker).length});
 };
 const make=(id,revision,source)=>{
   const route=[[28,77],[id==='a'?24+revision/10:22,75],[13,77]];
   return {recommended_plan:{journey_id:id,plan_id:`${id}-${revision}`,revision,mode:'road',vehicles:[{id:revision,label:`TRK-${revision}`}],route_legs:[{route_id:revision,route_type:'road',from_location:source,to_location:'Bengaluru',source_coords:{lat:28,lng:77},destination_coords:{lat:13,lng:77}}]},
     movement:{journey_id:id,revision,plan_id:`${id}-${revision}`,simulation_id:`sim-${id}`,shipment_id:`PLAN-${id}`,route_id:`geometry-${id}-${revision}`,sequence:revision,route,latitude:28,longitude:77,heading:0,mode:'SURFACE',origin_station:source,gateway:'Bengaluru',status:'IN_TRANSIT',progress:0,paused:false,delay_minutes:0,scheduled_etd:'2026-09-30T00:00:00Z',current_eta:'2026-10-02T00:00:00Z',data_source:'SYNTHETIC_NETWORK',location_source:'DEMO_SIMULATION'}};
 };
 const send=async(message,actions)=>{
   response={success:true,response:'Done',actions};
   await act(async()=>hook.result.current.processMessage(message));
 };
 const plan=async(message,value)=>send(message,[{type:'supply_chain_planning_operation',data:value}]);
 // Retain an earlier independent journey: single mode must hide it, not delete it.
 const {useFedexStore:fedex}=await server.ssrLoadModule('/src/store/fedexStore.ts');
 const b=make('b',1,'Gujarat');await plan('Plan Gujarat to Bengaluru.',b);verify('retained second shipment',1);
 await act(async()=>fedex.setState({telemetry:{...b.movement,simulation_id:'old-fedex'}}));
 verify('unrelated FedEx overlay hidden',1);
 const oldBPath=layers(L.Polyline)[0],oldBMarker=layers(L.Marker)[0];
 let a=make('a',1,'Delhi');await plan('Plan Delhi to Bengaluru.',a);verify('1 initial',1);
 assert.equal(ops.getState().aiDisplayMode,'SINGLE_ROUTE');assert.ok(!map.hasLayer(oldBPath));assert.ok(!map.hasLayer(oldBMarker));
 const path=layers(L.Polyline)[0],marker=layers(L.Marker)[0];
 for(const [revision,prompt] of [[2,'Make the same shipment cheapest.'],[3,'Make the same shipment fastest.']]){
   a=make('a',revision,'Delhi');await plan(prompt,a);verify(`${revision} revision`,1);
   assert.equal(layers(L.Polyline)[0],path);assert.equal(layers(L.Marker)[0],marker);
   assert.equal(path.getLatLngs()[1].lat,24+revision/10);
 }
 a.movement={...a.movement,sequence:4,delay_minutes:30,current_eta:'2026-10-02T00:30:00Z'};
 await send('Delay the same shipment by 30 minutes.',[{type:'movement_updated',data:a.movement}]);verify('4 delay',1);
 await act(async()=>ops.getState().patch({movements:ops.getState().movements.map(m=>m.journey_id==='a'?{...m,progress:.4,latitude:24,longitude:75}:m)}));
 a=make('a',4,'Delhi');await plan('The current route is unavailable. Use another route.',a);verify('5 disruption after progress',1);
 assert.equal(path.getLatLngs()[1].lat,24.4);
 assert.equal(layers(L.Marker)[0],marker);assert.equal(marker.getLatLng().lat,28);
 a=make('a',5,'Delhi');await plan('Use the cheapest alternative route.',a);verify('cheapest alternative',1);
 assert.equal(layers(L.Polyline)[0],path);assert.equal(path.getLatLngs()[1].lat,24.5);
 const display=(mode,values)=>[{type:'set_journey_display',data:{mode,simulation_ids:values.map(v=>v.movement.simulation_id),movements:values.map(v=>v.movement)}}];
 await send('Show multiple routes for comparison: Delhi to Bengaluru and Gujarat to Bengaluru.',display('MULTI_ROUTE',[a,b]));verify('6 explicit multiple',2);
 assert.equal(ops.getState().aiDisplayMode,'MULTI_ROUTE');
 const bPath=layers(L.Polyline).find(p=>p.getLatLngs()[1].lat===22);const bGeometry=bPath.getLatLngs();
 a=make('a',6,'Delhi');await plan('Make Delhi to Bengaluru cheapest.',a);verify('7 revise comparison member',2);
 assert.ok(map.hasLayer(bPath));assert.deepEqual(bPath.getLatLngs(),bGeometry);
 assert.equal(ops.getState().aiDisplayMode,'MULTI_ROUTE');
 await send('Show only the Delhi to Bengaluru route.',display('SINGLE_ROUTE',[a]));verify('explicit single',1);
 assert.ok(!map.hasLayer(bPath));assert.equal(ops.getState().movements.filter(m=>m.journey_id).length,2);
 assert.equal(Object.values(app.getState().activeRoutes).filter(r=>r.routeData?.planning).length,2);
 await send('Keep both routes visible.',display('MULTI_ROUTE',[a,b]));verify('explicit both again',2);
 const c=make('c',1,'Mumbai');await plan('Plan another shipment from Mumbai to Bengaluru.',c);verify('new third journey defaults single',1);
 await send('Show these three routes together.',display('MULTI_ROUTE',[a,b,c]));verify('three specified routes',3);
 for(const message of ['Show route IDs for current shipment.','Show assigned vehicle IDs.','Show active warehouses.','Create a draft fuel what-if scenario.','Compare draft with baseline.','Summarize active shipments.']){
   const paths=layers(L.Polyline),markers=layers(L.Marker),before=ops.getState();
   await send(message,[]);verify(message,3);
   assert.deepEqual(layers(L.Polyline),paths);assert.deepEqual(layers(L.Marker),markers);
   assert.equal(ops.getState(),before,'Read-only chat must not mutate operations/map state');
 }
 await send('Show only Delhi to Bengaluru.',display('SINGLE_ROUTE',[a]));verify('three to one',1);
 await send('Show all three again.',display('MULTI_ROUTE',[a,b,c]));verify('one to three restored',3);
 await act(async()=>fedex.setState({telemetry:null}));
 await act(async()=>hook.result.current.startNewSession());
 assert.equal(ops.getState().aiDisplayMode,'SINGLE_ROUTE');assert.equal(layers(L.Polyline).length,0);assert.equal(layers(L.Marker).length,0);
 assert.equal(ops.getState().movements.filter(m=>m.journey_id).length,3,'New Chat display reset preserves operations state');
 ui.unmount();assert.equal(layers(L.Polyline).length,0);assert.equal(layers(L.Marker).length,0);assert.equal(frames.size,0);
 console.log('PASS: rendered single/multi display acceptance '+JSON.stringify(counts));
} finally {cleanup();await server.close();dom.window.close();}
