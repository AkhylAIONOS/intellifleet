import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
const out='../../qa/road-routing';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},timezoneId:'Asia/Kolkata'});
const results=[],errors=[],evidence={};
let expectedFailure=false;
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error'&&!expectedFailure)errors.push(m.text());});
page.on('response',r=>{if(r.url().includes(':4219')&&r.status()>=400&&!expectedFailure)errors.push(`HTTP ${r.status()} ${r.url().split('?')[0]}`);});
page.on('requestfailed',r=>{if(!expectedFailure&&!r.failure()?.errorText.includes('ERR_ABORTED'))errors.push(`${r.failure()?.errorText} ${r.url().split('?')[0]}`);});
async function api(url,data,method='get'){return page.evaluate(async({url,data,method})=>{const {default:client}=await import('/src/api/client.ts');try{const r=await client.request({url,data,method});return {status:r.status,data:r.data};}catch(e){return {status:e.response?.status,data:e.response?.data};}},{url,data,method});}
const tab=n=>page.getByRole('navigation',{name:'Operations workspace'}).getByRole('button',{name:n,exact:true}).click();
const state=()=>page.evaluate(async()=> (await import('/src/store/fedexStore.ts')).useFedexStore.getState().telemetry);
const pos=s=>[s.latitude,s.longitude];
async function check(name,fn){try{await fn();results.push({name,pass:true});console.log('PASS',name);}catch(e){results.push({name,pass:false,error:e.message});console.log('FAIL',name,e.message.slice(0,500));}}
let id;
try{
await check('real browser login and 30/97/72 network import',async()=>{
 await page.goto('http://127.0.0.1:5189');await page.getByRole('button',{name:'Enter UniFleet',exact:true}).click();await tab('NETWORK');
 const inputs=page.locator('.network-upload-fields input[type=file]');for(const [i,n] of ['warehouse','vehicle','routes'].entries())await inputs.nth(i).setInputFiles(`public/synthetic_v2/${n}.csv`);
 const response=page.waitForResponse(r=>r.url().endsWith('/upload-network'));await page.getByRole('button',{name:'Upload & Process'}).click();expect((await response).status()).toBe(200);
 await page.waitForTimeout(1200);await tab('NETWORK');await expect(page.locator('.network-summary dd')).toHaveText(['30','97','72']);
});
await check('real OSRM Surface start and road polyline rendered',async()=>{
 await tab('SCHEDULES');await page.getByLabel('Schedule source',{exact:false}).selectOption('FEDEX');await page.getByLabel('Origin Station',{exact:false}).selectOption('UDRPU');await page.getByLabel('Gateway',{exact:false}).selectOption('DELGW');await page.getByLabel('Simulation Date',{exact:false}).fill('2026-09-29');await page.getByLabel('Shipment Ready Time',{exact:false}).fill('18:00');await page.getByRole('button',{name:'Evaluate Cutoffs',exact:true}).click();await page.getByLabel('Simulation Speed',{exact:false}).selectOption('3600');
 await page.getByRole('button',{name:'Start Simulation',exact:true}).click();await expect(page.getByLabel('FedEx live state',{exact:true})).toContainText('IN_TRANSIT',{timeout:60000});
 let s=await state();id=s.simulation_id;expect(s.mode).toBe('SURFACE');expect(s.route.length).toBeGreaterThan(1000);expect(s.road_routing_status).toBe('READY');expect(s.route_source).toContain('OSRM');
 await api(`/fedex/simulations/${id}/control`,{action:'speed',speed:1},'post');
 evidence.route={points:s.route.length,source:s.route_source,km:s.route_distance_km,routeId:s.route_id};
 expect(await page.locator('.leaflet-overlay-pane path').evaluateAll(paths=>Math.max(...paths.map(p=>(p.getAttribute('d')||'').split('L').length)))).toBeGreaterThan(20);
 await page.getByRole('button',{name:'Zoom out',exact:true}).click();await page.waitForTimeout(2000);await page.screenshot({path:`${out}/road-route.png`});
});
await check('30-minute delay freezes exact road position and updates ETA',async()=>{
 await page.getByRole('button',{name:'Inject Delay',exact:true}).click();await expect(page.getByLabel('FedEx live state',{exact:true})).toContainText('12:30');
 const before=(await api(`/fedex/simulations/${id}`)).data;await page.waitForTimeout(1800);const after=(await api(`/fedex/simulations/${id}`)).data;
 expect(pos(after)).toEqual(pos(before));expect(after.current_eta).not.toBe(after.scheduled_eta);expect(after.delay_minutes).toBe(30);expect(after.route_id).toBe(before.route_id);
 const [a,b]=after.route.slice(after.current_segment,after.current_segment+2);const [lat,lon]=pos(after);
 expect(Math.abs((lat-a[0])*(b[1]-a[1])-(lon-a[1])*(b[0]-a[0]))).toBeLessThan(1e-10);
 expect(lat).toBeGreaterThanOrEqual(Math.min(a[0],b[0]));expect(lat).toBeLessThanOrEqual(Math.max(a[0],b[0]));
 expect(lon).toBeGreaterThanOrEqual(Math.min(a[1],b[1]));expect(lon).toBeLessThanOrEqual(Math.max(a[1],b[1]));
 evidence.delay={position:pos(after),scheduled:after.scheduled_eta,revised:after.current_eta};
 const map=await page.locator('.leaflet-container').boundingBox();const marker=await page.locator('.movement-icon').first().boundingBox();
 const target={x:map.x+map.width/2,y:map.y+Math.min(map.height,1000-map.y)/2};
 await page.mouse.move(target.x,target.y);await page.mouse.down();await page.mouse.move(target.x+target.x-marker.x-marker.width/2,target.y+target.y-marker.y-marker.height/2,{steps:10});await page.mouse.up();
 await page.mouse.move(target.x,target.y);await page.mouse.wheel(0,-400);await page.waitForTimeout(2000);await page.screenshot({path:`${out}/road-delay.png`});
});
await check('pause resumes on same route and reaches snapped destination',async()=>{
 await api(`/fedex/simulations/${id}/control`,{action:'pause'},'post');const before=(await api(`/fedex/simulations/${id}`)).data;await page.waitForTimeout(1000);expect(pos((await api(`/fedex/simulations/${id}`)).data)).toEqual(pos(before));
 await api(`/fedex/simulations/${id}/control`,{action:'speed',speed:10000},'post');await api(`/fedex/simulations/${id}/control`,{action:'resume'},'post');
 await expect.poll(async()=>(await api(`/fedex/simulations/${id}`)).data.status,{timeout:30000}).toBe('ARRIVED_AT_GTW');const end=(await api(`/fedex/simulations/${id}`)).data;expect(pos(end)).toEqual(end.route.at(-1));expect(end.progress).toBe(1);
});
await check('Delhi Mumbai road geometry and preserved planning',async()=>{
 const plan=await api('/planning/plans',{source:'Delhi',destination:'Mumbai',shipment:{weight_kg:6000},allowed_modes:['road']},'post');expect(plan.data.recommended_plan).toBeTruthy();
 await tab('LIVE OPERATIONS');await page.getByRole('region',{name:'Live network',exact:true}).getByLabel('Origin',{exact:false}).selectOption('Delhi');await page.getByRole('region',{name:'Live network',exact:true}).getByLabel('Destination',{exact:false}).selectOption('Mumbai');
 const response=page.waitForResponse(r=>r.url().endsWith('/operations/route-simulation'));await page.getByRole('button',{name:'Plan & simulate 6000 kg'}).click();const result=await response;expect(result.status()).toBe(201);const s=await result.json();expect(s.route.length).toBeGreaterThan(7000);evidence.delhiMumbai={points:s.route.length,km:s.route_distance_km};
 await expect(page.getByLabel('Selected movement',{exact:true})).toContainText('OpenStreetMap / OSRM');await page.waitForTimeout(2000);await page.screenshot({path:`${out}/delhi-mumbai-live.png`});
});
await check('unsupported road objective returns explicit 422',async()=>{
 expectedFailure=true;const r=await api('/fedex/simulations',{origin_station:'UDRPU',gateway:'DELGW',simulation_date:'2026-09-29',shipment_ready_datetime:'2026-09-29T18:00:00+05:30',road_optimization:'CHEAPEST'},'post');expect(r.status).toBe(422);expect(r.data.detail).toContain('ROAD_OPTIMIZATION_UNSUPPORTED');expectedFailure=false;
});
await check('no unexpected browser console or network errors',async()=>expect(errors).toEqual([]));
}finally{await fs.writeFile(`${out}/browser.json`,JSON.stringify({results,evidence,errors},null,2));await browser.close();}
if(results.some(r=>!r.pass))process.exitCode=1;
