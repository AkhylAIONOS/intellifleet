import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Element','SVGElement','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
Object.defineProperty(HTMLElement.prototype,'clientWidth',{get:()=>900});Object.defineProperty(HTMLElement.prototype,'clientHeight',{get:()=>600});
const L=(await import('leaflet')).default;L.Browser.svg=true;
const React=await import('react');const {render,act,cleanup}=await import('@testing-library/react');const {MapContainer}=await import('react-leaflet');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {NetworkMovementsLayer}=await server.ssrLoadModule('/src/components/MapLayers/NetworkMovementsLayer.tsx');
 const {ControlTowerLayer}=await server.ssrLoadModule('/src/components/MapLayers/ControlTowerLayer.tsx');
 const {useControlTowerStore:tower}=await server.ssrLoadModule('/src/store/controlTowerStore.ts');
 const {useOperationsStore,movementMatches}=await server.ssrLoadModule('/src/store/operationsStore.ts');
 const {useFedexStore}=await server.ssrLoadModule('/src/store/fedexStore.ts');
 let map,fits=0;const original=L.Map.prototype.fitBounds;L.Map.prototype.fitBounds=function(...args){fits++;return original.apply(this,args);};
 render(React.createElement(MapContainer,{center:[24,74],zoom:5,ref:m=>{if(m)map=m;}},React.createElement(NetworkMovementsLayer),React.createElement(ControlTowerLayer)));
 const movements=Array.from({length:100},(_,i)=>({simulation_id:`m${i}`,shipment_id:`SHIP-${i}`,mode:['SURFACE','AIR','RAIL'][i%3],origin_station:'Kochi',gateway:'Chennai',route:[[10,76],[11,77],[13,80]],latitude:10+i*.1,longitude:76,heading:30,progress:.3,status:'IN_TRANSIT',data_source:i%2?'FEDEX_SOURCE':'SYNTHETIC_NETWORK',location_source:'DEMO_SIMULATION',scheduled_etd:'2026-09-29T18:00',current_eta:'2026-09-30T08:00',delay_minutes:30}));
 const paths=()=>{const result=[];map.eachLayer(l=>{if(l instanceof L.Polyline)result.push(l);});return result;};
 const markers=()=>{const result=[];map.eachLayer(l=>{if(l instanceof L.Marker)result.push(l);});return result;};
 await act(async()=>useOperationsStore.getState().patch({enabled:true,viewMode:'LIVE',movements}));
 assert.equal(markers().length,100);assert.equal(paths().length,100);assert.equal(fits,0);
 for(const marker of markers().slice(0,4)){
  await act(async()=>marker.fire('click'));
  assert.equal(markers().length,100);assert.equal(paths().length,100);
  assert.equal(useOperationsStore.getState().movements.length,100);
 }
 for(const type of ['truck','plane','train'])assert.ok(markers().some(m=>m.options.icon.options.html.includes(`aria-label="${type}"`)));
 await act(async()=>markers()[0].openTooltip());
 for(const value of ['SHIP-0','Kochi','Chennai','IN_TRANSIT','30.0%','ETA','Delay 30','SYNTHETIC_NETWORK','DEMO_SIMULATION'])assert.ok(document.body.textContent.includes(value),value);
 map.panTo([20,75],{animate:false});const center=map.getCenter();
 await act(async()=>useOperationsStore.getState().patch({movements:movements.map(m=>({...m,latitude:m.latitude+.1,progress:.4}))}));
 assert.equal(fits,0);assert.ok(map.getCenter().equals(center));assert.equal(markers()[0].getLatLng().lat,10.1);
 for(const filter of ['AIR','RAIL','SURFACE','FEDEX','SYNTHETIC']){
  await act(async()=>useOperationsStore.getState().patch({filter}));assert.equal(markers().length,movements.filter(m=>movementMatches(m,filter)).length);
 }
 await act(async()=>useOperationsStore.getState().patch({filter:'ALL',selected:'m0'}));assert.equal(fits,0);assert.ok(map.getCenter().equals(center));
 await act(async()=>useOperationsStore.getState().patch({fit:1}));assert.equal(fits,1,'Fit network explicitly fits');
 const {LiveOperations}=await server.ssrLoadModule('/src/components/LiveOperations.tsx');
 const {default:api}=await server.ssrLoadModule('/src/api/client.ts');
 let backendMovements=useOperationsStore.getState().movements,created=0,posts=0,gets=0;
 api.get=async()=>{gets++;return {data:{movements:backendMovements}};};
 api.post=async(path,body)=>{
  assert.equal(path,'/operations/movements/initialize');assert.equal(body,undefined);posts++;
  if(!backendMovements.some(m=>!m.shipment_id.startsWith('PLAN-'))){created++;backendMovements=[...backendMovements,...movements];}
  return {data:{movements:backendMovements}};
 };
 const controls=render(React.createElement(LiveOperations));
 const beforeShowAll=map.getCenter(),zoomBefore=map.getZoom(),fitsBefore=fits;
 await act(async()=>controls.getByRole('button',{name:'HIDE ALL MOVEMENTS'}).click());
 await act(async()=>controls.getByRole('button',{name:'SHOW ALL MOVEMENTS'}).click());
 assert.equal(fits,fitsBefore);assert.equal(map.getZoom(),zoomBefore);assert.ok(map.getCenter().equals(beforeShowAll));
 assert.equal(created,0);assert.equal(posts,1);
 const beforeFollow=map.getCenter();document.querySelector('.journey-controls button').click();
 assert.equal(map.getZoom(),11);assert.ok(!map.getCenter().equals(beforeFollow));
 map.getContainer().dispatchEvent(new window.Event('pointerdown'));map.panTo([19,72],{animate:false});const manual=map.getCenter();
 await act(async()=>useOperationsStore.getState().patch({movements:movements.map(m=>({...m,latitude:m.latitude+.2}))}));assert.ok(map.getCenter().equals(manual));
 let path;map.eachLayer(l=>{if(l instanceof L.Polyline)path=l;});assert.equal(path.getLatLngs().length,3);
 // A fresh fleet with one retained AI journey must initialize wider operations once.
 const ai={...movements[0],simulation_id:'ai-only',shipment_id:'PLAN-only'};
 backendMovements=[ai];
 await act(async()=>useOperationsStore.getState().patch({enabled:true,viewMode:'AI',filter:'ALL',aiSimulationIds:['ai-only'],movements:[ai]}));
 assert.equal(markers().length,1);
 await act(async()=>controls.getByRole('button',{name:'SHOW ALL MOVEMENTS'}).click());
 assert.equal(created,1);assert.equal(markers().length,101);assert.equal(paths().length,101);
 for(const filter of ['ALL','SURFACE','AIR','RAIL']){
  await act(async()=>useOperationsStore.getState().patch({filter}));
  assert.equal(markers().length,backendMovements.filter(m=>movementMatches(m,filter)).length);
 }
 await act(async()=>useOperationsStore.getState().patch({filter:'ALL'}));
 await act(async()=>controls.getByRole('button',{name:'HIDE ALL MOVEMENTS'}).click());
 assert.equal(markers().length,1);assert.equal(useOperationsStore.getState().viewMode,'AI');assert.equal(backendMovements.length,101);
 await act(async()=>controls.getByRole('button',{name:'SHOW ALL MOVEMENTS'}).click());
 assert.equal(created,1);assert.equal(markers().length,101);assert.ok(gets<10,'bounded polling during toggles');
 const {pollMovements}=await server.ssrLoadModule('/src/api/operations.ts');
 const pollOptions=[];
 api.get=async(path,options)=>{pollOptions.push(options);return {data:{movements:backendMovements.map(({route,...m})=>m)}};};
 for(let i=0;i<3;i++){
  const compact=await pollMovements();assert.deepEqual(compact.map(m=>m.route),backendMovements.map(m=>m.route));
 }
 assert.equal(pollOptions.length,3);assert.ok(pollOptions.every(o=>o?.params?.include_geometry===false));
 api.get=async()=>({data:{movements:backendMovements}});
 const preserved=backendMovements.map(m=>m.simulation_id);
 await act(async()=>useOperationsStore.getState().patch({enabled:false,viewMode:'AI',aiSimulationIds:[],selected:null}));
 assert.equal(markers().length,0);
 await act(async()=>controls.getByRole('button',{name:'SHOW ALL MOVEMENTS'}).click());
 assert.equal(markers().length,101);assert.deepEqual(useOperationsStore.getState().aiSimulationIds,[]);
 await act(async()=>controls.getByRole('button',{name:'HIDE ALL MOVEMENTS'}).click());assert.equal(markers().length,0);
 assert.deepEqual(backendMovements.map(m=>m.simulation_id),preserved);
 backendMovements=movements;
 await act(async()=>useOperationsStore.getState().patch({enabled:true,viewMode:'LIVE',movements,aiSimulationIds:[]}));
 await act(async()=>useFedexStore.getState().begin({...movements[0],sequence:1}));assert.equal(markers().length,99);
 await act(async()=>useOperationsStore.getState().patch({enabled:false}));assert.equal(markers().length,0);
 await act(async()=>useFedexStore.getState().reset());
 await act(async()=>useOperationsStore.getState().patch({enabled:true,viewMode:'LIVE',filter:'ALL',selected:'m1',movements}));
 const run={run_id:'tower-air',movement_id:'m1',critical:true,status:'DELAYED',schedule:{mode:'AIR',lane:'Test lane',service:'Test carrier'},latest_location:null,location_source:'SYNTHETIC_TELEMETRY'};
 await act(async()=>tower.getState().select(run));
 assert.equal(markers().length,1,'one selected operational aircraft');assert.equal(paths().length,1);
 assert.equal(paths()[0].options.color,'#b42318','delayed route emphasis');
 await act(async()=>tower.getState().select({...run,status:'ON TIME'}));
 assert.equal(paths()[0].options.color,'#9a6700','critical route emphasis');
 map.panTo([18,73],{animate:false});const towerCenter=map.getCenter(),towerFits=fits;
 await act(async()=>useOperationsStore.getState().patch({movements:movements.map(m=>({...m,latitude:m.latitude+.01}))}));
 assert.ok(map.getCenter().equals(towerCenter));assert.equal(fits,towerFits);
 await act(async()=>tower.getState().select({...run,run_id:'unlinked',movement_id:null}));
 assert.equal(markers().length,0,'unlinked run hides unrelated aircraft');
 const location={...run,run_id:'scan-test',movement_id:null,latest_location:{latitude:12,longitude:72},current_eta:'2030-01-01T12:00:00Z',last_update_at:'2030-01-01T10:00:00Z'};
 await act(async()=>tower.getState().select(location));
 assert.equal(markers().length,1,'one labelled test location marker');
 assert.equal(paths().length,0,'location facts never invent geometry');
 await act(async()=>markers()[0].openTooltip());
 assert.ok(document.body.textContent.includes('SYNTHETIC_TELEMETRY'));
 map.panTo([16,75],{animate:false});const scanCenter=map.getCenter();
 await act(async()=>tower.getState().select({...location,latest_location:{latitude:12.1,longitude:72}}));
 assert.ok(map.getCenter().equals(scanCenter),'location updates preserve manual pan');
 await act(async()=>controls.getByRole('button',{name:'HIDE ALL MOVEMENTS'}).click());
 await act(async()=>controls.getByRole('button',{name:'SHOW ALL MOVEMENTS'}).click());
 assert.equal(tower.getState().selected,null);assert.equal(markers().length,100,'Show All clears operational focus without duplication');
 console.log('PASS: 100 Leaflet entities; truck/plane/train icons; hover fields; filters; batched movement; pan preserved; arbitrary 3-node path; selected run deduplication; show-all off');
}finally{cleanup();await server.close();dom.window.close();}
