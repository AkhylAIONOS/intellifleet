import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const out=process.env.UNIFLEET_QA_OUTPUT||path.resolve('../../qa/client-network');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1600,height:1000},timezoneId:'Asia/Kolkata'});
const page=await context.newPage();const results=[],errors=[],requests=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(r.url().includes(':4228'))requests.push(new URL(r.url()).pathname);});
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true}).click();
const capture=async name=>{await page.locator('.leaflet-tile-loaded').first().waitFor({state:'visible',timeout:3000}).catch(()=>{});await page.screenshot({path:`${out}/${name}.png`,fullPage:true});};
async function check(name,fn){try{await fn();results.push({name,pass:true});console.log('PASS',name);}catch(e){results.push({name,pass:false,error:e.message.slice(0,1500)});console.log('FAIL',name,e.message.slice(0,500));await capture(`failure-${results.length}`);}}
async function api(url,data,method='get'){return page.evaluate(async({url,data,method})=>{const {default:client}=await import('/src/api/client.ts');try{const r=await client.request({url,data,method});return {status:r.status,data:r.data};}catch(e){return {status:e.response?.status,data:e.response?.data};}},{url,data,method});}
let model,plans,runs;
try{
await check('Login and workbook dashboard',async()=>{
 await page.goto('http://127.0.0.1:5198');await page.getByLabel('Name',{exact:true}).fill('Client Network Review');await page.getByLabel('Email',{exact:true}).fill('client-network-review@example.com');await page.getByRole('button',{name:'Continue to UniFleet'}).click();
 await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
 model=(await api('/client-network')).data;expect(model.summary.client_services).toBe(38);expect(model.summary.client_nodes).toBe(34);expect(model.summary.generated_resources).toBe(40);expect(model.summary.simulated_shipments).toBe(320);
 await expect(page.getByLabel('Client network overview')).toContainText('320');await capture('01-dashboard');
});
await check('Network Overview supplied nodes services and resources',async()=>{
 await nav('Planning');await page.getByRole('navigation',{name:'Planning sections'}).getByRole('button',{name:'Network Overview'}).click();await expect(page.getByLabel('Client network overview')).toContainText('6E 5355');await expect(page.getByLabel('Client network overview').locator('tbody tr')).toHaveCount(38);await expect(page.locator('input[type=file]')).toHaveCount(0);await capture('05-network-overview');
});
await check('CJB 2000kg Planning and only two legitimate plans',async()=>{
 await page.getByRole('navigation',{name:'Planning sections'}).getByRole('button',{name:'Planner',exact:true}).click();
 await page.getByLabel('Source',{exact:true}).fill('CJBMB');await page.getByLabel('Destination',{exact:true}).fill('BLRGW');await page.getByRole('spinbutton',{name:'Weight kg',exact:true}).fill('2000');
 const response=page.waitForResponse(r=>r.url().endsWith('/planning/plans'));await page.getByRole('button',{name:'Calculate Plan',exact:true}).click();plans=await(await response).json();expect(plans.candidate_plans.length).toBe(2);expect(plans.candidate_plans.map(p=>p.client_service).sort()).toEqual(['6E 5355','TATA 407']);await expect(page.locator('.plan-options button')).toHaveCount(2);await capture('02-planning');
 for(let i=0;i<2;i++){await page.locator('.plan-options button').nth(i).click();await capture(`03-plan-${i===0?'a':'b'}`);}
});
await check('What-if comparison fuel calculation',async()=>{
 await page.getByText('What-if scenario controls',{exact:true}).click();const response=page.waitForResponse(r=>r.url().endsWith('/planning/scenarios'));await page.getByRole('button',{name:'Run What-if Scenario'}).click();const value=await(await response).json();expect(value.scenario.recommended_plan).toBeTruthy();await expect(page.getByText('Draft What-if Scenario',{exact:true})).toBeVisible();await capture('12-what-if-comparison');
});
await check('Schedules source-only cutoff and midnight',async()=>{
 await page.getByRole('navigation',{name:'Planning sections'}).getByRole('button',{name:'Schedules',exact:true}).click();
 const source=page.getByLabel('Schedule source');expect(await source.locator('option').allTextContents()).toEqual(['Client Network Plan']);
 await page.getByLabel(/Origin Station/).selectOption('CJBMB');await page.getByLabel(/^Gateway/).selectOption('BLRGW');await page.getByLabel(/Shipment Ready Time/).selectOption('17:00');
 await page.getByRole('button',{name:'Evaluate Cutoffs'}).click();await expect(page.getByText(/AIR \/ 1 \/ 6E 5355/).first()).toBeVisible();await capture('04-schedules');
});
await check('Live Operations only supplied runs',async()=>{
 await nav('Live Operations');const response=page.waitForResponse(r=>r.url().endsWith('/operations/control-tower/import'));await page.getByRole('button',{name:'Import client workbook'}).click();runs=(await(await response).json()).runs;
 await expect(page.locator('.operations-table tbody tr')).toHaveCount(38);expect(new Set(runs.map(r=>r.schedule_id))).toEqual(new Set(model.schedules.map(s=>s.schedule_id)));await capture('06-live-operations');
});
for(const [mode,name] of [['AIR','07-selected-air-run'],['SURFACE','08-selected-surface-run']])await check(`Selected ${mode} source schedule and generated resource`,async()=>{
 const selected=runs.find(r=>r.schedule.origin_station==='CJBMB'&&r.schedule.gateway==='BLRGW'&&r.schedule.mode===mode);
 const row=page.locator('.operations-table tbody tr').filter({hasText:selected.schedule.lane}).filter({hasText:selected.schedule.service});await row.getByRole('button').first().click();await expect(page.getByLabel('Operational run details')).toContainText('Simulation resources & load');await expect(page.getByLabel('Operational run details')).toContainText(mode==='AIR'?'12,000':'2,500');await capture(name);
});
await check('AI planning comparison and flight disruption through UI',async()=>{
 await nav('Planning');await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'AI Chat',exact:true}).click();
 const input=page.locator('.chat-input textarea, .chat-input-container textarea, textarea').first();
 async function send(message){await input.fill(message);const response=page.waitForResponse(r=>r.url().endsWith('/mcp-agent'));await input.press('Enter');return (await(await response).json());}
 const first=await send('Plan 2,000 kg from CJBMB to BLRGW.');expect(first.planning_result.candidate_plans.length).toBe(2);await capture('09-ai-planning');
 await send('Compare Air and Surface.');const blocked=await send('What if 6E 5355 becomes unavailable?');expect(blocked.planning_result.candidate_plans.map(p=>p.client_service)).toEqual(['TATA 407']);await capture('10-ai-disruption');
 const broken=await send('The assigned Surface vehicle breaks down.');expect(broken.recovery.replacement_vehicles).toEqual([]);await expect(page.getByText(/No available same-service resource/)).toBeVisible();await capture('11-breakdown-recovery');
});
await check('No legacy topology workflow remains and auth still protects APIs',async()=>{
 for(const url of ['/upload-network','/upload_csv','/upload-routes-json'])expect((await api(url,{},'post')).status).toBe(404);
 expect((await api('/operations/movements/initialize',{},'post')).status).toBe(410);
 expect((await api('/operations/schedules/import',{},'post')).status).toBe(422);
 expect((await api('/auth/users')).status).toBe(403);
 expect(requests.some(p=>p.includes('synthetic_v2'))).toBe(false);
 await page.setViewportSize({width:1280,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Logout',exact:true}).click();await expect(page.getByRole('button',{name:'Continue to UniFleet'})).toBeVisible();expect(await page.evaluate(()=>localStorage.getItem('authToken'))).toBeNull();
});
}finally{await fs.writeFile(`${out}/browser-results.json`,JSON.stringify({results,errors,requests,summary:model?.summary},null,2));await browser.close();}
if(results.some(r=>!r.pass)||errors.length)process.exitCode=1;
