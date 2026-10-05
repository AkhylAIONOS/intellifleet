"""Additive SQLite migration; existing tables/columns are never changed."""
def migrate(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS ct_personal_recipients (
      owner INTEGER NOT NULL, identity TEXT NOT NULL, email TEXT NOT NULL,
      PRIMARY KEY(owner,identity));
    CREATE TABLE IF NOT EXISTS ct_personal_outbox (
      outbox_id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, identity TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ct_chat_context (
      owner INTEGER NOT NULL, service_date TEXT NOT NULL, session_id TEXT NOT NULL, run_ids_json TEXT NOT NULL,
      PRIMARY KEY(owner,service_date,session_id));
    CREATE TABLE IF NOT EXISTS ct_runs (
      owner INTEGER NOT NULL, run_id TEXT NOT NULL, lane_key TEXT NOT NULL,
      schedule_id TEXT NOT NULL, service_date TEXT NOT NULL, network_version TEXT NOT NULL,
      schedule_json TEXT NOT NULL, planned_etd TEXT, planned_eta TEXT, current_eta TEXT,
      actual_departure_at TEXT, actual_arrival_at TEXT, actual_source TEXT,
      movement_id TEXT, carrier TEXT, status TEXT NOT NULL DEFAULT 'SCHEDULED',
      last_update_at TEXT NOT NULL, PRIMARY KEY(owner,run_id));
    CREATE INDEX IF NOT EXISTS ct_runs_date ON ct_runs(owner,service_date);
    CREATE TABLE IF NOT EXISTS ct_network_imports (
      owner INTEGER NOT NULL,service_date TEXT NOT NULL,network_version TEXT NOT NULL,
      imported_at TEXT NOT NULL,PRIMARY KEY(owner,service_date));
    CREATE TABLE IF NOT EXISTS ct_critical_lanes (
      owner INTEGER NOT NULL, lane_key TEXT NOT NULL, critical INTEGER NOT NULL,
      updated_at TEXT NOT NULL, PRIMARY KEY(owner,lane_key));
    CREATE TABLE IF NOT EXISTS ct_events (
      owner INTEGER NOT NULL, event_id TEXT NOT NULL, run_id TEXT NOT NULL,
      event_type TEXT NOT NULL, source TEXT NOT NULL, event_at TEXT NOT NULL,
      payload_json TEXT NOT NULL, PRIMARY KEY(owner,event_id));
    CREATE INDEX IF NOT EXISTS ct_events_run ON ct_events(owner,run_id,event_at);
    CREATE TABLE IF NOT EXISTS ct_recipients (
      owner INTEGER NOT NULL, email TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
      PRIMARY KEY(owner,email));
    CREATE TABLE IF NOT EXISTS ct_outbox (
      id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER NOT NULL, run_id TEXT NOT NULL,
      transition_key TEXT NOT NULL, payload_json TEXT NOT NULL, recipients_json TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
      next_attempt_at TEXT NOT NULL, created_at TEXT NOT NULL, delivered_at TEXT,
      last_error TEXT, UNIQUE(owner,transition_key));
    CREATE INDEX IF NOT EXISTS ct_outbox_due ON ct_outbox(status,next_attempt_at);
    CREATE TABLE IF NOT EXISTS ct_cons (
      owner INTEGER NOT NULL, con_number TEXT NOT NULL, run_id TEXT NOT NULL,
      source TEXT NOT NULL, event_at TEXT NOT NULL, event_id TEXT NOT NULL,
      PRIMARY KEY(owner,con_number));
    CREATE TABLE IF NOT EXISTS ct_con_events (
      owner INTEGER NOT NULL, event_id TEXT NOT NULL, con_number TEXT NOT NULL,
      run_id TEXT NOT NULL, source TEXT NOT NULL, event_at TEXT NOT NULL,
      PRIMARY KEY(owner,event_id));
    CREATE INDEX IF NOT EXISTS ct_cons_run ON ct_cons(owner,run_id);
    ''')
