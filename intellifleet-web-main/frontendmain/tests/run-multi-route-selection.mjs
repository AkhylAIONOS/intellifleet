import assert from 'node:assert/strict';
import {createServer} from 'vite';
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {useControlTowerStore}=await server.ssrLoadModule('/src/store/controlTowerStore.ts');
 const run=(id,date='2026-10-09')=>({run_id:id,service_date:date,status:'SCHEDULED',schedule:{mode:'AIR'}});
 const store=()=>useControlTowerStore.getState();store().reset();
 for(const id of ['a','b','c','d'])store().toggleSelection(run(id));
 assert.deepEqual(store().selectedRuns.map(r=>r.run_id),['a','b','c','d']);
 store().refreshSelection(['a','b','c','d'].map(id=>({...run(id),status:'ON TIME'})));
 assert.equal(store().selectedRuns.length,4);assert.ok(store().selectedRuns.every(r=>r.status==='ON TIME'));
 store().updateSelection({...run('d'),status:'DELAYED'});assert.equal(store().selectedRuns.length,4);assert.equal(store().selected.status,'DELAYED');
 store().toggleSelection(run('b'));assert.deepEqual(store().selectedRuns.map(r=>r.run_id),['a','c','d']);
 store().setServiceDate('2026-10-10');assert.equal(store().selected,null);assert.deepEqual(store().selectedRuns,[]);
 store().select(run('single'));assert.deepEqual(store().selectedRuns.map(r=>r.run_id),['single']);
 store().select(null);assert.equal(store().selected,null);assert.deepEqual(store().selectedRuns,[]);
 store().toggleSelection(run('a'));store().reset();assert.equal(store().selectedRuns.length,0);
 console.log('PASS: 2/3/4 route selection, refresh retention, focused details, removal, date isolation, single selection and reset');
}finally{await server.close();}
