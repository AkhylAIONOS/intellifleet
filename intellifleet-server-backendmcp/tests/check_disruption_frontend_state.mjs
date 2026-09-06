// Checks real captured chat actions against the existing frontend store without editing frontend code.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const frontend=new URL('../../intellifleet-web-main/frontendmain/',import.meta.url);
const {createServer}=await import(new URL('node_modules/vite/dist/node/index.js',frontend));
const rows=JSON.parse(fs.readFileSync(new URL('./contextual_disruption_azure_results.json',import.meta.url),'utf8'));
const server=await createServer({root:fileURLToPath(frontend),optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
 const {useAppStore}=await server.ssrLoadModule('/src/store/appStore.ts');
 for(const row of rows){
  const store=useAppStore.getState();store.resetStore();
  store.applyPlanningMapPlan(row.first.body.actions[0].data);
  const before=useAppStore.getState().selectedPlan;
  const result=row.second.body.actions[0].data;
  store.applyPlanningMapPlan(result);
  const state=useAppStore.getState();
  if(result.recommended_plan){
   assert.deepEqual(state.selectedPlan.route_legs,result.recommended_plan.route_legs);
   assert.notDeepEqual(state.selectedPlan.route_legs,before.route_legs);
   assert.equal(Object.values(state.activeRoutes).filter(r=>r.routeData.planning).length,1);
   assert.deepEqual(state.planComparison.before,before);
  }else{assert.deepEqual(state.selectedPlan,before);assert.match(state.planNotice,/current plan retained/);}
  console.log('PASS unchanged frontend action/state:',row.name);
 }
}finally{await server.close();}
