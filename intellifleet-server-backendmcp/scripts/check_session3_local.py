"""Session 3 loopback QA; run after the two existing local checks."""
import json
import time
import httpx


def main():
    with httpx.Client(base_url='http://127.0.0.1:4208',timeout=60) as client:
        auth=client.post('/auth/demo-access');auth.raise_for_status()
        client.headers['Authorization']='Bearer '+auth.json()['data']['token']
        assert client.get('/operations/alerts').json()['delivery_enabled'] is False
        response=client.get('/operations/control-tower/runs',params={'limit':200});response.raise_for_status()
        runs=response.json()['runs'];assert len(runs)==38
        assert all(r['schedule']['lane']!='UNSUPPORTED_FORMULA' for r in runs)
        selected=next(r for r in runs if r['schedule']['lane']=='CJB-BLR' and r['schedule']['mode']=='AIR')
        source=selected['schedule']['source'].copy();s=selected['schedule']
        response=client.post(f'/operations/control-tower/runs/{selected["run_id"]}/simulation',json={
            'origin_station':s['origin_station'],'gateway':s['gateway'],'simulation_date':selected['service_date'],
            'shipment_ready_datetime':selected['service_date']+'T00:00:00+05:30','demo_playback':True,'speed':120})
        response.raise_for_status();started=response.json()
        assert started['location_source']=='SYNTHETIC_TELEMETRY' and started['latest_location']
        time.sleep(.5)
        response=client.get(f'/operations/control-tower/runs/{selected["run_id"]}');response.raise_for_status()
        active=response.json();assert active['movement']['progress']>0
        assert active['schedule']['source']==source
        observed={}
        for name,origin,destination,modes,weight in [('ground','Ahmedabad','Bengaluru',['road'],6000),('candidates','Mumbai','Chennai',['road','air','multimodal'],5000),('gag','Jaipur','Hyderabad',['multimodal'],1000)]:
            response=client.post('/planning/plans',json={'source':origin,'destination':destination,'allowed_modes':modes,'shipment':{'weight_kg':weight},'objective':'balanced'})
            response.raise_for_status();result=response.json();p=result['recommended_plan'];assert p
            observed[name]={'mode':p['mode'],'cost':p['operational_cost'],'hours':p['duration_hours'],'risk':p['risk_score'],'leg_modes':[leg['route_type'] for leg in p['route_legs']],'candidate_modes':[c['mode'] for c in result['candidate_plans']]}
        print(json.dumps({'passed':True,'runs':38,'surface_formula_display':'resolved','synthetic_air_progress':active['movement']['progress'],'source_cells_unchanged':True,'plans':observed,'emails_sent':False}))


if __name__=='__main__':main()
