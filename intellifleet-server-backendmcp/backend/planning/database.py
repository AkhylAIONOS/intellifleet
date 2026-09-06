import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from backend.database.database import initialize_base_schema


def migrate_planning_schema(db_path: str = "users.db") -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        # The planning router can instantiate its service before app lifespan.
        # Reuse the canonical schema, including on a fresh or partial database.
        initialize_base_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(warehouse_inventory)")}
        for name, definition in {
            "storage_capacity": "REAL NOT NULL DEFAULT 0",
            "reserved_inventory": "REAL NOT NULL DEFAULT 0",
            "handling_cost": "REAL NOT NULL DEFAULT 0",
            "fixed_operating_cost": "REAL NOT NULL DEFAULT 0",
            "reliability": "REAL NOT NULL DEFAULT 0.9",
            "disruption_risk": "REAL NOT NULL DEFAULT 0",
            "nearest_airport_iata": "TEXT",
            "airport_distance_km": "REAL",
            "region": "TEXT",
            "annual_demand_units": "REAL",
            "primary_sku": "TEXT",
        }.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE warehouse_inventory ADD COLUMN {name} {definition}")
        vehicle_columns = {row[1] for row in conn.execute("PRAGMA table_info(vehicles)")}
        for name, definition in {
            "cost_per_km": "REAL NOT NULL DEFAULT 0",
            "reliability": "REAL NOT NULL DEFAULT 0.9",
            "compatible_modes": "TEXT",
            "cost_per_hour": "REAL NOT NULL DEFAULT 0",
            "fixed_dispatch_cost": "REAL NOT NULL DEFAULT 0",
            "avg_speed_kmph": "REAL",
            "breakdown_risk": "REAL NOT NULL DEFAULT 0",
            "available_from": "TEXT",
            "available_until": "TEXT",
            "max_range_km": "REAL",
            "loading_time_min": "REAL NOT NULL DEFAULT 0",
            "unloading_time_min": "REAL NOT NULL DEFAULT 0",
            "co2_kg_per_km": "REAL NOT NULL DEFAULT 0",
            "express_eligible": "INTEGER NOT NULL DEFAULT 0",
            "refrigerated": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in vehicle_columns:
                conn.execute(f"ALTER TABLE vehicles ADD COLUMN {name} {definition}")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS planning_scenarios (
            scenario_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, status TEXT NOT NULL,
            request_json TEXT NOT NULL, changes_json TEXT NOT NULL,
            baseline_json TEXT NOT NULL, scenario_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS planning_plans (
            plan_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, scenario_id TEXT,
            status TEXT NOT NULL, plan_json TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS shipments (
            shipment_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, source TEXT NOT NULL,
            destination TEXT NOT NULL, weight_kg REAL NOT NULL, quantity INTEGER NOT NULL,
            sku TEXT, deadline TEXT, status TEXT NOT NULL DEFAULT 'planned',
            assigned_vehicle_ids TEXT, route_id INTEGER, scheduled_start TEXT,
            scheduled_end TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS route_conditions (
            user_id INTEGER NOT NULL, route_id INTEGER NOT NULL, reliability REAL NOT NULL DEFAULT .9,
            weather_risk REAL NOT NULL DEFAULT 0, operational_risk REAL NOT NULL DEFAULT 0,
            toll_cost REAL NOT NULL DEFAULT 0, handling_cost REAL NOT NULL DEFAULT 0,
            fuel_cost REAL NOT NULL DEFAULT 0, air_cost REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, route_id)
        );
        CREATE INDEX IF NOT EXISTS idx_scenarios_user_status ON planning_scenarios(user_id,status);
        CREATE INDEX IF NOT EXISTS idx_plans_user_status ON planning_plans(user_id,status);
        CREATE INDEX IF NOT EXISTS idx_shipments_user_start ON shipments(user_id,scheduled_start);
        CREATE INDEX IF NOT EXISTS idx_shipments_vehicle ON shipments(user_id,assigned_vehicle_ids);
        CREATE INDEX IF NOT EXISTS idx_route_conditions_user ON route_conditions(user_id);
        """)
        scenario_columns = {row[1] for row in conn.execute("PRAGMA table_info(planning_scenarios)")}
        if "applied_at" not in scenario_columns:
            conn.execute("ALTER TABLE planning_scenarios ADD COLUMN applied_at TEXT")
        route_columns = {row[1] for row in conn.execute("PRAGMA table_info(route_conditions)")}
        for name, definition in {
            "capacity_per_day_kg": "REAL", "current_utilization_pct": "REAL",
            "service_class": "TEXT", "express_eligible": "INTEGER NOT NULL DEFAULT 0",
            "sla_hours": "REAL", "carbon_kg": "REAL", "status": "TEXT NOT NULL DEFAULT 'active'",
            "notes": "TEXT", "base_transport_cost": "REAL NOT NULL DEFAULT 0",
        }.items():
            if name not in route_columns:
                conn.execute(f"ALTER TABLE route_conditions ADD COLUMN {name} {definition}")


def save_scenario(db_path: str, user_id: int, record: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("""INSERT INTO planning_scenarios
            (scenario_id,user_id,status,request_json,changes_json,baseline_json,scenario_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""", (
            record["scenario_id"], user_id, record["status"], json.dumps(record["baseline"]["planning_request"]),
            json.dumps(record["changes"]), json.dumps(record["baseline"]), json.dumps(record["scenario"]), now, now))


def load_scenario(db_path: str, user_id: int, scenario_id: str) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM planning_scenarios WHERE scenario_id=? AND user_id=?", (scenario_id, user_id)).fetchone()
    if not row:
        return None
    return {"scenario_id": row["scenario_id"], "user_id": row["user_id"], "status": row["status"],
            "changes": json.loads(row["changes_json"]), "baseline": json.loads(row["baseline_json"]),
            "scenario": json.loads(row["scenario_json"]), "created_at": row["created_at"]}
