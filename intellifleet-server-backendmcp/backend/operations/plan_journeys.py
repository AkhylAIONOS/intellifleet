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
            key = (owner, plan['plan_id'])
            saved = _plans.get(key)
            value = deepcopy(plan)
            # Planner candidates may be serialized/cached again without lifecycle
            # metadata. A committed revision-to-journey binding is authoritative.
            if saved and saved[1].get('journey_id'):
                value.update({k: saved[1][k] for k in ('journey_id', 'revision') if k in saved[1]})
            _plans[key] = (time.monotonic(), value)
        while len(_plans) > 1000:
            _plans.popitem(last=False)


def canonical_identity(owner, plan_id, movement_id=None):
    """Recover an existing binding using IDs, never an origin/destination guess."""
    from backend.fedex.telemetry import runtime
    with _lock:
        for entry in list(runtime.entries.values()):
            sim = entry.simulation
            if entry.owner == owner and (
                (movement_id and sim.id == movement_id)
                or getattr(sim, 'plan_revision_id', None) == plan_id
                or sim.request.shipment_id == 'PLAN-' + str(plan_id)
            ):
                return {'journey_id': getattr(sim, 'journey_id', None) or sim.request.shipment_id.removeprefix('PLAN-'),
                        'movement_id': sim.id, 'shipment_id': sim.request.shipment_id}
        saved = _plans.get((owner, plan_id))
        if saved and saved[1].get('journey_id'):
            return {'journey_id': saved[1]['journey_id']}
    return {}


def start(owner, plan_id, *, planner_reroute=False):
    with _lock:
        return _start(owner, plan_id, planner_reroute=planner_reroute)


def _start(owner, plan_id, *, planner_reroute=False):
    from backend.fedex.models import Schedule, SimulationInput
    from backend.fedex.telemetry import runtime
    from backend.fedex.eligibility import IST
    with _lock:
        saved = _plans.get((owner, plan_id))
        if not saved or time.monotonic()-saved[0] > 21600:
            raise KeyError('Plan expired or unavailable. Calculate the plan again before replaying.')
        plan = deepcopy(saved[1])
    identity = plan.get('journey_id') or plan_id
    existing = None
    # Repeated UI effects/requests must reuse the runtime-owned journey.
    for entry in list(runtime.entries.values()):
        sim = entry.simulation
        if entry.owner == owner and sim.request.shipment_id == 'PLAN-'+identity:
            if sim.stopped or sim.progress >= 1:
                if not plan.get('journey_id'):
                    continue
                if getattr(sim, 'plan_revision_id', identity) != plan_id:
                    raise ValueError('Stopped or completed journeys cannot be revised; create an explicit new shipment.')
                return sim.snapshot()
            if getattr(sim, 'plan_revision_id', identity) == plan_id or (plan.get('journey_id') and getattr(sim, 'plan_revision', 0) >= plan.get('revision', 1)):
                return sim.advance(runtime.clock())
            existing = sim
            break
    legs = plan['route_legs']
    path_changed = existing and getattr(existing, 'network_route_ids', []) != [leg.get('route_id') for leg in legs]
    # Origin-to-destination planning refreshes synthetic playback; it does not
    # claim to join a new path from a live vehicle's current GPS position.
    restart_replay = planner_reroute and path_changed
    if existing and existing.progress > 0 and path_changed and not planner_reroute:
        raise ValueError('Mid-route replacement requires a verified transfer/rejoin location; current movement retained.')
    if not legs or any(x['route_type'].lower() not in {'road','surface','ground','air'} for x in legs):
        raise ValueError('Replay requires verified Ground/Air legs')
    surface = all(x['route_type'].lower() in {'road','surface','ground'} for x in legs)
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
    schedule = Schedule(schedule_id='PLAN-'+identity, source_sheet='Authoritative planning result',source_row=0,
        origin_city=legs[0]['from_location'],origin_station=legs[0]['from_location'],gateway=legs[-1]['to_location'],
        lane='Plan replay',run='DEMO',mode='SURFACE' if surface else 'AIR',source_mode=plan['mode'],service=' / '.join(str(v.get('label') or v['id']) for v in plan['vehicles']),
        cutoff_minutes=0,etd_minutes=1,eta_minutes=2,eta_day_offset=0,data_source='SYNTHETIC_NETWORK',
        origin_coordinates=(origin['lat'],origin['lng']),destination_coordinates=(destination['lat'],destination['lng']))
    if not surface:
        from backend.operations.road_routing_engine import road_routing_engine
        geometry = []
        segments = []
        elapsed = 0.0
        assignments = plan.get('leg_assignments') or [{'route_legs':legs, 'vehicles':plan['vehicles'], 'duration_hours':plan['duration_hours']}]
        for leg in legs:
            assignment = next(x for x in assignments if any(l['route_id'] == leg['route_id'] for l in x['route_legs']))
            travel = sum(float(l.get('duration') or 0) for l in assignment['route_legs'])
            share = float(leg.get('duration') or 0)/travel if travel else 1/len(assignment['route_legs'])
            hours = float(assignment.get('duration_hours') or travel)*share
            a = (leg['source_coords']['lat'], leg['source_coords']['lng'])
            b = (leg['destination_coords']['lat'], leg['destination_coords']['lng'])
            road = leg['route_type'].lower() != 'air'
            points = road_routing_engine.get_route(*a, *b).geometry if road else [a, b]
            start_index = max(0, len(geometry)-1)
            geometry.extend(points if not geometry else points[1:])
            segments.append({'start_index': start_index, 'end_index': len(geometry)-1,
                             'mode': 'SURFACE' if road else 'AIR', 'route_id': leg.get('route_id'),
                             'from_location':leg['from_location'], 'to_location':leg['to_location'],
                             'vehicles':deepcopy(assignment['vehicles']), 'duration_hours':hours,
                             'start_hours':elapsed, 'end_hours':elapsed+hours})
            elapsed += hours
        # Include deterministic transfer overhead in each segment's playback share.
        for segment in segments:
            segment['start_progress'] = segment['start_hours']/elapsed
            segment['end_progress'] = segment['end_hours']/elapsed
    sim = runtime.create(owner,SimulationInput(origin_station=schedule.origin_station,gateway=schedule.gateway,
        simulation_date=etd.date(),shipment_ready_datetime=etd.replace(hour=0,minute=0,second=0,microsecond=0),
        shipment_id='PLAN-'+identity),[schedule],
        road_waypoints=[(origin['lat'],origin['lng']), *[(leg['destination_coords']['lat'],leg['destination_coords']['lng']) for leg in legs]])
    if not surface:
        sim.route = geometry
        sim.journey_segments = segments
    sim.journey_id = identity
    sim.plan_revision_id = plan_id
    sim.plan_revision = plan.get('revision', 1)
    sim.plan_risk = plan.get('risk_score')
    if existing:
        # Publish a revision under the same runtime key. Never create a second movement.
        del runtime.entries[sim.id]
        sim.id = existing.id
        runtime.entries[existing.id].simulation = sim
        sim.progress = 0 if restart_replay else existing.progress
        sim.events = existing.events
        sim.alerts = existing.alerts
        sim.speed = existing.speed
        sim.sequence = existing.sequence + 1
    # Replay begins at the plan's departure, never at elapsed wall-clock progress.
    sim.selected.update(etd=etd,eta=eta,cutoff=etd)
    sim.duration=duration;sim.now=etd;sim.current_eta=eta;sim.paused=True
    sim.network_vehicle_ids=[v['id'] for v in plan['vehicles']]
    sim.network_route_ids=[leg.get('route_id') for leg in legs]
    sim.status='IN_TRANSIT';sim.last_wall=runtime.clock()
    if existing:
        sim.paused = existing.paused
        sim.now = etd if restart_replay else existing.now
        delay = existing.current_eta-existing.selected['eta']
        sim.current_eta += delay
        sim.hold_until = existing.hold_until
        if restart_replay:
            remaining_hold = max(timedelta(), (existing.hold_until or existing.now)-existing.now)
            sim.hold_until = sim.now+remaining_hold if remaining_hold else None
    return sim.snapshot()
