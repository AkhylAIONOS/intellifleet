from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from aioredis.exceptions import ConnectionError
from backend.api import chat_api
from backend.routes.auth import get_current_user


def client(monkeypatch):
    app=FastAPI();app.include_router(chat_api.router)
    app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5178'])
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    async def unavailable(*args):raise ConnectionError('test-only unavailable dependency')
    monkeypatch.setattr(chat_api,'get_active_planning_context',unavailable)
    return TestClient(app,raise_server_exceptions=False)


def test_missing_context_storage_returns_readable_503_with_cors(monkeypatch):
    c=client(monkeypatch)
    for message in ['Plan a 6,000 kg shipment from Mumbai to Bengaluru using the best available option.', 'Why did you choose this option?']:
        r=c.post('/mcp-agent',json={'message':message},headers={'Origin':'http://127.0.0.1:5178'})
        assert r.status_code==503
        assert r.headers['access-control-allow-origin']=='http://127.0.0.1:5178'
        assert 'AI chat storage is temporarily unavailable' in r.json()['detail']
        assert 'test-only' not in r.text


def test_real_gps_question_bypasses_unavailable_context_and_model(monkeypatch):
    r=client(monkeypatch).post('/mcp-agent',json={'message':'Tell me the exact live FedEx GPS location of this CON right now.'})
    assert r.status_code==200
    body=r.json();assert body['success'] and body['actions']==[]
    assert 'Real live FedEx GPS is unavailable' in body['response']
    assert 'SYNTHETIC_TELEMETRY' in body['response']
