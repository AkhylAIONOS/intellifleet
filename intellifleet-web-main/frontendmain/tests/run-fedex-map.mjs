import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Element','SVGElement','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
Object.defineProperty(HTMLElement.prototype,'clientWidth',{get:()=>900});Object.defineProperty(HTMLElement.prototype,'clientHeight',{get:()=>600});
const L=(await import('leaflet')).default;L.Browser.svg=true;
const React=await import('react');const {render,act,cleanup}=await import('@testing-library/react');const {MapContainer}=await import('react-leaflet');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
  const {useFedexStore}=await server.ssrLoadModule('/src/store/fedexStore.ts');
  const {FedExLayer}=await server.ssrLoadModule('/src/components/MapLayers/FedExLayer.tsx');
  let map, fits=0;const original=L.Map.prototype.fitBounds;L.Map.prototype.fitBounds=function(...args){fits++;return original.apply(this,args);};
  render(React.createElement(MapContainer,{center:[24,74],zoom:5,ref:m=>{if(m)map=m;}},React.createElement(FedExLayer)));
  const state={simulation_id:'one',sequence:1,shipment_id:'S1',origin_station:'UDRPU',gateway:'DELGW',route:[[24,74],[28,77]],latitude:24,longitude:74,mode:'SURFACE',status:'IN_TRANSIT',progress:0};
  await act(async()=>useFedexStore.getState().begin(state));assert.equal(fits,1);
  const moving=()=>{let marker;map.eachLayer(l=>{if(l instanceof L.CircleMarker&&l.options.radius===11)marker=l;});return marker;};
  assert.equal(moving().getLatLng().lat,24);
  map.panTo([26,75]);const center=map.getCenter();
  await act(async()=>useFedexStore.getState().update({...state,sequence:2,latitude:26,longitude:75.5,progress:.5}));
  assert.equal(moving().getLatLng().lat,26);assert.equal(fits,1);assert.ok(map.getCenter().equals(center));
  assert.match(document.body.textContent,/SIMULATED TELEMETRY/);
  await act(async()=>useFedexStore.getState().reset());assert.equal(moving(),undefined);
  cleanup();console.log('PASS: backend snapshot moves Leaflet marker; one fit per run; manual pan preserved; synthetic label; reset removes layer');
}finally{cleanup();await server.close();dom.window.close();}
