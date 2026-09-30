"""Owner-scoped replay of authoritative planner results using the existing simulator."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta
from threading import RLock
import time
import math

_plans = OrderedDict()
_lock = RLock()


def remember(owner, plans):
    with _lock:
        for plan in plans:
            _plans[(owner, plan['plan_id'])] = (time.monotonic(), deepcopy(plan))
        while len(_plans) > 1000:
            _plans.popitem(last=False)


def start(owner, plan_id):
    with _lock:
        return _start(owner, plan_id)


def _start(owner, plan_id):
    from backend.fedex.models import Schedule, SimulationInput
    from backend.fedex.telemetry import runtime
    from backend.fedex.eligibility import IST
    with _lock:
        saved = _plans.get((owner, plan_id))
        if not saved or time.monotonic()-saved[0] > 21600:
            raise KeyError('Plan expired or unavailable. Calculate the plan again before replaying.')
        plan = deepcopy(saved[1])
    # Repeated UI effects/requests must reuse the runtime-owned journey.
    for entry in list(runtime.entries.values()):
        sim = entry.simulation
        if entry.owner == owner and sim.request.shipment_id == 'PLAN-'+plan_id and not sim.stopped and sim.progress < 1:
            return sim.advance(runtime.clock())
    legs = plan['route_legs']
    if not legs or any(x['route_type'].lower() not in {'road','surface','ground'} for x in legs):
        raise ValueError('Road replay requires a Surface/Ground plan')
    if not plan.get('vehicles'):
        raise ValueError('Road replay requires assigned vehicles')
    for leg in legs:
        for key in ('source_coords','destination_coords'):
            point=leg.get(key)
            if not isinstance(point,dict) or any(not isinstance(point.get(k),(int,float)) or not math.isfinite(point[k]) for k in ('lat','lng')):
                raise ValueError('Valid coordinates are required for every planned road leg')
    origin, destination = legs[0]['source_coords'], legs[-1]['destination_coords']
    eta = datetime.fromisoformat(plan['eta']).astimezone(IST)
    duration = float(plan['duration_hours'])*3600
    etd = eta-timedelta(seconds=duration)
    schedule = Schedule(schedule_id='PLAN-'+plan_id, source_sheet='Authoritative planning result',source_row=0,
        origin_city=legs[0]['from_location'],origin_station=legs[0]['from_location'],gateway=legs[-1]['to_location'],
        lane='Plan replay',run='DEMO',mode='SURFACE',source_mode='road',service=' / '.join(str(v.get('label') or v['id']) for v in plan['vehicles']),
        cutoff_minutes=0,etd_minutes=1,eta_minutes=2,eta_day_offset=0,data_source='SYNTHETIC_NETWORK',
        origin_coordinates=(origin['lat'],origin['lng']),destination_coordinates=(destination['lat'],destination['lng']))
    sim = runtime.create(owner,SimulationInput(origin_station=schedule.origin_station,gateway=schedule.gateway,
        simulation_date=etd.date(),shipment_ready_datetime=etd.replace(hour=0,minute=0,second=0,microsecond=0),
        shipment_id='PLAN-'+plan_id),[schedule],
        road_waypoints=[(origin['lat'],origin['lng']), *[(leg['destination_coords']['lat'],leg['destination_coords']['lng']) for leg in legs]])
    # Replay begins at the plan's departure, never at elapsed wall-clock progress.
    sim.selected.update(etd=etd,eta=eta,cutoff=etd)
    sim.duration=duration;sim.now=etd;sim.current_eta=eta;sim.paused=True
    sim.status='IN_TRANSIT';sim.last_wall=runtime.clock()
    return sim.snapshot()
