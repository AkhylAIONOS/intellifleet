import assert from 'node:assert/strict';
import {createServer} from 'vite';
const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
try {
 const {useAppStore:store}=await server.ssrLoadModule('/src/store/appStore.ts');
 const make=(id,journey,source='Bengaluru',destination='Delhi')=>({recommended_plan:{plan_id:id,journey_id:journey,mode:'road',revision:1,vehicles:[{id:3,label:'TRK-003'}],route_legs:[{route_id:1,from_location:source,to_location:destination,route_type:'road',source_coords:{lat:12,lng:77},destination_coords:{lat:28,lng:77}}]}});
 store.setState({activeRoutes:{},vehicles:[],selectedPlan:null});
 const first=store.getState().applyPlanningMapPlan(make('revision-1','journey-a'));
 const second=store.getState().applyPlanningMapPlan(make('revision-2','journey-b','Mumbai','Bengaluru'));
 assert.equal(store.getState().planComparison,null,'Independent shipment must not compare against the previous shipment');
 const revised=make('revision-3','journey-a');revised.recommended_plan.revision=2;
 const updated=store.getState().applyPlanningMapPlan(revised);
 assert.equal(first,updated);assert.notEqual(first,second);
 assert.equal(Object.keys(store.getState().activeRoutes).length,2);
 assert.equal(store.getState().activeRoutes[second].routeData.plan_id,'revision-2');
 store.getState().applyPlanningMapPlan(make('revision-4','journey-c'));
 assert.equal(Object.keys(store.getState().activeRoutes).length,3,'Explicit same-OD shipment must remain independent');
 globalThis.localStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{}};
 const {default:api}=await server.ssrLoadModule('/src/api/client.ts');
 const {useOperationsStore:ops}=await server.ssrLoadModule('/src/store/operationsStore.ts');
 const {ensurePlanMovement}=await server.ssrLoadModule('/src/utils/planMovement.ts');
 ops.setState({movements:[],aiSimulationIds:[],aiSessionGeneration:0});
 let requests=0;
 api.defaults.adapter=async config=>{
   requests++;
   const revision=config.url.includes('revision-3')?2:1;
   return {data:{simulation_id:'movement-a',shipment_id:'PLAN-journey-a',revision,plan_id:revision===2?'revision-3':'revision-1',paused:false,progress:0,stopped:false},status:200,statusText:'OK',headers:{},config};
 };
 await ensurePlanMovement(make('revision-1','journey-a').recommended_plan);
 await ensurePlanMovement(revised.recommended_plan);
 await ensurePlanMovement(revised.recommended_plan);
 assert.equal(requests,2,'A revision refreshes operations once; repeated effects reuse it');
 assert.equal(ops.getState().movements.length,1);
 assert.equal(ops.getState().movements[0].revision,2);
 assert.deepEqual(ops.getState().aiSimulationIds,['movement-a']);
 console.log('PASS: logical journey revisions replace one route; unrelated and same-OD shipments persist; independent plans have no false before/after comparison');
} finally {await server.close();}
