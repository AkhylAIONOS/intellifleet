"""Unified deterministic operations over loaded data and the existing Python runtime."""
from datetime import datetime, timedelta
import random
from backend.fedex.models import Schedule, SimulationInput
from backend.fedex.eligibility import IST
from backend.fedex.telemetry import runtime
from backend.planning.service import PlanningService
from .data import synthetic_schedules


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


def start_demo(owner,count,seed=42):
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
    choices.extend((s,[s.origin_coordinates,s.destination_coordinates]) for s in synthetic_schedules() if s.mode in {'AIR','RAIL'})
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
            shipment_ready_datetime=now.replace(hour=0,minute=0),shipment_id=f'NETWORK-DEMO-{i+1:03}',speed=600,seed=seed+i)
        sim=Simulation(request,[schedule],runtime.clock()); sim.route=path
        if schedule.data_source=='SYNTHETIC_NETWORK':
            sim.data_source=network['routes'][0].get('data_source','USER_NETWORK')
        sim.now=sim.selected['etd']; sim.advance(sim.last_wall+rng.uniform(.05,.65)*sim.duration/sim.speed)
        sim.last_wall=runtime.clock(); prepared.append(sim)
    for key in old: del runtime.entries[key]
    for sim in prepared: runtime.entries[sim.id]=Entry(owner,sim,runtime.clock())
    return movements(owner)


def movements(owner, schedules=None):
    runtime.cleanup()
    states=[e.simulation.advance(runtime.clock()) for e in list(runtime.entries.values()) if e.owner==owner]
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
    return {'movements':states+templates,'telemetry_source':'DEMO_SIMULATION'}


def start_route(owner,origin,destination,weight=6000):
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
        shipment_id='PLAN-'+str(plan['plan_id']),speed=600),[schedule])
    sim.route=path;sim.data_source=legs[0].get('data_source','USER_NETWORK');sim.now=sim.selected['etd']
    sim.planning_context={'request':request,'network':network,'owner':owner,'plan':plan}
    return sim.snapshot()
