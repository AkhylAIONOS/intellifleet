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
 const {useOperationsStore,movementMatches}=await server.ssrLoadModule('/src/store/operationsStore.ts');
 const {useFedexStore}=await server.ssrLoadModule('/src/store/fedexStore.ts');
 let map,fits=0;const original=L.Map.prototype.fitBounds;L.Map.prototype.fitBounds=function(...args){fits++;return original.apply(this,args);};
 render(React.createElement(MapContainer,{center:[24,74],zoom:5,ref:m=>{if(m)map=m;}},React.createElement(NetworkMovementsLayer)));
 const movements=Array.from({length:100},(_,i)=>({simulation_id:`m${i}`,shipment_id:`SHIP-${i}`,mode:['SURFACE','AIR','RAIL'][i%3],origin_station:'Kochi',gateway:'Chennai',route:[[10,76],[11,77],[13,80]],latitude:10+i*.1,longitude:76,heading:30,progress:.3,status:'IN_TRANSIT',data_source:i%2?'FEDEX_SOURCE':'SYNTHETIC_NETWORK',location_source:'DEMO_SIMULATION',scheduled_etd:'2026-09-29T18:00',current_eta:'2026-09-30T08:00',delay_minutes:30}));
 const paths=()=>{const result=[];map.eachLayer(l=>{if(l instanceof L.Polyline)result.push(l);});return result;};
 const markers=()=>{const result=[];map.eachLayer(l=>{if(l instanceof L.Marker)result.push(l);});return result;};
 await act(async()=>useOperationsStore.getState().patch({enabled:true,viewMode:'LIVE',movements}));
 assert.equal(markers().length,100);assert.equal(paths().length,100);assert.equal(fits,0);
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
 api.get=async()=>({data:{movements:useOperationsStore.getState().movements}});
 const controls=render(React.createElement(LiveOperations));
 const beforeShowAll=map.getCenter(),zoomBefore=map.getZoom(),fitsBefore=fits;
 await act(async()=>controls.getByRole('button',{name:'HIDE ALL MOVEMENTS'}).click());
 await act(async()=>controls.getByRole('button',{name:'SHOW ALL MOVEMENTS'}).click());
 assert.equal(fits,fitsBefore);assert.equal(map.getZoom(),zoomBefore);assert.ok(map.getCenter().equals(beforeShowAll));
 const beforeFollow=map.getCenter();document.querySelector('.journey-controls button').click();
 assert.equal(map.getZoom(),11);assert.ok(!map.getCenter().equals(beforeFollow));
 map.getContainer().dispatchEvent(new window.Event('pointerdown'));map.panTo([19,72],{animate:false});const manual=map.getCenter();
 await act(async()=>useOperationsStore.getState().patch({movements:movements.map(m=>({...m,latitude:m.latitude+.2}))}));assert.ok(map.getCenter().equals(manual));
 let path;map.eachLayer(l=>{if(l instanceof L.Polyline)path=l;});assert.equal(path.getLatLngs().length,3);
 await act(async()=>useFedexStore.getState().begin({...movements[0],sequence:1}));assert.equal(markers().length,99);
 await act(async()=>useOperationsStore.getState().patch({enabled:false}));assert.equal(markers().length,0);
 console.log('PASS: 100 Leaflet entities; truck/plane/train icons; hover fields; filters; batched movement; pan preserved; arbitrary 3-node path; selected run deduplication; show-all off');
}finally{cleanup();await server.close();dom.window.close();}
