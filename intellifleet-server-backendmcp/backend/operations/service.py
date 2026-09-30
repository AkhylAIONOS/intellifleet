"""Unified deterministic operations over loaded data and the existing Python runtime."""
from datetime import datetime, timedelta
import random
from backend.fedex.models import Schedule, SimulationInput
from backend.fedex.eligibility import IST
from backend.fedex.telemetry import runtime
from backend.planning.service import PlanningService
from .data import synthetic_schedules



# ============================================================
# VERIFIED TRANSPORT NODES FOR SYNTHETIC AIR / RAIL DEMO
#
# AIR  = real airport reference points
# RAIL = real passenger railway stations
#
# The movement between nodes is intentionally straight-line
# visualization. We do NOT claim an airway or physical rail
# track geometry here.
# ============================================================

TRANSPORT_NODE_REGISTRY = {
    'AIR': {
        'UDR': {
            'code': 'UDR',
            'name': 'Maharana Pratap Airport, Udaipur',
            'kind': 'AIRPORT',
            'lat': 24.6177,
            'lng': 73.8961,
        },
        'DEL': {
            'code': 'DEL',
            'name': 'Indira Gandhi International Airport, Delhi',
            'kind': 'AIRPORT',
            'lat': 28.5686,
            'lng': 77.1122,
        },
        'BOM': {
            'code': 'BOM',
            'name': 'Chhatrapati Shivaji Maharaj International Airport, Mumbai',
            'kind': 'AIRPORT',
            'lat': 19.0917,
            'lng': 72.8661,
        },
        'BLR': {
            'code': 'BLR',
            'name': 'Kempegowda International Airport, Bengaluru',
            'kind': 'AIRPORT',
            'lat': 13.1989,
            'lng': 77.7056,
        },
    },

    'RAIL': {
        'UDR': {
            'code': 'UDZ',
            'name': 'Udaipur City Railway Station',
            'kind': 'RAIL_STATION',
            'lat': 24.5685,
            'lng': 73.6998,
        },
        'DEL': {
            'code': 'NDLS',
            'name': 'New Delhi Railway Station',
            'kind': 'RAIL_STATION',
            'lat': 28.6423,
            'lng': 77.2200,
        },
        'BOM': {
            'code': 'MMCT',
            'name': 'Mumbai Central Railway Station',
            'kind': 'RAIL_STATION',
            'lat': 18.9696,
            'lng': 72.8193,
        },
        'BLR': {
            'code': 'SBC',
            'name': 'KSR Bengaluru City Railway Station',
            'kind': 'RAIL_STATION',
            'lat': 12.9776,
            'lng': 77.5681,
        },
    },
}


def _transport_token(value):
    """Resolve existing synthetic station/gateway code to city token."""
    value = str(value or '').upper()

    for token in ('UDR', 'DEL', 'BOM', 'BLR'):
        if token in value:
            return token

    return None


def transport_route(schedule):
    """
    Return straight-line visualization through verified transport nodes.

    route_nodes may later contain >2 entries when an authoritative
    schedule provides genuine intermediate halts.
    """
    mode = str(schedule.mode or '').upper()

    if mode not in {'AIR', 'RAIL'}:
        return [], []

    origin_token = _transport_token(schedule.origin_station)
    destination_token = _transport_token(schedule.gateway)

    registry = TRANSPORT_NODE_REGISTRY.get(mode, {})

    origin = registry.get(origin_token)
    destination = registry.get(destination_token)

    if origin and destination:
        nodes = [
            dict(origin, role='ORIGIN'),
            dict(destination, role='DESTINATION'),
        ]

        path = [
            (node['lat'], node['lng'])
            for node in nodes
        ]

        return path, nodes

    # Never invent a station/airport for an unknown code.
    fallback = [
        point for point in (
            schedule.origin_coordinates,
            schedule.destination_coordinates,
        )
        if point is not None
    ]

    return fallback, []


def network_path(network, origin, destination, mode='road'):
    routes=network['routes']
    direct=[r for r in routes if r['from_location'].casefold()==origin.casefold() and r['to_location'].casefold()==destination.casefold()
            and r['route_type']==mode and r.get('status','active') in {'active','available','open'}]
    paths=[ [r] for r in direct ] or PlanningService._paths(routes,origin,destination,{mode},set())
    if not paths: raise ValueError('NO CONNECTED ROUTE')
    legs=min(paths,key=lambda p:sum(r['duration'] for r in p))
    names=[legs[0]['from_location']]+[r['to_location'] for r in legs]
    facilities={w['name'].casefold():w for w in network['warehouses']}
    points=[(facilities[n.casefold()]['latitude'],facilities[n.casefold()]['longitude']) for n in names]
    if any(None in p for p in points): raise ValueError('Missing network coordinates')
    return legs,points


from threading import RLock

_demo_lock = RLock()


def start_demo(owner,count,seed=42,reuse_existing=False):
    # Serialize check/create with explicit batch replacement in this runtime.
    with _demo_lock:
        if reuse_existing:
            existing = movements(owner)
            if any(m['status'] != 'SCHEDULE_TEMPLATE' and not m.get('stopped')
                   and not m['shipment_id'].startswith('PLAN-')
                   and (m.get('progress') or 0) < 1
                   and m.get('latitude') is not None and m.get('longitude') is not None
                   for m in existing['movements']):
                return existing
        return _start_demo(owner,count,seed)


def _start_demo(owner,count,seed=42):
    if count not in (10,50,100): raise ValueError('Choose 10, 50 or 100 entities')
    network=PlanningService().load_network(owner)
    rng=random.Random(seed)
    now=datetime.now(IST).replace(second=0,microsecond=0)
    choices=[]
    # Only loaded, active directed road edges; no invented or reverse lane.
    for vehicle in network['vehicles']:
        if not vehicle.get('is_available') or not vehicle.get('is_active',1) or vehicle['type'].lower() not in {'truck','car','auto','bike'}: continue
        edges=[r for r in network['routes'] if r['from_location']==vehicle['current_location'] and r['route_type']=='road'
               and r.get('status','active')=='active' and (not vehicle.get('max_range_km') or r['distance']<=vehicle['max_range_km'])]
        if edges:
            edge=rng.choice(edges)
            legs,path=network_path(network,edge['from_location'],edge['to_location'])
            duration=max(sum(r['duration'] for r in legs),sum(r['distance'] for r in legs)/float(vehicle.get('avg_speed_kmph') or 45))
            tt=max(1,round(duration*60)); etd=now.hour*60+now.minute
            # Start at midnight template, then advance into the trip deterministically below.
            choices.append((Schedule(schedule_id=f'NET-{vehicle["id"]}',source_sheet='Loaded network',source_row=0,
                origin_city=edge['from_location'],origin_station=edge['from_location'],gateway=edge['to_location'],lane='Loaded route',run='DEMO',
                mode='SURFACE',source_mode='road',service=vehicle['label'],cutoff_minutes=0,etd_minutes=1,
                eta_minutes=(1+tt)%1440,eta_day_offset=(1+tt)//1440,transit_minutes=tt,
                data_source='SYNTHETIC_NETWORK',origin_coordinates=path[0],destination_coordinates=path[-1]),path))
    for s in synthetic_schedules():
        if s.mode in {'AIR','RAIL'}:
            transport_path, _ = transport_route(s)

            if len(transport_path) >= 2:
                choices.append((s, transport_path))
    if not network['routes']: raise ValueError('Load network CSVs before starting a network demo')
    # Include both non-road modes once, then fill from distinct represented services.
    leading=[next(c for c in choices if c[0].mode==mode) for mode in ('AIR','RAIL')]
    choices=leading+[c for c in choices if c[0].schedule_id not in {x[0].schedule_id for x in leading}]
    if len(choices)<count: raise ValueError(f'Only {len(choices)} distinct feasible network/schedule services; load more data or choose a smaller batch')
    runtime.cleanup()
    old=[k for k,e in runtime.entries.items() if e.owner==owner and e.simulation.request.shipment_id.startswith('NETWORK-DEMO-')]
    if len(runtime.entries)-len(old)+count>runtime.limit: raise ValueError('Simulation limit reached')
    # Construct everything before replacing the prior demo batch.
    from backend.fedex.simulator import Simulation
    from backend.fedex.telemetry import Entry
    prepared=[]
    for i in range(count):
        schedule,path=choices[i]
        request=SimulationInput(origin_station=schedule.origin_station,gateway=schedule.gateway,simulation_date=now.date(),
            shipment_ready_datetime=now.replace(hour=0,minute=0),shipment_id=f'NETWORK-DEMO-{i+1:03}',seed=seed+i)
        sim=Simulation(request,[schedule],runtime.clock(),road_waypoints=path if schedule.mode=='SURFACE' else None)
        if schedule.mode != 'SURFACE':
            sim.route = path
            _, sim.transport_nodes = transport_route(schedule)
        if schedule.data_source=='SYNTHETIC_NETWORK':
            sim.data_source=network['routes'][0].get('data_source','USER_NETWORK')
        sim.now=sim.selected['etd']; sim.advance(sim.last_wall+rng.uniform(.05,.65)*sim.duration/sim.speed)
        sim.last_wall=runtime.clock(); prepared.append(sim)
    for key in old: del runtime.entries[key]
    published_at=runtime.clock()
    for sim in prepared:
        sim.last_wall=published_at  # Cold routing time must not advance earlier batch members.
        runtime.entries[sim.id]=Entry(owner,sim,published_at)
    return movements(owner)


def movements(owner, schedules=None, include_geometry=True):
    runtime.cleanup()
    states=[]

    for entry in list(runtime.entries.values()):
        if entry.owner != owner:
            continue

        state = entry.simulation.advance(runtime.clock())
        state['network_vehicle_ids'] = getattr(entry.simulation, 'network_vehicle_ids', [])
        state['network_route_ids'] = getattr(entry.simulation, 'network_route_ids', [])

        nodes = getattr(
            entry.simulation,
            'transport_nodes',
            None
        )

        if nodes:
            state['route_nodes'] = nodes

            if state.get('mode') == 'AIR':
                state['route_source'] = (
                    'Verified airport endpoints · '
                    'straight-line air visualization'
                )
            elif state.get('mode') == 'RAIL':
                state['route_source'] = (
                    'Verified railway station endpoints · '
                    'straight-line rail visualization'
                )

        states.append(state)
    represented={s['schedule_id'] for s in states}
    templates=[]
    for s in schedules if schedules is not None else synthetic_schedules():
        if s.schedule_id in represented: continue
        templates.append(dict(simulation_id=f'template-{s.schedule_id}',schedule_id=s.schedule_id,shipment_id=s.service,
            service=s.service,mode=s.mode,origin_station=s.origin_station,gateway=s.gateway,status='SCHEDULE_TEMPLATE',
            progress=None,latitude=s.origin_coordinates[0] if s.origin_coordinates else None,
            longitude=s.origin_coordinates[1] if s.origin_coordinates else None,route=[s.origin_coordinates,s.destination_coordinates] if s.origin_coordinates else [],
            data_source=s.data_source,location_source='TEMPLATE_ONLY',scheduled_etd=f'{s.etd_minutes//60:02}:{s.etd_minutes%60:02}' if s.etd_minutes is not None else 'Unknown',
            current_eta=(f'{s.eta_minutes//60:02}:{s.eta_minutes%60:02}' + (f' (+{s.eta_day_offset}d)' if s.eta_day_offset else '')) if s.eta_minutes is not None else 'Unknown',
            delay_minutes=0,heading=0,notice='Schedule template only; no physical movement asserted'))
    items=states+templates
    if not include_geometry:
        for item in items:
            item.pop('route',None)
    return {'movements':items,'telemetry_source':'DEMO_SIMULATION'}



def _normalize_plan_location(value):
    value=' '.join(str(value or '').strip().casefold().split())
    aliases={
        'bangalore':'bengaluru',
        'bangaluru':'bengaluru',
        'bombay':'mumbai',
        'calcutta':'kolkata',
    }
    return aliases.get(value,value)


def _js_int32(value):
    value=int(value) & 0xffffffff
    return value-0x100000000 if value & 0x80000000 else value


def _planning_frontend_route_id(plan_id):
    """Match the negative planning route id generated by appStore.ts."""
    value=0
    for character in str(plan_id):
        shifted=_js_int32(_js_int32(value) << 5)
        value=shifted-value+ord(character)
    return -1-abs(value)


def stop_plan_movement(owner, origin, destination):
    """Stop only the newest active AI PLAN movement for this lane."""
    runtime.cleanup()

    source=_normalize_plan_location(origin)
    target=_normalize_plan_location(destination)

    matches=[]

    for key,entry in list(runtime.entries.items()):
        if entry.owner != owner:
            continue

        sim=entry.simulation
        shipment=str(sim.request.shipment_id or '')

        if not shipment.startswith('PLAN-') or sim.stopped:
            continue

        if (
            _normalize_plan_location(sim.request.origin_station)==source
            and
            _normalize_plan_location(sim.request.gateway)==target
        ):
            matches.append((key,entry))

    if not matches:
        return None

    _,entry=matches[-1]
    sim=entry.simulation

    sim.control('stop',runtime.clock())

    plan_id=str(sim.request.shipment_id)[5:]

    return {
        'message':f'Stopped AI route {sim.request.origin_station} -> {sim.request.gateway}.',
        'route_id':_planning_frontend_route_id(plan_id),
        'simulation_id':sim.id,
        'source':sim.request.origin_station,
        'destination':sim.request.gateway,
    }


def reset_plan_movements(owner):
    """Remove all AI PLAN simulations for this owner only."""
    runtime.cleanup()

    keys=[
        key for key,entry in list(runtime.entries.items())
        if entry.owner==owner
        and str(entry.simulation.request.shipment_id or '').startswith('PLAN-')
    ]

    for key in keys:
        del runtime.entries[key]

    return {
        'success':True,
        'reset_plan_movements':len(keys)
    }


def start_route(owner,origin,destination,weight):
    from backend.planning.models import PlanningRequest
    planner=PlanningService(); network=planner.load_network(owner)
    legs,path=network_path(network,origin,destination)
    request=PlanningRequest(source=origin,destination=destination,shipment={'weight_kg':weight},allowed_modes=['road'])
    # Enforce capacity, range and costs through the existing planner over the chosen loaded path.
    plan=planner.plan(owner,request,{**network,'routes':legs})['recommended_plan']
    if not plan: raise ValueError('No feasible loaded fleet capacity/range for this route')
    now=datetime.now(IST).replace(second=0,microsecond=0)
    duration=plan['duration_hours']
    tt=max(1,round(duration*60))
    schedule=Schedule(schedule_id='NETWORK-'+str(plan['plan_id']),source_sheet='Loaded network plan',source_row=0,
        origin_city=origin,origin_station=origin,gateway=destination,lane=f'{origin} -> {destination}',run='DEMO',mode='SURFACE',source_mode='road',
        service=' / '.join(v.get('label',str(v['id'])) for v in plan['vehicles']),cutoff_minutes=0,etd_minutes=1,eta_minutes=(tt+1)%1440,
        eta_day_offset=(tt+1)//1440,transit_minutes=tt,data_source='SYNTHETIC_NETWORK',origin_coordinates=path[0],destination_coordinates=path[-1])
    sim=runtime.create(owner,SimulationInput(origin_station=origin,gateway=destination,simulation_date=now.date(),shipment_ready_datetime=now.replace(hour=0,minute=0),
        shipment_id='PLAN-'+str(plan['plan_id'])),[schedule],road_waypoints=path)
    sim.data_source=legs[0].get('data_source','USER_NETWORK');sim.now=sim.selected['etd']
    sim.planning_context={'request':request,'network':network,'owner':owner,'plan':plan}
    return sim.snapshot()
