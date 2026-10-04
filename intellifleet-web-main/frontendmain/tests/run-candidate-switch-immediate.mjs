import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Element','SVGElement','Node','navigator','localStorage','sessionStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
Object.defineProperty(HTMLElement.prototype,'clientWidth',{get:()=>900});Object.defineProperty(HTMLElement.prototype,'clientHeight',{get:()=>600});
const L=(await import('leaflet')).default;L.Browser.svg=true;
const React=await import('react');const {render,act,cleanup}=await import('@testing-library/react');const {MapContainer}=await import('react-leaflet');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {PlanSelectionPreview}=await server.ssrLoadModule('/src/components/MapLayers/PlanSelectionPreview.tsx');
 const {NetworkMovementsLayer}=await server.ssrLoadModule('/src/components/MapLayers/NetworkMovementsLayer.tsx');
 const {useAppStore:app}=await server.ssrLoadModule('/src/store/appStore.ts');
 const {useOperationsStore:ops}=await server.ssrLoadModule('/src/store/operationsStore.ts');
 const {ensurePlanMovement}=await server.ssrLoadModule('/src/utils/planMovement.ts');
 const {default:api}=await server.ssrLoadModule('/src/api/client.ts');
 const pending=new Map();api.post=url=>new Promise(resolve=>pending.set(url.split('/').at(-1),resolve));
 const leg=(id,mode,a,b)=>({route_id:id,from_location:'Hub '+a,to_location:'Hub '+b,route_type:mode,source_coords:{lat:10+a,lng:70+a},destination_coords:{lat:10+b,lng:70+b}});
 const plan=(id,legs)=>({plan_id:id,mode:legs.length>1?'multimodal':'road',vehicles:[{id:1,type:'truck',label:'Test truck'}],route_legs:legs});
 const plans=[plan('A',[leg(1,'road',0,1)]),plan('B',[leg(2,'road',1,2),leg(3,'air',2,3),leg(4,'road',3,4)]),plan('C',[leg(5,'road',4,5)])];
 const movement=(id,route)=>({simulation_id:'m'+id,plan_id:id,shipment_id:'PLAN-'+id,mode:'SURFACE',origin_station:'Hub',gateway:'Hub',route,latitude:route[0][0],longitude:route[0][1],heading:0,status:'IN_TRANSIT',progress:0,paused:false,stopped:false,data_source:'SYNTHETIC_NETWORK'});
 ops.setState({enabled:true,viewMode:'AI',filter:'ALL',aiSimulationIds:['mZ'],selected:'mZ',movements:[movement('Z',[[9,69],[10,70]])]});
 let map;render(React.createElement(MapContainer,{center:[20,75],zoom:5,ref:m=>{if(m)map=m;}},React.createElement(PlanSelectionPreview),React.createElement(NetworkMovementsLayer)));
 const layers=type=>{const result=[];map.eachLayer(l=>{if(l instanceof type)result.push(l);});return result;};
 map.panTo([19,74],{animate:false});const center=map.getCenter();
 const tasks=[];
 for(const p of plans){
  await act(async()=>{app.getState().applyPlanningMapPlan({recommended_plan:p});tasks.push(ensurePlanMovement(p));});
  assert.equal(layers(L.Polyline).length,p.route_legs.length,'selected geometry renders before HTTP resolves');
  assert.equal(layers(L.Marker).length,0,'old carrier disappears while replay initializes');
  assert.ok(map.getCenter().equals(center),'candidate selection does not move manual camera');
 }
 await act(async()=>{pending.get('C')({data:movement('C',[[14,74],[15,75]])});await tasks[2];});
 assert.equal(layers(L.Marker).length,1);assert.equal(layers(L.Polyline).length,1);
 await act(async()=>{pending.get('A')({data:movement('A',[[10,70],[11,71]])});pending.get('B')({data:movement('B',[[11,71],[14,74]])});await Promise.all(tasks);});
 assert.equal(ops.getState().selected,'mC');assert.equal(app.getState().selectedPlan.plan_id,'C');
 assert.equal(layers(L.Marker).length,1);assert.equal(layers(L.Polyline).length,1);
 console.log('PASS: immediate Road → Multimodal → Road geometry before replay HTTP; old carriers removed; late A/B responses ignored; one C carrier; manual camera preserved');
}finally{cleanup();await server.close();dom.window.close();}
