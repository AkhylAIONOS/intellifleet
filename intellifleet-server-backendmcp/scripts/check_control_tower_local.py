"""HTTP smoke for the isolated local launcher only; never sends email."""
import json
from uuid import uuid4
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx


def main():
    with httpx.Client(base_url='http://127.0.0.1:4208',timeout=30) as client:
        assert client.get('/operations/control-tower/runs').status_code in (401,403)
        response=client.post('/auth/demo-access');response.raise_for_status()
        client.headers['Authorization']='Bearer '+response.json()['data']['token']
        client.headers['X-UniFleet-Demo-Session-Id']=str(uuid4())
        # Refuse to run against a server with delivery enabled.
        alerts=client.get('/operations/alerts');alerts.raise_for_status()
        assert alerts.json()['delivery_enabled'] is False
        today=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()
        imported=client.post('/operations/control-tower/import',json={'service_date':today})
        imported.raise_for_status();runs=imported.json()['runs']
        assert runs and all(r['schedule']['data_source']=='FEDEX_SOURCE' for r in runs)
        row=next(r for r in runs if r['schedule']['valid'])
        run_id=row['run_id']
        response=client.put('/operations/critical-lanes/'+run_id,json={'critical':True})
        response.raise_for_status();assert response.json()['critical'] is True
        now=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
        event={'event_id':'local-smoke-departure','event_type':'DEPARTURE','event_at':now,'source':'FEDEX_SCAN'}
        assert client.post(f'/operations/control-tower/runs/{run_id}/events',json=event).status_code==503
        event['source']='SYNTHETIC_TELEMETRY'
        response=client.post(f'/operations/control-tower/runs/{run_id}/events',json=event)
        response.raise_for_status()
        response=client.post('/operations/cons/events',json={'con_number':'CT-LOCAL-SYNTHETIC','run_id':run_id,
            'event_id':'local-smoke-con','event_at':now,'source':'SYNTHETIC_TELEMETRY'})
        response.raise_for_status()
        response=client.get('/operations/cons/CT-LOCAL-SYNTHETIC');response.raise_for_status()
        assert response.json()['run']['run_id']==run_id
        summary=client.get('/operations/control-tower/summary',params={'service_date':today})
        summary.raise_for_status()
        print(json.dumps({'passed':True,'summary':summary.json(),'con_source':'SYNTHETIC_TELEMETRY','email_delivery':False}))


if __name__=='__main__':
    main()
