import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const React=await import('react');const {render,act,fireEvent,cleanup}=await import('@testing-library/react');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
  const {fedexApi,parseTelemetryFrame}=await server.ssrLoadModule('/src/api/fedex.ts');
  const {useFedexStore}=await server.ssrLoadModule('/src/store/fedexStore.ts');
  const {FedExPanel}=await server.ssrLoadModule('/src/components/FedExPanel.tsx');
  const state={simulation_id:'test',shipment_id:'S1',sequence:1,origin_station:'UDRPU',gateway:'DELGW',mode:'SURFACE',run:'1',service:'pickup',simulation_timestamp:'2026-09-29T23:00:00+05:30',scheduled_etd:'2026-09-29T22:00:00+05:30',scheduled_eta:'2026-09-30T12:00:00+05:30',current_eta:'2026-09-30T12:00:00+05:30',cutoff:'2026-09-29T21:30:00+05:30',retrieval:null,latitude:25,longitude:74,progress:.1,status:'IN_TRANSIT',paused:false,stopped:false,simulation_speed:600,synthetic_data:true,location_source:'DEMO_SIMULATION',route:[[24,73],[28,77]],alerts:[]};
  assert.equal(parseTelemetryFrame(`event: telemetry\ndata: ${JSON.stringify(state)}`).progress,.1);
  assert.equal(parseTelemetryFrame('event: expired\ndata: {}'),null);
  assert.throws(()=>parseTelemetryFrame('event: telemetry\ndata: {}'));
  useFedexStore.getState().begin(state);useFedexStore.getState().update({...state,sequence:0,progress:.9});assert.equal(useFedexStore.getState().telemetry.progress,.1);
  useFedexStore.getState().reset();useFedexStore.getState().update(state);assert.equal(useFedexStore.getState().telemetry,null);
  fedexApi.summary=async()=>({lanes:[{origin_station:'UDRPU',gateway:'DELGW',simulation_supported:true}],schedule_notice:'Template only'});
  const candidate={schedule_id:'surface-16',mode:'SURFACE',run:'1',service:'pickup',eligible:true,cutoff:state.cutoff,etd:state.scheduled_etd,eta:state.scheduled_eta,warnings:[],reason:'Ready before cutoff'};
  const sources=[];
  fedexApi.eligible=async(_input,source)=>{sources.push(source);return({candidates:[candidate],selected:candidate,selection_reason:'Earliest eligible arrival'});};
  let created;
  fedexApi.create=async input=>{created=input;return state;};
  globalThis.fetch=async()=>new Response('',{status:404});
  fedexApi.event=async()=>({...state,sequence:2,status:'DELAYED',current_eta:'2026-09-30T12:30:00+05:30',alerts:[{title:'DELAY DETECTED',severity:'WARNING',impact:'Arrival shifts by 30 minutes',recommended_action:'Notify gateway',reason:'Synthetic delay',eligible_alternatives:[]}]});
  fedexApi.control=async()=>({reset:true});
  let ui;await act(async()=>{ui=render(React.createElement(FedExPanel));});
  assert.ok(ui.getByText('SIMULATED TELEMETRY'));
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Evaluate Cutoffs'})));
  assert.ok(ui.getByText('Ready before cutoff'));
  assert.equal(sources.at(-1),'SYNTHETIC');
  for(const ready of ['16:30','21:30','00:00','23:00']){
    await act(async()=>fireEvent.change(ui.getByLabelText('Shipment Ready Time'),{target:{value:ready}}));
    assert.equal(ui.queryByText('Ready before cutoff'),null);
    await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Evaluate Cutoffs'})));
  }
  for(const source of ['FEDEX','SYNTHETIC','FEDEX']){
    await act(async()=>fireEvent.change(ui.getByLabelText('Schedule source'),{target:{value:source}}));
    assert.equal(ui.queryByText('Ready before cutoff'),null);
    await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Evaluate Cutoffs'})));
    assert.equal(sources.at(-1),source);
  }
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Start Simulation'})));
  assert.equal(created.schedule_id,'surface-16');assert.equal(created.speed,120);
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Inject Delay'})));
  assert.ok(ui.getByText(/DELAY DETECTED/));assert.equal(useFedexStore.getState().telemetry.current_eta,'2026-09-30T12:30:00+05:30');
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Reset'})));
  assert.equal(useFedexStore.getState().telemetry,null);
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Start Simulation'})));
  fedexApi.control=async()=>{throw {response:{status:404}};};
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Reset'})));
  assert.equal(useFedexStore.getState().telemetry,null,'Expired server runs can be reset locally');
  cleanup();console.log('PASS: FedEx controls, cutoff result, telemetry validation, stale-event isolation, delay alert and reset');
}finally{cleanup();await server.close();}
