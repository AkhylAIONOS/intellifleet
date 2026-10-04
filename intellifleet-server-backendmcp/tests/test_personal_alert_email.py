import asyncio
import json
from uuid import uuid4
from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.control_tower import routes
from backend.routes.auth import get_current_user
from test_control_tower import tower, load, event, NOW


def test_personal_configuration(tower,monkeypatch):
    app=FastAPI();app.include_router(routes.router)
    monkeypatch.setattr(routes,'service',tower)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    c=TestClient(app);path='/operations/alerts/recipients'
    a={'X-UniFleet-Demo-Session-Id':str(uuid4())};b={'X-UniFleet-Demo-Session-Id':str(uuid4())}
    assert c.get(path).status_code==422
    assert c.get(path,headers={'X-UniFleet-Demo-Session-Id':'bad'}).status_code==422
    for h,email in [(a,'a@example.com'),(b,'b@example.com')]:
        assert c.put(path,headers=h,json={'emails':[email]}).json()=={'emails':[email]}
        assert c.get(path,headers=h).json()=={'emails':[email]}
    assert c.put(path,headers=a,json={'emails':['new@example.com']}).json()=={'emails':['new@example.com']}
    for emails in [['bad'],['one@example.com','two@example.com']]:
        assert c.put(path,headers=a,json={'emails':emails}).status_code==422
    assert c.get(path,headers=a).json()=={'emails':['new@example.com']}
    assert c.get(path,headers=b).json()=={'emails':['b@example.com']}
    assert c.put(path,headers=a,json={'emails':[]}).json()=={'emails':[]}
    assert c.get(path,headers=a).json()=={'emails':[]}
    assert c.get(path,headers=b).json()=={'emails':['b@example.com']}
    assert tower.personal_email(2,a['X-UniFleet-Demo-Session-Id']) is None


def test_personal_snapshot_history_polling_retry(tower,monkeypatch):
    a,b=str(uuid4()),str(uuid4());rid=load(tower)[0]['run_id']
    tower.personal_email(1,a,'old@example.com');tower.personal_email(1,a,'new@example.com');tower.personal_email(1,b,'b@example.com')
    with tower.db() as conn:conn.execute('INSERT INTO ct_recipients VALUES(?,?,1)',(1,'legacy@example.com'))
    tower.event(1,rid,event(at=NOW-timedelta(hours=1)))
    delay=event('ETA_UPDATE','delay',NOW,current_eta=(NOW+timedelta(hours=3)).isoformat())
    tower.event(1,rid,delay);tower.event(1,rid,delay);tower.observe(1);tower.observe(1)
    rows=tower.alerts(1);assert len(rows)==2
    assert {tuple(json.loads(r['recipients_json'])) for r in rows}=={('new@example.com',),('b@example.com',)}
    for identity in [a,b]:
        history=tower.personal_alerts(1,identity)
        assert len(history)==1 and 'recipients_json' not in history[0] and 'payload_json' not in history[0]
    assert tower.personal_alerts(1,str(uuid4()))==[]
    async def fail(*args):raise RuntimeError('private-secret')
    asyncio.run(tower.deliver(sender=fail,enabled=False));assert all(r['attempts']==0 for r in tower.alerts(1))
    tower.clock=lambda:NOW+timedelta(minutes=6)
    asyncio.run(tower.deliver(sender=fail,enabled=True))
    assert all(r['status']=='RETRY' and 'private-secret' not in r['last_error'] for r in tower.alerts(1))
    sent=[]
    async def sender(*args):sent.append(args[0])
    tower.clock=lambda:NOW+timedelta(minutes=10)
    asyncio.run(tower.deliver(sender=sender,enabled=True));asyncio.run(tower.deliver(sender=sender,enabled=True))
    assert sorted(sent)==['b@example.com','new@example.com']
