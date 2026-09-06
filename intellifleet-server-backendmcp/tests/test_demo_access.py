from datetime import timedelta
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import jwt
import pytest

from backend.config.config import Settings, settings
from backend.core.security import ALGORITHM, SECRET_KEY, create_access_token
from backend.database.database import init_db
from backend.planning.database import migrate_planning_schema
from backend.routes import auth
from backend.planning.routes import router as planning_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    migrate_planning_schema()
    def no_email(*args, **kwargs):
        raise AssertionError('Demo entry must not use SMTP')
    monkeypatch.setattr(auth, 'send_email', no_email)
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(planning_router)
    return TestClient(app)


def test_demo_flag_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv('DEMO_ACCESS_ENABLED', raising=False)
    assert Settings(_env_file=None).DEMO_ACCESS_ENABLED is False


def test_disabled_demo_access_does_not_create_user(client, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_ACCESS_ENABLED', False)
    assert client.post('/auth/demo-access').status_code == 403
    with sqlite3.connect('users.db') as conn:
        assert conn.execute('SELECT count(*) FROM users').fetchone()[0] == 0


def test_demo_access_reuses_user_and_returns_normal_protected_jwt(client, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_ACCESS_ENABLED', True)
    responses = [client.post('/auth/demo-access') for _ in range(2)]
    for response in responses:
        assert response.status_code == 200
        data = response.json()['data']
        assert data['user']['email'] == 'demo@unifleet.local'
        assert set(data['user']) == {'id', 'first_name', 'last_name', 'email'}
        claims = jwt.decode(data['token'], SECRET_KEY, algorithms=[ALGORITHM])
        assert claims['user_id'] == data['user']['id']
        assert 'admin' not in claims and 'password' not in claims
        protected = client.get('/planning/warehouse-capacity', headers={'Authorization':'Bearer '+data['token']})
        assert protected.status_code == 200
        assert protected.json() == {'warehouses': []}
    assert responses[0].json()['data']['user'] == responses[1].json()['data']['user']
    with sqlite3.connect('users.db') as conn:
        assert conn.execute('SELECT count(*) FROM users').fetchone()[0] == 1
        for table in ('warehouses', 'vehicles', 'nodes', 'nodes_air'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_demo_access_keeps_protected_route_authentication(client, monkeypatch):
    monkeypatch.setattr(settings, 'DEMO_ACCESS_ENABLED', True)
    assert client.get('/planning/warehouse-capacity').status_code == 401
    assert client.get('/planning/warehouse-capacity', headers={'Authorization':'Bearer invalid'}).status_code == 401
    expired = create_access_token({'user_id':1}, expires_delta=timedelta(seconds=-1))
    assert client.get('/planning/warehouse-capacity', headers={'Authorization':'Bearer '+expired}).status_code == 401
