"""The UI's real runs endpoint over the unchanged 28 supplied Surface rows."""
from datetime import date
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.control_tower import routes
from backend.control_tower.service import ControlTower
from backend.fedex.importer import load_schedules
from backend.routes.auth import get_current_user


def test_delhi_aliases_ui_endpoint_and_source_preservation(tmp_path,monkeypatch):
    tower=ControlTower(str(tmp_path/'ct.db'));day=date(2030,1,1)
    original=tower.import_network(1,load_schedules(),day)
    monkeypatch.setattr(routes,'service',tower)
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    client=TestClient(app)
    def search(query):
        r=client.get('/operations/control-tower/runs',params={'service_date':str(day),'mode':'SURFACE','search':query,'limit':100})
        assert r.status_code==200
        return r.json()
    baseline=search('');assert baseline['total']==28
    delgw=search('DELGW');ndls=search('NDLS');delhi=search('Delhi')
    assert delgw['total']>0 and ndls['total']>0 and delhi['total']>0
    ids=lambda result:{r['run_id'] for r in result['runs']}
    assert ids(delgw)|ids(ndls)<=ids(delhi)
    assert ids(search('delhi'))==ids(delhi)==ids(search(' DEL '))
    assert any(r['schedule']['lane']=='AGRGA-DELGW' for r in delhi['runs'])
    assert search('unrelated-atlantis-query')=={'runs':[],'total':0,'source':'FEDEX_SOURCE'}
    assert ids(search(''))==ids(baseline)
    assert [r['schedule'] for r in tower.runs(1,day)]==[r['schedule'] for r in original]
