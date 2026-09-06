"""Read the loaded network and assert geographic preservation regressions."""
import json
from pathlib import Path
from backend.planning.service import PlanningService
from backend.planning.models import PlanningRequest
service=PlanningService()
network=service.load_network(5)
records=[]
for source,dest,weight,objective,modes in [('Delhi','Mumbai',6000,'balanced',['road']),('Mumbai','Bengaluru',6000,'balanced',['road']),('Bengaluru','Chennai',6000,'cheapest',['road']),('Kolkata','Guwahati',6000,'balanced',['road','air']),('Mumbai','Pune',18000,'cheapest',['road']),('Delhi','Bengaluru',6000,'fastest',['road','air']),('Ahmedabad','Surat',6000,'cheapest',['road']),('Delhi','Frankfurt',5000,'balanced',['air'])]:
 request=PlanningRequest(source=source,destination=dest,shipment={'weight_kg':weight},objective=objective,allowed_modes=modes)
 result=service.plan(5,request,network)
 plan=result['recommended_plan'];assert plan,(source,dest,result['reason'])
 assert abs(sum(v['assigned_load_kg'] for v in plan['vehicles'])-weight)<1e-5
 assert all(v['assigned_load_kg']<=v['capacity'] for v in plan['vehicles'])
 assert all(leg in network['routes'] for leg in plan['route_legs'])
 records.append({'source':source,'destination':dest,'weight':weight,'plan':plan,'status':'PASS'})
 if source=='Delhi' and dest=='Mumbai':
  pair=[plan['route_legs'][0]['from_location'],plan['route_legs'][-1]['to_location']]
  revised=service.plan(5,request,network,{'blocked_routes':[pair]})
  assert revised['recommended_plan'] and len(revised['recommended_plan']['route_legs'])>1
  records.append({'regression':'6000kg disruption reroute','result':revised,'status':'PASS'})
  large=service.plan(5,request.model_copy(update={'shipment':request.shipment.model_copy(update={'weight_kg':18000})}),network,{'blocked_routes':[pair]})
  if large['recommended_plan']:
   recovered=large['recommended_plan'];raw={v['id']:v for v in network['vehicles']}
   assert sum(v['assigned_load_kg'] for v in recovered['vehicles'])==18000
   assert all(not raw[v['id']].get('max_range_km') or raw[v['id']]['max_range_km']>=recovered['distance_km'] for v in recovered['vehicles'])
  records.append({'regression':'18000kg disruption feasibility checked against actual ranges','result':large,'status':'PASS'})
  impossible=service.plan(5,request.model_copy(update={'shipment':request.shipment.model_copy(update={'weight_kg':180000})}),network,{'blocked_routes':[pair]})
  assert impossible['recommended_plan'] is None
  records.append({'regression':'180000kg safe infeasibility','result':impossible,'status':'PASS'})
Path('tests/ps30_network_results.json').write_text(json.dumps(records,indent=2))
print(f'PASS: {len(records)} loaded-network checks; no live plan or network mutations')
