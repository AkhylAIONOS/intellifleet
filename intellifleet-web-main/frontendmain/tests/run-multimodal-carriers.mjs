import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Element','SVGElement','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
Object.defineProperty(HTMLElement.prototype,'clientWidth',{get:()=>900});Object.defineProperty(HTMLElement.prototype,'clientHeight',{get:()=>600});
let reduced=false;window.matchMedia=()=>({matches:reduced,addEventListener(){},removeEventListener(){}});
const L=(await import('leaflet')).default;L.Browser.svg=true;
const React=await import('react');const {render,act,cleanup}=await import('@testing-library/react');const {MapContainer}=await import('react-leaflet');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {NetworkMovementsLayer}=await server.ssrLoadModule('/src/components/MapLayers/NetworkMovementsLayer.tsx');
 const {useOperationsStore}=await server.ssrLoadModule('/src/store/operationsStore.ts');
 let map,fits=0;const original=L.Map.prototype.fitBounds;L.Map.prototype.fitBounds=function(...args){fits++;return original.apply(this,args);};
 render(React.createElement(MapContainer,{center:[24,74],zoom:5,ref:m=>{if(m)map=m;}},React.createElement(NetworkMovementsLayer)));
 const route=[[10,70],[11,71],[12,72],[13,73]];
 const journey_segments=['SURFACE','AIR','SURFACE'].map((mode,i)=>({start_index:i,end_index:i+1,mode,route_id:i+1,from_location:'ABCD'[i],to_location:'ABCD'[i+1],start_progress:i/3,end_progress:(i+1)/3,vehicles:[{id:i+1,label:['TRK-001','AIR-001','TRK-002'][i],type:mode==='AIR'?'aircraft':'truck'}]}));
 const base={simulation_id:'shipment',journey_id:'logical',plan_id:'p1',revision:1,shipment_id:'PLAN-logical',mode:'SURFACE',origin_station:'A',gateway:'D',route,journey_segments,latitude:10,longitude:70,heading:30,progress:0,status:'IN_TRANSIT',data_source:'SYNTHETIC_NETWORK',location_source:'DEMO_SIMULATION',scheduled_etd:'2026-10-01T18:00',current_eta:'2026-10-02T08:00',delay_minutes:0};
 const layers=type=>{const rows=[];map.eachLayer(l=>{if(l instanceof type)rows.push(l);});return rows;};
 await act(async()=>useOperationsStore.getState().patch({enabled:true,viewMode:'AI',selected:'shipment',aiSimulationIds:['shipment'],movements:[base],filter:'ALL',fit:1}));
 assert.equal(layers(L.Polyline).length,3);const stableFits=fits;let sequence=0;
 for(reduced of [false,true])for(let leg=0;leg<3;leg++){
   const positions=[];
   for(const fraction of [.2,.8]){
    await act(async()=>useOperationsStore.getState().patch({movements:[{...base,sequence:++sequence,active_leg_index:leg,segment_progress:fraction,progress:(leg+fraction)/3,latitude:10+leg+fraction,longitude:70+leg+fraction}]}));
    const markers=layers(L.Marker);assert.equal(markers.length,1,'No duplicate carriers after transfer');
    assert.match(markers[0].options.icon.options.html,new RegExp(`aria-label="${leg===1?'plane':'truck'}"`));
    positions.push(markers[0].getLatLng());await act(async()=>markers[0].openTooltip());
    assert.ok(document.body.textContent.includes(journey_segments[leg].vehicles[0].label));
    assert.equal(layers(L.Polyline).length,3);assert.equal(useOperationsStore.getState().movements.length,1);
   }
   assert.ok(!positions[0].equals(positions[1]),'Active carrier moves along its own geometry');
 }
 assert.equal(fits,stableFits,'Animation ticks never refit');
 await act(async()=>useOperationsStore.getState().patch({filter:'SURFACE',movements:[{...base,sequence:++sequence,mode:'AIR',active_leg_index:1,latitude:11.5,longitude:71.5,progress:.5}]}));
 assert.equal(layers(L.Marker).length,1,'Surface filter cannot hide the Air carrier of the same mixed journey');
 assert.match(layers(L.Marker)[0].options.icon.options.html,/aria-label="plane"/);
 document.querySelector('.journey-controls button').click();const center=map.getCenter();
 await act(async()=>useOperationsStore.getState().patch({movements:[{...base,sequence:++sequence,latitude:12,longitude:72,progress:.5,active_leg_index:1}]}));
 assert.ok(map.getCenter().equals(center),'Reduced motion suppresses camera tracking');reduced=false;
 await act(async()=>useOperationsStore.getState().patch({movements:[{...base,sequence:++sequence,latitude:12.1,longitude:72.1,progress:.6,active_leg_index:1}]}));
 assert.ok(map.getCenter().equals(L.latLng(12.1,72.1)));
 await act(async()=>useOperationsStore.getState().patch({movements:[{...base,revision:2,plan_id:'p2',route:[[20,70],[21,71]],journey_segments:[{start_index:0,end_index:1,mode:'AIR',vehicles:[{id:4,label:'AIR-004'}]}],active_leg_index:0,latitude:20.5,longitude:70.5}]}));
 assert.equal(layers(L.Polyline).length,1);assert.equal(layers(L.Marker).length,1);
 await act(async()=>useOperationsStore.getState().patch({movements:[{...base,revision:3,plan_id:'p3',active_leg_index:1,latitude:11.5,longitude:71.5}]}));
 assert.equal(layers(L.Polyline).length,3);assert.equal(layers(L.Marker).length,1);
 assert.ok(layers(L.Polyline).every(p=>p.getLatLngs().every(point=>point.lat<20)));
 assert.match(layers(L.Marker)[0].options.icon.options.html,/aria-label="plane"/);
 console.log('PASS: rendered Road → Air → Road, moving plane, assignments, follow, reduced motion, revision replacement, no duplicates or per-tick fit');
}finally{cleanup();await server.close();dom.window.close();}
