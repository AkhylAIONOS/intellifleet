import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from .database import migrate
from .status import operational_fields, timestamp


class ControlTower:
    def __init__(self, db_path='users.db', clock=None):
        self.db_path = db_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            migrate(conn)
            with conn:
                yield conn
        finally:
            conn.close()

    def import_network(self, owner, schedules, service_date):
        from backend.fedex.eligibility import candidate, IST
        from backend.fedex.models import EligibilityInput
        if any(s.data_source != 'FEDEX_SOURCE' for s in schedules):
            raise ValueError('Only provided FedEx workbook schedules belong to the operational network')
        version=hashlib.sha256(json.dumps([s.model_dump(mode='json') for s in schedules],sort_keys=True).encode()).hexdigest()
        with self.db() as conn:
            for schedule in schedules:
                req=EligibilityInput(origin_station=schedule.origin_station,gateway=schedule.gateway,
                    simulation_date=service_date,shipment_ready_datetime=datetime.combine(service_date,datetime.min.time(),IST))
                dates=candidate(schedule,req)
                lane_key=json.dumps([schedule.origin_station,schedule.gateway,schedule.lane],separators=(',',':'))
                run_id=hashlib.sha256(f'{version}:{schedule.schedule_id}:{service_date}'.encode()).hexdigest()[:24]
                etd=dates['etd'].isoformat() if dates['etd'] else None
                eta=dates['eta'].isoformat() if dates['eta'] else None
                conn.execute('''INSERT OR IGNORE INTO ct_runs
                    (owner,run_id,lane_key,schedule_id,service_date,network_version,schedule_json,planned_etd,planned_eta,current_eta,last_update_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                    (owner,run_id,lane_key,schedule.schedule_id,str(service_date),version,json.dumps(schedule.model_dump(mode='json')),etd,eta,eta,self.clock().isoformat()))
            conn.execute('INSERT OR REPLACE INTO ct_network_imports VALUES(?,?,?,?)',(owner,str(service_date),version,self.clock().isoformat()))
        return self.runs(owner,service_date,version=version)

    def _row(self, conn, owner, run_id):
        row=conn.execute('SELECT * FROM ct_runs WHERE owner=? AND run_id=?',(owner,run_id)).fetchone()
        if row is None:
            raise KeyError('Operational run not found')
        return dict(row)

    def _decorate(self, conn, row):
        schedule=json.loads(row.pop('schedule_json'))
        critical=conn.execute('SELECT critical FROM ct_critical_lanes WHERE owner=? AND lane_key=?',(row['owner'],row['lane_key'])).fetchone()
        row.update(schedule=schedule,critical=bool(critical and critical[0]),data_source='FEDEX_SOURCE',
                   event_source=row.get('actual_source'),location_source=None,latest_location=None)
        if row.get('actual_source')=='FEDEX_SCAN':
            for event in conn.execute('SELECT payload_json,event_at FROM ct_events WHERE owner=? AND run_id=? ORDER BY event_at DESC',(row['owner'],row['run_id'])):
                payload=json.loads(event['payload_json'])
                if payload.get('latitude') is not None and payload.get('longitude') is not None:
                    row.update(latest_location={'latitude':payload['latitude'],'longitude':payload['longitude']},location_source='FEDEX_SCAN',location_updated_at=event['event_at'])
                    break
        now=self.clock()
        if row.get('movement_id'):
            from backend.fedex.telemetry import runtime
            try:
                snapshot=runtime.get(row['owner'],row['movement_id']).snapshot()
                row.update(latest_location={'latitude':snapshot['latitude'],'longitude':snapshot['longitude']},
                    location_source='SYNTHETIC_TELEMETRY',movement=snapshot,last_update_at=snapshot['simulation_timestamp'])
                # Synthetic playback clock must not be compared with wall time.
                if row.get('actual_source')=='SYNTHETIC_TELEMETRY':
                    now=timestamp(snapshot['simulation_timestamp'])
            except KeyError:
                row['tracking_notice']='Synthetic movement expired; last operational facts retained'
        row.update(operational_fields(row,now))
        return row

    def runs(self, owner, service_date=None, mode=None, status=None, critical=None, search='', version=None):
        with self.db() as conn:
            query='SELECT * FROM ct_runs WHERE owner=?';params=[owner]
            if service_date:
                query+=' AND service_date=?';params.append(str(service_date))
            if version:
                query+=' AND network_version=?';params.append(version)
            elif service_date:
                # A workbook revision remains archived, not silently merged.
                latest=conn.execute('SELECT network_version FROM ct_network_imports WHERE owner=? AND service_date=?',(owner,str(service_date))).fetchone()
                if latest:
                    query+=' AND network_version=?';params.append(latest[0])
            else:
                query+=' AND network_version=(SELECT network_version FROM ct_network_imports i WHERE i.owner=ct_runs.owner AND i.service_date=ct_runs.service_date)'
            rows=[self._decorate(conn,dict(r)) for r in conn.execute(query,params)]
        return [r for r in rows if (not mode or r['schedule']['mode']==mode or (mode=='SURFACE' and r['schedule']['source_sheet']=='Surface'))
            and (not status or r['status']==status) and (critical is None or r['critical']==critical)
            and (not search or search.casefold() in json.dumps(r['schedule']).casefold())]

    def detail(self, owner, run_id):
        with self.db() as conn:
            row=self._decorate(conn,self._row(conn,owner,run_id))
            row['events']=[dict(x) for x in conn.execute('SELECT * FROM ct_events WHERE owner=? AND run_id=? ORDER BY event_at',(owner,run_id))]
            row['cons']=[dict(x) for x in conn.execute('SELECT con_number,source,event_at FROM ct_cons WHERE owner=? AND run_id=?',(owner,run_id))]
            return row

    def summary(self, rows):
        counts={s:sum(r['status']==s for r in rows) for s in ['SCHEDULED','ON TIME','EXPECTED DELAY','DELAYED','ARRIVED']}
        return dict(total_runs=len(rows),air_runs=sum(r['schedule']['mode']=='AIR' for r in rows),
            surface_runs=sum(r['schedule']['mode']=='SURFACE' or r['schedule']['source_sheet']=='Surface' for r in rows),statuses=counts,
            critical_lanes=len({r['lane_key'] for r in rows if r['critical']}),
            critical_lanes_at_risk=len({r['lane_key'] for r in rows if r['critical'] and r['status'] in {'EXPECTED DELAY','DELAYED'}}))

    def mark_critical(self, owner, run_id, critical):
        with self.db() as conn:
            row=self._row(conn,owner,run_id)
            conn.execute('INSERT OR REPLACE INTO ct_critical_lanes VALUES(?,?,?,?)',(owner,row['lane_key'],int(critical),self.clock().isoformat()))
        return self.detail(owner,run_id)

    def recipients(self, owner, emails=None):
        with self.db() as conn:
            if emails is not None:
                conn.execute('DELETE FROM ct_recipients WHERE owner=?',(owner,))
                conn.executemany('INSERT INTO ct_recipients VALUES(?,?,1)',[(owner,e) for e in sorted(set(emails))])
            return [r[0] for r in conn.execute('SELECT email FROM ct_recipients WHERE owner=? AND enabled=1 ORDER BY email',(owner,))]

    def _transition(self, conn, row, previous, event_key, reason, now):
        fields=operational_fields(row,now)
        new=fields['status']
        conn.execute('UPDATE ct_runs SET status=? WHERE owner=? AND run_id=?',(new,row['owner'],row['run_id']))
        if previous==new or new not in {'EXPECTED DELAY','DELAYED'}:
            return
        recipients=[r[0] for r in conn.execute('SELECT email FROM ct_recipients WHERE owner=? AND enabled=1',(row['owner'],))]
        decorated=self._decorate(conn,dict(row))
        payload={k:decorated.get(k) for k in ['run_id','lane_key','schedule','planned_etd','planned_eta','current_eta','critical','actual_source','last_update_at']}
        payload.update(fields,previous_status=previous,reason=reason,timestamp=now.isoformat())
        # Independent recipient retries avoid resending successfully delivered mail.
        for email in recipients or [None]:
            conn.execute('''INSERT OR IGNORE INTO ct_outbox(owner,run_id,transition_key,payload_json,recipients_json,status,next_attempt_at,created_at)
                VALUES(?,?,?,?,?,?,?,?)''',(row['owner'],row['run_id'],f'{row["run_id"]}:{event_key}:{new}:{email or "none"}',json.dumps(payload),json.dumps([email] if email else []),
                    'PENDING' if email else 'NO_RECIPIENTS',now.isoformat(),now.isoformat()))

    def event(self, owner, run_id, event):
        event= dict(event)
        if event.get('source') not in {'FEDEX_SCAN','SYNTHETIC_TELEMETRY'} or event.get('event_type') not in {'DEPARTURE','ARRIVAL','ETA_UPDATE','LOCATION'}:
            raise ValueError('Unsupported operational event type/source')
        at=timestamp(event['event_at'])
        eta=timestamp(event.get('current_eta'))
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=self._row(conn,owner,run_id)
            existing=conn.execute('SELECT payload_json FROM ct_events WHERE owner=? AND event_id=?',(owner,event['event_id'])).fetchone()
            payload=json.dumps(event,sort_keys=True,default=str)
            if existing:
                if existing[0]!=payload:
                    raise ValueError('Event ID already belongs to different event data')
                return self._decorate(conn,row)
            if row.get('actual_source') and row['actual_source']!=event['source']:
                raise ValueError('Real scan and synthetic execution cannot be mixed in one run')
            last=conn.execute('SELECT max(event_at) FROM ct_events WHERE owner=? AND run_id=?',(owner,run_id)).fetchone()[0]
            if last and at<timestamp(last):
                raise ValueError('Stale event rejected; event timestamps must be chronological')
            kind=event['event_type']
            if row['actual_arrival_at']:
                raise ValueError('Arrived run is immutable')
            if kind=='DEPARTURE':
                if row['actual_departure_at']:
                    raise ValueError('Departure already recorded')
                row['actual_departure_at']=at.isoformat()
            elif kind=='ARRIVAL':
                if not row['actual_departure_at'] or at<timestamp(row['actual_departure_at']):
                    raise ValueError('Arrival requires an earlier departure')
                row['actual_arrival_at']=at.isoformat()
            elif kind=='ETA_UPDATE' and eta is None:
                raise ValueError('ETA update requires current_eta')
            if eta:
                if row['actual_departure_at'] and eta<timestamp(row['actual_departure_at']):
                    raise ValueError('ETA cannot precede departure')
                row['current_eta']=eta.isoformat()
            row.update(actual_source=event['source'],last_update_at=at.isoformat())
            if event.get('carrier'):
                row['carrier']=event['carrier']
                conn.execute('UPDATE ct_runs SET carrier=? WHERE owner=? AND run_id=?',(row['carrier'],owner,run_id))
            conn.execute('UPDATE ct_runs SET actual_departure_at=?,actual_arrival_at=?,actual_source=?,current_eta=?,last_update_at=? WHERE owner=? AND run_id=?',
                (row['actual_departure_at'],row['actual_arrival_at'],row['actual_source'],row['current_eta'],row['last_update_at'],owner,run_id))
            conn.execute('INSERT INTO ct_events VALUES(?,?,?,?,?,?,?)',(owner,event['event_id'],run_id,kind,event['source'],at.isoformat(),payload))
            self._transition(conn,row,row['status'],event['event_id'],event.get('reason','Operational event'),at)
        return self.detail(owner,run_id)

    def link_simulation(self, owner, run_id, request):
        from backend.fedex.telemetry import runtime
        from backend.fedex.models import Schedule
        with self.db() as conn:
            row=self._row(conn,owner,run_id)
            if row['actual_source']=='FEDEX_SCAN':
                raise ValueError('A real execution run cannot be replaced with synthetic playback')
            if row['movement_id']:
                return self._decorate(conn,row)
            if str(request.simulation_date)!=row['service_date'] or request.origin_station!=json.loads(row['schedule_json'])['origin_station'] or request.gateway!=json.loads(row['schedule_json'])['gateway']:
                raise ValueError('Simulation must use the operational run date and endpoints')
            schedule=Schedule(**json.loads(row['schedule_json']))
            request=request.model_copy(update={'schedule_id':schedule.schedule_id,'shipment_id':'CT-DEMO-'+run_id})
            sim=runtime.create(owner,request,[schedule])
            conn.execute('UPDATE ct_runs SET movement_id=?,actual_source=?,carrier=? WHERE owner=? AND run_id=?',(sim.id,'SYNTHETIC_TELEMETRY',schedule.service,owner,run_id))
        return self.detail(owner,run_id)

    def observe(self, owner):
        """Persist labelled simulation milestones and time-based transitions."""
        from backend.fedex.telemetry import runtime
        for row in self.runs(owner):
            now=self.clock()
            if row.get('movement_id') and row.get('actual_source')=='SYNTHETIC_TELEMETRY':
                try:
                    snapshot=runtime.get(owner,row['movement_id']).snapshot()
                except KeyError:
                    continue
                now=timestamp(snapshot['simulation_timestamp'])
                events=[]
                if snapshot['progress']>0 and not row['actual_departure_at']:
                    events.append(dict(event_type='DEPARTURE',event_at=snapshot['scheduled_etd'],event_id='sim-departure:'+row['movement_id']))
                if snapshot['current_eta']!=row['current_eta']:
                    events.append(dict(event_type='ETA_UPDATE',event_at=snapshot['simulation_timestamp'],current_eta=snapshot['current_eta'],event_id=f'sim-eta:{row["movement_id"]}:{snapshot["current_eta"]}'))
                if snapshot['progress']>=1 and not row['actual_arrival_at']:
                    events.append(dict(event_type='ARRIVAL',event_at=snapshot['current_eta'],event_id='sim-arrival:'+row['movement_id']))
                for event in events:
                    self.event(owner,row['run_id'],dict(event,source='SYNTHETIC_TELEMETRY',reason='Labelled simulation milestone'))
            with self.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                fresh=self._row(conn,owner,row['run_id'])
                self._transition(conn,fresh,fresh['status'],'clock:'+fresh['status'],'Planned arrival threshold exceeded',now)

    def con_event(self, owner, data):
        at=timestamp(data['event_at'])
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=self._row(conn,owner,data['run_id'])
            if not row['actual_departure_at'] or at<timestamp(row['actual_departure_at']):
                raise ValueError('CON association requires a recorded departure')
            if data['source']!=row['actual_source']:
                raise ValueError('CON and run event provenance must match')
            existing=conn.execute('SELECT * FROM ct_con_events WHERE owner=? AND event_id=?',(owner,data['event_id'])).fetchone()
            values=(owner,data['event_id'],data['con_number'],data['run_id'],data['source'],at.isoformat())
            if existing:
                if tuple(existing)!=values:
                    raise ValueError('CON event ID conflict')
            else:
                prior=conn.execute('SELECT event_at FROM ct_cons WHERE owner=? AND con_number=?',(owner,data['con_number'])).fetchone()
                if prior and at<timestamp(prior[0]):
                    raise ValueError('Stale CON association rejected')
                conn.execute('INSERT INTO ct_con_events VALUES(?,?,?,?,?,?)',values)
                conn.execute('INSERT OR REPLACE INTO ct_cons VALUES(?,?,?,?,?,?)',(owner,data['con_number'],data['run_id'],data['source'],at.isoformat(),data['event_id']))
        return self.con(owner,data['con_number'])

    def con(self, owner, number):
        with self.db() as conn:
            con=conn.execute('SELECT * FROM ct_cons WHERE owner=? AND con_number=?',(owner,number)).fetchone()
            if not con:
                raise KeyError('CON not found')
            con=dict(con)
        return dict(con=con,run=self.detail(owner,con['run_id']))

    def alerts(self, owner):
        with self.db() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM ct_outbox WHERE owner=? ORDER BY id DESC LIMIT 100',(owner,))]

    async def deliver(self, sender=None, enabled=False):
        """Persistent leased outbox. Delivery is explicitly disabled by default."""
        from backend.config.config import settings
        from backend.utilities.email import send_email
        configured=all(getattr(settings,k,None) for k in ['SMTP_SERVER','SMTP_PORT','SMTP_USERNAME','SMTP_PASSWORD','EMAIL_FROM'])
        now=self.clock()
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=[dict(r) for r in conn.execute("SELECT * FROM ct_outbox WHERE status IN ('PENDING','RETRY','NOT_CONFIGURED','DELIVERY_DISABLED','PROCESSING') AND next_attempt_at<=? AND attempts<5",(now.isoformat(),))]
            for r in rows:
                status='PROCESSING' if enabled and (configured or sender) else 'NOT_CONFIGURED' if not configured else 'DELIVERY_DISABLED'
                conn.execute('UPDATE ct_outbox SET status=?,next_attempt_at=? WHERE id=?',(status,(now+timedelta(minutes=5)).isoformat(),r['id']))
        if not enabled or not (configured or sender):
            return
        for r in rows:
            recipients=json.loads(r['recipients_json'])
            try:
                payload=json.loads(r['payload_json'])
                await (sender or send_email)(', '.join(recipients),f'UniFleet {payload["status"]}: {payload["schedule"]["lane"]}',json.dumps(payload,indent=2))
                status,error='DELIVERED',None
            except Exception:
                status,error='RETRY' if r['attempts']+1<5 else 'FAILED','SMTP delivery failed; inspect server configuration'
            with self.db() as conn:
                conn.execute('UPDATE ct_outbox SET status=?,attempts=attempts+1,last_error=?,delivered_at=?,next_attempt_at=? WHERE id=?',
                    (status,error,now.isoformat() if status=='DELIVERED' else None,(now+timedelta(minutes=2**(r['attempts']+1))).isoformat(),r['id']))
