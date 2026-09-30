import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://192.0.2.1/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const original=Object.getOwnPropertyDescriptor(globalThis,'crypto');
const React=await import('react');
const {renderHook,act,cleanup}=await import('@testing-library/react');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
 const {createSessionId}=await server.ssrLoadModule('/src/utils/sessionId.ts');
 const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
 Object.defineProperty(globalThis,'crypto',{value:{randomUUID:()=> 'native-uuid'},configurable:true});
 assert.equal(createSessionId(),'native-uuid');
 let randomCalls=0;
 Object.defineProperty(globalThis,'crypto',{value:{getRandomValues:b=>{randomCalls++;return dom.window.crypto.getRandomValues(b);}},configurable:true});
 assert.match(createSessionId(),uuid);assert.equal(randomCalls,1);
 const {useRouteAgent}=await server.ssrLoadModule('/src/hooks/useRouteAgent.ts');
 const {chatApi}=await server.ssrLoadModule('/src/api/chat.ts');
 const {useAppStore}=await server.ssrLoadModule('/src/store/appStore.ts');
 const {useOperationsStore}=await server.ssrLoadModule('/src/store/operationsStore.ts');
 const {default:api}=await server.ssrLoadModule('/src/api/client.ts');
 const prompt='Plan 6,000 kg from Mumbai to Bengaluru using Ground. Show the route, assigned vehicle, cost, ETA, risk and reliability.';
 const plan={plan_id:'http-ground',mode:'road',vehicles:[{id:1,label:'Truck',capacity:7000}],route_legs:[{route_id:1,route_type:'road',from_location:'Mumbai',to_location:'Bengaluru',source_coords:{lat:19,lng:73},destination_coords:{lat:13,lng:77}}],distance_km:1000,duration_hours:24,operational_cost:50000};
 let sent=[];
 chatApi.sendMessage=async(message,id)=>{assert.equal(message,prompt);assert.match(id,uuid);sent.push(id);return {success:true,response:'Ground plan ready',actions:[{type:'supply_chain_planning_operation',data:{recommended_plan:plan}}]};};
 api.post=async(path)=>{assert.equal(path,'/operations/plan-journeys/http-ground');return {data:{simulation_id:'ai-http',shipment_id:'PLAN-http-ground',paused:false,progress:0,route:[[19,73],[13,77]]}};};
 const hook=renderHook(()=>useRouteAgent());
 await act(async()=>hook.result.current.processMessage(prompt));
 assert.equal(useAppStore.getState().selectedPlan.plan_id,plan.plan_id);
 assert.deepEqual(useOperationsStore.getState().aiSimulationIds,['ai-http']);
 await act(async()=>hook.result.current.processMessage(prompt));assert.equal(sent[0],sent[1]);
 Object.defineProperty(globalThis,'crypto',{value:undefined,configurable:true});
 const ids=new Set(Array.from({length:100},()=>createSessionId()));assert.equal(ids.size,100);for(const id of ids)assert.match(id,uuid);
 await act(async()=>{hook.result.current.startNewSession();await hook.result.current.processMessage(prompt);});assert.notEqual(sent[2],sent[0]);
 // Four sequential requests in one HTTP chat retain all feasible returned plans.
 await act(async()=>hook.result.current.startNewSession());
 const pairs=[['Delhi','Bengaluru'],['Mumbai','Bengaluru'],['Mumbai','Chennai'],['Kolkata','Delhi']];
 let next=0,sessionIds=[];
 chatApi.sendMessage=async(message,id)=>{
  const [source,destination]=pairs[next];assert.equal(message,`Plan 6000 kg ${source} to ${destination} using Ground.`);sessionIds.push(id);
  const result={...plan,plan_id:`sequence-${next++}`,route_legs:[{...plan.route_legs[0],from_location:source,to_location:destination}]};
  return {success:true,response:'Calculated plan',actions:[{type:'supply_chain_planning_operation',data:{recommended_plan:result}}]};
 };
 api.post=async(path)=>{const id=path.split('/').at(-1);return {data:{simulation_id:id,shipment_id:`PLAN-${id}`,paused:false,progress:0,route:[[19,73],[13,77]]}};};
 for(const [source,destination] of pairs){
  await act(async()=>hook.result.current.processMessage(`Plan 6000 kg ${source} to ${destination} using Ground.`));
  assert.equal(useOperationsStore.getState().aiSimulationIds.length,next);
 }
 assert.equal(new Set(sessionIds).size,1);
 chatApi.sendMessage=async()=>({success:true,response:'Revised ETA',actions:[{type:'show_movements',data:{selected:'sequence-0',filter:'ALL'}}]});
 await act(async()=>hook.result.current.processMessage('What happens if the selected shipment is delayed by 30 minutes?'));
 assert.equal(useOperationsStore.getState().viewMode,'AI');assert.equal(useOperationsStore.getState().aiSimulationIds.length,4);
 const backendCount=useOperationsStore.getState().movements.length;
 await act(async()=>hook.result.current.startNewSession());
 assert.deepEqual(useOperationsStore.getState().aiSimulationIds,[]);
 assert.equal(useOperationsStore.getState().movements.length,backendCount);
 let finish;
 chatApi.sendMessage=()=>new Promise(resolve=>{finish=resolve;});
 let pending;
 await act(async()=>{pending=hook.result.current.processMessage('Plan another route');});
 await act(async()=>hook.result.current.startNewSession());
 await act(async()=>{finish({success:true,actions:[{type:'supply_chain_planning_operation',data:{recommended_plan:{...plan,plan_id:'stale'}}}]});await pending;});
 assert.deepEqual(useOperationsStore.getState().aiSimulationIds,[],'Late response cannot leak into a new chat');
 console.log('PASS: four sequential HTTP planning requests, isolated New Chat, stale response ignored');
 console.log('PASS: native UUID, getRandomValues UUID, absent crypto fallback, HTTP Ground chat request/action/journey, session reuse/reset');
}finally{cleanup();await server.close();dom.window.close();if(original)Object.defineProperty(globalThis,'crypto',original);else delete globalThis.crypto;}
