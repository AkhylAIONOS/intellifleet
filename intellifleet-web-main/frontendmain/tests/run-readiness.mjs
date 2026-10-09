import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const React=await import('react');const {render,fireEvent,waitFor,cleanup}=await import('@testing-library/react');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
 const {operationalTime}=await server.ssrLoadModule('/src/utils/operationalTime.ts');
 assert.match(operationalTime('2026-09-29T23:30:00Z'),/30 Sept? 2026, 05:00 IST/);
 assert.match(operationalTime('2026-09-30T12:30:00+05:30'),/12:30 IST/);
 assert.equal(operationalTime('12:00 (+1d)'),'12:00 (+1d)');
 const {planningApi}=await server.ssrLoadModule('/src/api/planning.ts');
 const {PlanningPanel}=await server.ssrLoadModule('/src/components/PlanningPanel.tsx');
 const screen=render(React.createElement(PlanningPanel));
 fireEvent.change(screen.getByPlaceholderText('Delhi'),{target:{value:'Delhi'}});
 fireEvent.change(screen.getByPlaceholderText('Mumbai'),{target:{value:'Mumbai'}});
 planningApi.createPlan=async()=>{throw {response:{status:500,data:{detail:'secret server trace'}}};};
 fireEvent.click(screen.getByText('Calculate Plan'));await waitFor(()=>assert.match(screen.getByRole('alert').textContent,/could not complete/));
 assert.doesNotMatch(screen.getByRole('alert').textContent,/secret/);
 planningApi.createPlan=async()=>({recommended_plan:null,reason:'No feasible air route in the loaded network.'});
 fireEvent.click(screen.getByText('Calculate Plan'));await waitFor(()=>assert.match(screen.getByRole('alert').textContent,/No feasible air route/));
 console.log('PASS: IST rollover, schedule-only clocks preserved, planner errors sanitized, infeasibility visible');
} finally {cleanup();await server.close();dom.window.close();}
