"""Actual V2 multipart contract, authentication, browser CORS, and atomicity."""
from pathlib import Path
import csv
import io
import runpy
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.config.config import settings
from backend.database.database import init_db
from backend.planning.database import migrate_planning_schema
from backend.operations.data import DATA_DIR


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    migrate_planning_schema()
    monkeypatch.setattr(settings, 'DEMO_ACCESS_ENABLED', True)
    app = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'main.py'))['app']
    client = TestClient(app)
    auth = client.post('/auth/demo-access')
    assert auth.status_code == 200
    token = auth.json()['data']['token']
    client.headers.update({'Authorization': f'Bearer {token}',
                           'Origin': 'http://127.0.0.1:5178',
                           'ngrok-skip-browser-warning': 'true'})
    return client


def files():
    return {f'{name}_csv': (f'{name}.csv', (DATA_DIR / f'{name}.csv').read_bytes(), 'text/csv')
            for name in ('warehouse', 'vehicle', 'routes')}


def snapshot():
    with sqlite3.connect('users.db') as conn:
        return '\n'.join(conn.iterdump())


def assert_summary(client):
    for path, key, count in [('/warehouses', 'warehouses', 30),
                             ('/vehicles', 'vehicles', 97),
                             ('/route_session', 'routes', 72)]:
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert len(response.json()['data'][key]) == count


@pytest.mark.parametrize('origin', ['http://127.0.0.1:5178', 'http://localhost:5178',
                                    'http://127.0.0.1:5173', 'http://localhost:5173'])
def test_v2_browser_upload(api, origin):
    headers = {'Origin': origin}
    preflight = api.options('/upload-network', headers={**headers,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,content-type,ngrok-skip-browser-warning'})
    assert preflight.status_code == 200
    assert preflight.headers['access-control-allow-origin'] == origin
    assert preflight.headers['access-control-allow-credentials'] == 'true'
    result = api.post('/upload-network', files=files(), headers=headers)
    assert result.status_code == 200, result.text
    assert result.headers['access-control-allow-origin'] == origin
    assert {k: result.json()[k] for k in ('warehouses', 'vehicles', 'routes')} == {
        'warehouses': 30, 'vehicles': 97, 'routes': 72}
    assert_summary(api)


def test_auth_validation_and_transaction_preserve_network(api):
    assert api.post('/upload-network', files=files()).status_code == 200
    before = snapshot()
    response = api.post('/upload-network', files=files(), headers={'Authorization': ''})
    assert response.status_code == 401
    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5178'
    assert snapshot() == before
    for field, column in [('warehouse_csv', 'Name'), ('vehicle_csv', 'WarehouseName'), ('routes_csv', 'Destination')]:
        invalid = files()
        name, content, mime = invalid[field]
        records = list(csv.DictReader(io.StringIO(content.decode())))
        records[0][column] = 'UnknownWarehouse'
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
        invalid[field] = (name, stream.getvalue().encode(), mime)
        response = api.post('/upload-network', files=invalid)
        assert response.status_code == 422, response.text
        assert snapshot() == before
    # A write failure after deletion and warehouse insertion must roll back everything.
    with sqlite3.connect('users.db') as conn:
        conn.execute("CREATE TRIGGER fail_vehicle BEFORE INSERT ON vehicles BEGIN SELECT RAISE(ABORT, 'forced write failure'); END")
    before = snapshot()
    response = api.post('/upload-network', files=files())
    assert response.status_code == 500
    assert snapshot() == before
    assert_summary(api)


@pytest.mark.parametrize('content', [b'', b'\xff\xfe', b'a,b\n"unterminated'])
def test_malformed_csv_is_readable_validation_error(api, content):
    assert api.post('/upload-network', files=files()).status_code == 200
    before = snapshot()
    invalid = files()
    invalid['routes_csv'] = ('routes.csv', content, 'text/csv')
    response = api.post('/upload-network', files=invalid)
    assert response.status_code == 422
    assert 'valid UTF-8 CSV' in response.json()['detail']
    assert snapshot() == before
