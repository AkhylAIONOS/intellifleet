"""Read/write QA only against the isolated loopback launcher; no emails or real scans."""
from pathlib import Path
import json
import httpx


def main():
    data=Path(__file__).resolve().parents[2]/'intellifleet-web-main/frontendmain/public/synthetic_v2'
    with httpx.Client(base_url='http://127.0.0.1:4208',timeout=60) as client:
        auth=client.post('/auth/demo-access');auth.raise_for_status()
        client.headers['Authorization']='Bearer '+auth.json()['data']['token']
        alerts=client.get('/operations/alerts');alerts.raise_for_status()
        assert alerts.json()['delivery_enabled'] is False
        before=client.get('/operations/control-tower/runs',params={'limit':200});before.raise_for_status()
        source={r['run_id']:r['schedule']['source'] for r in before.json()['runs']}
        assert len(source)==38
        upload=client.post('/upload-network',files={f'{name}_csv':(name+'.csv',(data/(name+'.csv')).read_bytes(),'text/csv') for name in ['warehouse','vehicle','routes']})
        upload.raise_for_status();counts=upload.json()
        assert (counts['warehouses'],counts['vehicles'],counts['routes'])==(30,97,72)
        assert counts['processing_time_ms']>=0
        plans={}
        for name,modes,origin,destination,weight in [
            ('ground',['road'],'Mumbai','Bengaluru',6000),
            ('air',['air'],'Delhi','Mumbai',6000),
            ('multimodal',['multimodal'],'Jaipur','Hyderabad',1000)]:
            response=client.post('/planning/plans',json={'source':origin,'destination':destination,'shipment':{'weight_kg':weight},'allowed_modes':modes,'objective':'balanced'})
            response.raise_for_status();body=response.json();plan=body.get('recommended_plan')
            assert plan,body.get('reason')
            assert 0<=plan['risk_score']<=1
            assert all(0<=value<=1 for value in plan['risk_breakdown'].values())
            if name=='air':assert plan['cost_breakdown']['air_cost']==0
            plans[name]={'mode':plan['mode'],'legs':len(plan['route_legs']),'risk':plan['risk_score'],'cost':plan['operational_cost']}
        after=client.get('/operations/control-tower/runs',params={'limit':200});after.raise_for_status()
        assert {r['run_id']:r['schedule']['source'] for r in after.json()['runs']}==source
        for mode,count in [('AIR',10),('SURFACE',28)]:
            response=client.get('/operations/control-tower/runs',params={'mode':mode,'limit':25});response.raise_for_status()
            assert response.json()['total']==count
        response=client.post('/mcp-agent',json={'message':'Which critical lanes are currently at risk?'})
        response.raise_for_status();assert response.json()['success']
        response=client.post('/mcp-agent',json={'message':'Find CON CT-LOCAL-SYNTHETIC'})
        response.raise_for_status();assert response.json()['actions'][0]['type']=='focus_operational_run'
        response=client.get('/operations/cons/NOT-A-REAL-CON');assert response.status_code==404
        print(json.dumps({'passed':True,'upload_counts':{k:counts[k] for k in ['warehouses','vehicles','routes','processing_time_ms']},'plans':plans,'operational_source_cells_unchanged':True,'operational_runs':38,'email_delivery':False}))


if __name__=='__main__':
    main()
