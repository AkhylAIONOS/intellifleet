"""Real Azure through authenticated /mcp-agent, isolated copy of loaded data.
No LLM, MCP, business engine, or HTTP endpoint is mocked.
"""
import asyncio,json,os,sqlite3,sys,tempfile,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
from backend.config.config import settings
FOCUS='--mitigation-only' in sys.argv
REPORT=ROOT/('tests/ps30_mitigation_live_results.json' if FOCUS else 'tests/ps30_live_results.json')

async def main():
    folder=Path(tempfile.mkdtemp(prefix='ps30-live-'))
    user=100000+uuid.uuid4().int%100000000
    with sqlite3.connect(f'file:{ROOT / "users.db"}?mode=ro',uri=True) as src, sqlite3.connect(folder/'users.db') as dst:
        src.backup(dst)
        for (table,) in dst.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            columns=[r[1] for r in dst.execute(f'PRAGMA table_info("{table}")')]
            if 'user_id' in columns:dst.execute(f'UPDATE "{table}" SET user_id=? WHERE user_id=5',(user,))
        dst.execute('UPDATE users SET id=? WHERE id=5',(user,))
    os.chdir(folder)
    from main import app
    from backend.config.redis import delete_data,get_active_planning_context
    from backend.core.security import create_access_token
    from backend.planning.service import PlanningService
    records=[]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',timeout=180) as client:
            async def ask(ps,prompt):
                start=time.perf_counter()
                try:
                    response=await client.post('/mcp-agent',headers={'Authorization':'Bearer '+create_access_token({'user_id':user})},json={'message':prompt})
                    body=response.json()
                    record={'ps':ps,'prompt':prompt,'http':response.status_code,'body':body,'context':await get_active_planning_context(user),'seconds':round(time.perf_counter()-start,2)}
                except Exception as exc:
                    record={'ps':ps,'prompt':prompt,'error':str(exc),'seconds':round(time.perf_counter()-start,2)}
                records.append(record)
                REPORT.write_text(json.dumps({'provider':settings.AI_PROVIDER,'dataset':'isolated SQLite copy of user 5 loaded network','records':records},indent=2))
                data=((record.get('body',{}).get('actions') or [{}])[0].get('data') or {})
                print(json.dumps({'ps':ps,'success':record.get('body',{}).get('success'),'operation':data.get('planning_operation'),'has_result':bool(data),'seconds':record['seconds'],'error':record.get('error')}),flush=True)
                return data
            cases=[
                (1,'Plan 6000 kg from Mumbai to Bengaluru using Ground.'),
                (2,'Find the cheapest feasible route for 6000 kg from Bengaluru to Chennai.'),
                (3,'Find the fastest feasible route for 6000 kg from Delhi to Bengaluru.'),
                (4,'Plan 6000 kg from Ahmedabad to Surat balancing cost, time and risk.'),
                (5,'Compare Ground and Express for 6000 kg from Kolkata to Guwahati.'),
                (6,'Plan 6000 kg Mumbai to Pune with a 20% margin.'),
                (11,'Plan 18000 kg Mumbai to Pune using Ground and show exact assigned loads.'),
                (12,'Should I use road or air for 6000 kg from Mumbai to Bengaluru?'),
                (14,'Use alternative warehouses to fulfil 5 units totaling 500 kg to Mysuru using the cheapest allocation.'),
                (15,'Combine multiple warehouses to fulfil 20 units totaling 200 kg to Mumbai using cheapest allocation.'),
                (16,'Show inventory, available storage and utilization for Bengaluru South Hub.'),
                (17,'Consolidate shipment A of 1000 kg and shipment B of 1200 kg both from Mumbai to Pune.'),
                (18,'Optimize a multi-stop 3000 kg shipment from Delhi to Mumbai stopping at Jaipur and Ahmedabad.'),
                (24,'Evaluate facility A at latitude 26.9 longitude 75.8 with capacity 5000 against demand 1000 at latitude 28.6 longitude 77.2. Do not assume construction costs.'),
                (25,'Estimate expansion cost for candidate Jaipur at latitude 26.9 longitude 75.8 with capacity 5000, facility cost 1000000, warehouse cost 200000 and transport cost per km 10 against demand 1000 at Delhi latitude 28.6 longitude 77.2.'),
                (26,'Plan 5000 kg from Delhi to Frankfurt using the best feasible international option.'),
            ]
            try:
                if FOCUS:
                    await ask(10,'Plan 6000 kg from Mumbai to Bengaluru using Ground.')
                    await ask(10,'Assume disruption risk increases by 0.2. Mitigate and replan this shipment with a baseline comparison.')
                    return
                for ps,prompt in cases:
                    await delete_data(user);await ask(ps,prompt)
                await delete_data(user)
                await ask(7,'Plan 6000 kg from Delhi to Mumbai using Ground.')
                await ask(7,'The direct route is unavailable. Replan this shipment and show exact changes.')
                await ask(10,'Assume disruption risk increases by 0.2. Mitigate and replan this shipment with a baseline comparison.')
                await delete_data(user)
                await ask(13,'Plan 6000 kg from Mumbai to Bengaluru using Ground.')
                context=await get_active_planning_context(user)
                if context and context.get('assigned_vehicles'):
                    from datetime import datetime,timedelta,timezone
                    start=datetime.now(timezone.utc)+timedelta(hours=1)
                    label=context['assigned_vehicles'][0]['label']
                    PlanningService().schedule_shipment(user,{'shipment_id':'PS22-fixture','source':context['source'],'destination':context['destination'],'weight_kg':1000,'quantity':1,'assigned_vehicle_labels':[label],'scheduled_start':start.isoformat(),'scheduled_end':(start+timedelta(hours=30)).isoformat(),'deadline':(start+timedelta(hours=32)).isoformat()})
                    await ask(22,f'{label} is delayed by 6 hours. Show affected future shipments and replan them.')
                await ask(13,'The assigned truck broke down after dispatch. Find the best way to complete the shipment.')
                await ask(13,'It broke down at Mumbai. Recover the shipment from there.')
                await delete_data(user)
                for ps,prompt in [(30,'Plan 6000 kg from Mumbai to Bengaluru.'),(27,'Why did you choose that option?'),(23,'What if I need it 8 hours earlier?'),(12,'Can air meet that?'),(16,'What warehouse are we using?'),(20,'What happens if fuel cost increases by 20%?'),(29,'Keep it as draft.'),(21,'Compare it with my baseline.'),(29,'Apply it.'),(20,'Create another draft with fuel cost increased by 10%.'),(29,'Discard it.')]:
                    await ask(ps,prompt)
            finally:await delete_data(user)
    print('Evidence: '+str(REPORT),flush=True)
if __name__=='__main__':asyncio.run(main())
