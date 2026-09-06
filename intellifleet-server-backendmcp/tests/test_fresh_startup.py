"""Fresh-install schema and startup regressions; all databases are temporary."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from backend.database.database import init_db
from backend.planning.database import migrate_planning_schema
from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService


REQUIRED_TABLES = {
    'users', 'warehouses', 'warehouse_inventory', 'vehicles', 'nodes', 'nodes_air',
    'planning_scenarios', 'planning_plans', 'shipments', 'route_conditions',
}


def assert_empty_schema(db):
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert REQUIRED_TABLES <= tables
        assert 'storage_capacity' in {row[1] for row in conn.execute('PRAGMA table_info(warehouse_inventory)')}
        assert 'max_range_km' in {row[1] for row in conn.execute('PRAGMA table_info(vehicles)')}
        for table in REQUIRED_TABLES:
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_migration_creates_missing_database(tmp_path):
    db = tmp_path / 'new.db'
    assert not db.exists()
    migrate_planning_schema(str(db))
    assert_empty_schema(db)
    assert not (tmp_path / 'users.db').exists()  # Honor the supplied database path.


def test_migration_repairs_database_without_inventory_table(tmp_path):
    db = tmp_path / 'partial.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE installation_metadata (version TEXT)')
        conn.execute("INSERT INTO installation_metadata VALUES ('keep-me')")
    migrate_planning_schema(str(db))
    assert_empty_schema(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT version FROM installation_metadata').fetchone() == ('keep-me',)


def test_initialized_database_rows_survive_initialization_and_migration(tmp_path):
    db = tmp_path / 'existing.db'
    init_db(str(db))
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO users(id,first_name,last_name,email,password) VALUES(1,'Schema','Test','schema@example.invalid','fixture')")
        conn.execute("INSERT INTO warehouses(warehouse_id,user_id,country,city,node_type,name,address) VALUES(1,1,'Test','Origin','Hub','Existing warehouse','Fixture address')")
        conn.execute("INSERT INTO warehouse_inventory(user_id,warehouse_id,warehouse_name,inventory,reorder_level) VALUES(1,1,'Existing warehouse',123,7)")
        conn.execute("INSERT INTO vehicles(user_id,warehouse_id,type,label,capacity,current_location) VALUES(1,1,'truck','Existing vehicle',500,'Existing warehouse')")
        conn.execute("INSERT INTO nodes(user_id,route_id,from_location,to_location,distance,duration,cost) VALUES(1,1,'Existing warehouse','Destination',10,1,50)")
    migrate_planning_schema(str(db))
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE warehouse_inventory SET storage_capacity=456, reserved_inventory=12')
        before = '\n'.join(conn.iterdump())
    init_db(str(db))
    migrate_planning_schema(str(db))
    with sqlite3.connect(db) as conn:
        assert '\n'.join(conn.iterdump()) == before
        assert conn.execute('SELECT inventory,storage_capacity,reserved_inventory FROM warehouse_inventory').fetchone() == (123,456,12)


def test_migration_twice_is_idempotent(tmp_path):
    db = tmp_path / 'repeat.db'
    migrate_planning_schema(str(db))
    with sqlite3.connect(db) as conn:
        before = '\n'.join(conn.iterdump())
    migrate_planning_schema(str(db))
    with sqlite3.connect(db) as conn:
        assert '\n'.join(conn.iterdump()) == before
    assert_empty_schema(db)


def test_empty_network_returns_upload_guidance(tmp_path):
    service = PlanningService(str(tmp_path / 'empty.db'))
    result = service.plan(1, PlanningRequest(source='Origin', destination='Destination', shipment={'weight_kg':100}))
    assert result['recommended_plan'] is None
    assert result['candidate_plans'] == []
    assert result['feasibility']['constraint'] == 'network_not_loaded'
    assert 'Upload' in result['reason']


def test_fresh_process_import_lifespan_health_and_empty_planner(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = '''
import main
print('IMPORT OK')
from fastapi.testclient import TestClient
from backend.routes.auth import get_current_user
main.app.dependency_overrides[get_current_user] = lambda: {'user_id': 1}
with TestClient(main.app) as client:
    response = client.get('/health')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'healthy'
    result = client.post('/planning/plans', json={'source':'Origin','destination':'Destination','shipment':{'weight_kg':100}})
    assert result.status_code == 200, result.text
    assert result.json()['feasibility']['constraint'] == 'network_not_loaded'
print('HEALTH AND EMPTY PLANNER OK')
'''
    process = subprocess.run([sys.executable, '-c', script], cwd=tmp_path,
        env={**os.environ, 'PYTHONPATH': str(root),
             'SECRET_KEY': 'fresh-startup-test-only-not-a-deployment-secret'},
        capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    assert 'IMPORT OK' in process.stdout
    assert 'HEALTH AND EMPTY PLANNER OK' in process.stdout
    assert_empty_schema(tmp_path / 'users.db')
