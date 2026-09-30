import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
const out='../../qa/plan-journey';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},timezoneId:'Asia/Kolkata'});
const results=[],errors=[],evidence=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
const tab=n=>page.getByRole('navigation',{name:'Operations workspace'}).getByRole('button',{name:n,exact:true}).click();
async function api(url,data,method='get'){return page.evaluate(async({url,data,method})=>{const {default:client}=await import('/src/api/client.ts');const r=await client.request({url,data,method});return r.data;},{url,data,method});}
async function check(name,fn){try{await fn();results.push({name,pass:true});console.log('PASS',name);}catch(e){results.push({name,pass:false,error:e.message});console.log('FAIL',name,e.message.slice(0,700));await page.screenshot({path:`${out}/failure-${results.length}.png`});}}
const journey=()=>page.getByLabel('Road journey',{exact:true});
const coordinates=s=>[s.latitude,s.longitude];
async function centerError(){return page.evaluate(()=>{const m=document.querySelector('.leaflet-container').getBoundingClientRect(),v=document.querySelector('.movement-icon').getBoundingClientRect();return Math.hypot(v.x+v.width/2-m.x-m.width/2,v.y+v.height/2-m.y-m.height/2);});}
try{
await check('network import and normal workspace',async()=>{await page.goto('http://127.0.0.1:5189');await page.getByRole('button',{name:'Enter UniFleet',exact:true}).click();await tab('NETWORK');const fields=page.locator('.network-upload-fields input[type=file]');for(const [i,n] of ['warehouse','vehicle','routes'].entries())await fields.nth(i).setInputFiles(`public/synthetic_v2/${n}.csv`);const response=page.waitForResponse(r=>r.url().endsWith('/upload-network'));await page.getByRole('button',{name:'Upload & Process'}).click();expect((await response).status()).toBe(200);await page.waitForTimeout(1200);});
for(const [name,origin,destination,chat] of [['A PLAN Mumbai Bengaluru','Mumbai','Bengaluru',false],['B AI Ground Mumbai Bengaluru','Mumbai','Bengaluru',true],['C PLAN Delhi Mumbai','Delhi','Mumbai',false]]){
await check(name,async()=>{
 if(chat){await tab('AI CHAT');const f=page.getByPlaceholder('Ask UniFleet anything…');await f.fill('Plan 1,000 kg from Mumbai to Bengaluru using Ground. Show route, vehicle, cost, ETA, risk and reliability.');const response=page.waitForResponse(r=>r.url().endsWith('/mcp-agent'),{timeout:90000});await f.press('Enter');expect((await response).status()).toBe(200);}
 else{await tab('PLAN');await page.getByPlaceholder('Delhi',{exact:true}).fill(origin);await page.getByPlaceholder('Mumbai',{exact:true}).fill(destination);await page.getByRole('spinbutton',{name:'Weight kg',exact:true}).fill('1000');await page.getByLabel('Transport mode',{exact:true}).selectOption('road');await page.getByRole('button',{name:'Calculate Plan',exact:true}).click();await expect(page.getByRole('dialog',{name:'Recommended Plan'})).toBeVisible();}
 await expect(journey()).toHaveAttribute('data-simulation-id',/.+/,{timeout:60000});
 let id=await journey().getAttribute('data-simulation-id');const state=()=>api(`/fedex/simulations/${id}`);
 // AI may replace the previous plan asynchronously; identify by authoritative selected plan.
 const plan=await page.evaluate(async()=>(await import('/src/store/appStore.ts')).useAppStore.getState().selectedPlan);
 await expect.poll(async()=>(await state()).shipment_id,{timeout:10000}).toBe('PLAN-'+plan.plan_id);
 let start=await state();expect(start.route.length).toBeGreaterThan(1000);expect(start.road_routing_status).toBe('READY');expect(start.progress).toBe(0);expect(coordinates(start)).toEqual(start.route[0]);expect(Date.parse(start.current_eta)).toBe(Date.parse(plan.eta));
 if(!chat)await page.getByRole('button',{name:'Close recommended plan'}).click();
 await expect.poll(async()=>(await state()).progress,{timeout:10000}).toBeGreaterThan(0);
 await expect.poll(centerError,{timeout:5000}).toBeLessThan(5);
 const moving=await state();const [a,b]=moving.route.slice(moving.current_segment,moving.current_segment+2);expect(Math.abs((moving.latitude-a[0])*(b[1]-a[1])-(moving.longitude-a[1])*(b[0]-a[0]))).toBeLessThan(1e-10);
 if(!chat&&origin==='Mumbai'){
   await api(`/fedex/simulations/${id}/control`,{action:'speed',speed:1},'post');
   const map=await page.locator('.leaflet-container').boundingBox();await page.mouse.move(map.x+map.width/2,map.y+map.height/2);await page.mouse.down();await page.mouse.move(map.x+map.width/2+140,map.y+map.height/2,{steps:5});await page.mouse.up();
   await expect(page.getByRole('button',{name:'Follow Vehicle',exact:true})).toHaveAttribute('aria-pressed','false');await page.waitForTimeout(600);expect(await centerError()).toBeGreaterThan(30);
   await page.getByRole('button',{name:'Follow Vehicle',exact:true}).click();await expect.poll(centerError).toBeLessThan(5);
   await page.getByRole('button',{name:'Delay +30 min',exact:true}).click();await expect(journey()).toContainText('Delay 30 min');const delayed=await state();await page.waitForTimeout(1000);expect(coordinates(await state())).toEqual(coordinates(delayed));expect(Date.parse(delayed.current_eta)-Date.parse(start.current_eta)).toBe(1800000);
   await page.screenshot({path:`${out}/delay-follow.png`});await api(`/fedex/simulations/${id}/control`,{action:'speed',speed:3600},'post');await expect.poll(async()=>(await state()).progress,{timeout:5000}).toBeGreaterThan(delayed.progress);
 }
 await expect.poll(async()=>(await state()).status,{timeout:60000}).toBe('ARRIVED_AT_GTW');const end=await state();expect(coordinates(end)).toEqual(end.route.at(-1));await expect(journey()).toContainText('ARRIVED_AT_GTW');
 evidence.push({name,points:start.route.length,km:start.route_distance_km,eta:start.current_eta,cost:plan.operational_cost,risk:plan.risk_score,reliability:plan.reliability});
 await page.screenshot({path:`${out}/${name[0]}-arrival.png`});
 await page.getByRole('button',{name:'Replay Journey',exact:true}).click();await expect(journey()).toHaveAttribute('data-simulation-id',new RegExp(`^(?!${id}$).+`));id=await journey().getAttribute('data-simulation-id');const replay=await state();expect(replay.progress).toBe(0);expect(coordinates(replay)).toEqual(replay.route[0]);
});}
await check('console is clean',async()=>expect(errors).toEqual([]));
}finally{await fs.writeFile(`${out}/browser.json`,JSON.stringify({results,errors,evidence},null,2));await browser.close();}
if(results.some(r=>!r.pass))process.exitCode=1;
