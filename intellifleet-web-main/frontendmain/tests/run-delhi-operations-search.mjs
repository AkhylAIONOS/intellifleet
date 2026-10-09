import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const backend=fileURLToPath(new URL('../../../intellifleet-server-backendmcp/',import.meta.url));
// Produce fixture responses through the real backend endpoint and supplied workbook.
const python=`
import json,tempfile
from datetime import date
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.control_tower import routes
from backend.control_tower.service import ControlTower
from backend.fedex.importer import load_schedules
from backend.routes.auth import get_current_user
with tempfile.TemporaryDirectory() as directory:
 routes.service=ControlTower(directory+'/ct.db')
 routes.service.import_network(1,load_schedules(),date(2030,1,1))
 app=FastAPI();app.include_router(routes.router)
 app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
 client=TestClient(app)
 queries=['','DELGW','NDLS','Delhi','delhi','DEL','Atlantis']
 responses={q:client.get('/operations/control-tower/runs',params={'service_date':'2030-01-01','mode':'SURFACE','search':q,'limit':25}).json() for q in queries}
 print(json.dumps(responses))
`;
const generated=spawnSync(process.env.UNIFLEET_TEST_PYTHON || (existsSync(backend+'.venv/bin/python')?backend+'.venv/bin/python':path.resolve(backend,'../../IntelliFleet/intellifleet-server-backendmcp/.venv/bin/python')),['-c',python],{cwd:backend,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',SECRET_KEY:randomBytes(32).toString('hex')},encoding:'utf8',maxBuffer:8*1024*1024});
assert.equal(generated.status,0,generated.stderr);const responses=JSON.parse(generated.stdout);
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const React=await import('react');const {render,act,fireEvent,waitFor,cleanup}=await import('@testing-library/react');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {controlTowerApi:api}=await server.ssrLoadModule('/src/api/controlTower.ts');
 const {ControlTower}=await server.ssrLoadModule('/src/components/ControlTower.tsx');
 const sent=[];
 api.runs=async params=>{sent.push(params.search||'');return responses[params.search||''];};
 api.summary=async()=>({total_runs:38,air_runs:10,surface_runs:21,statuses:{SCHEDULED:38},critical_lanes:0,critical_lanes_at_risk:0});
 api.recipients=async()=>({emails:[]});
 const ui=render(React.createElement(ControlTower));await act(async()=>{});
 const search=ui.getByPlaceholderText('City, station, lane, run or carrier');
 for(const query of ['DELGW','NDLS','Delhi','delhi','DEL','Atlantis','']){
  const before=sent.length;
  await act(async()=>fireEvent.change(search,{target:{value:query}}));
  await waitFor(()=>assert.ok(sent.length>before&&sent.at(-1)===query));
  await waitFor(()=>assert.ok(ui.getByText(`Surface linehaul · ${responses[query].total} matching runs · source cells preserved`)));
  if(query==='Atlantis')assert.ok(ui.getByText(/No matching operational runs/));
  if(query==='Delhi'){
   assert.ok(ui.getByRole('button',{name:'AGRGA-DELGW',exact:true}));
   assert.equal(ui.queryByRole('button',{name:'DDU-NDLS',exact:true}),null,'Train service must not appear in Surface results');
  }
 }
 assert.equal(responses[''].total,21);
 assert.equal(responses.Delhi.total,responses.delhi.total);
 assert.equal(responses.Delhi.total,responses.DEL.total);
 console.log('PASS: DELGW, NDLS, Delhi/delhi/DEL, clear restores 21 Surface rows; Train services remain separate, clean empty state; real backend endpoint responses rendered through UI');
}finally{cleanup();await server.close();dom.window.close();}
