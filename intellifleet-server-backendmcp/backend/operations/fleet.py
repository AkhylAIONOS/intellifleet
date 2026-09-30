"""Initialize network-backed playback in the existing owner-scoped runtime.

One movement per eligible loaded vehicle, never a requested test-batch size.
This is calculated playback, not a claim of live GPS or a shipment dispatch.
"""
from datetime import datetime, timedelta
import json
import math

from backend.fedex.eligibility import IST
from backend.fedex.models import Schedule, SimulationInput
from backend.fedex.simulator import Simulation
from backend.fedex.telemetry import Entry
from backend.planning.service import PlanningService
from . import service
from .road_routing_engine import RoadRoutingError


VEHICLE_MODES = {'truck': 'road', 'car': 'road', 'auto': 'road', 'bike': 'road',
                 'plane': 'air', 'aircraft': 'air', 'train': 'rail', 'rail': 'rail'}


def initialize(owner):
    with service._demo_lock:
        runtime = service.runtime
        runtime.cleanup()
        network = PlanningService().load_network(owner)
        if not network['vehicles'] or not network['routes']:
            raise ValueError('Load vehicles and routes before initializing operational movements')
        facilities = {w['name'].casefold(): w for w in network['warehouses'] if w.get('is_active', 1)}
        represented = set()
        for entry in list(runtime.entries.values()):
            if entry.owner != owner:
                continue
            sim = entry.simulation
            # A stopped initialized resource stays stopped across view changes.
            represented.update(getattr(sim, 'network_vehicle_ids', []))
            for vehicle in network['vehicles']:
                if sim.selected.get('schedule_id') == f"NET-{vehicle['id']}":
                    represented.add(vehicle['id'])
        prepared, skipped = [], []
        now = datetime.now(IST)
        for vehicle in sorted(network['vehicles'], key=lambda v: v['id']):
            if vehicle['id'] in represented:
                continue
            mode = VEHICLE_MODES.get(vehicle['type'].casefold())
            if not mode or not vehicle.get('is_available') or not vehicle.get('is_active', 1) or float(vehicle.get('capacity') or 0) <= 0:
                continue
            compatible = vehicle.get('compatible_modes')
            if isinstance(compatible, str):
                try: compatible = json.loads(compatible)
                except ValueError: compatible = compatible.split(',')
            if compatible and mode not in compatible:
                continue
            edges = [r for r in network['routes']
                     if r['from_location'].casefold() == str(vehicle.get('current_location') or '').casefold()
                     and r['route_type'].casefold() == mode
                     and r.get('status', 'active') in {'active', 'available', 'open'}
                     and r['from_location'].casefold() in facilities and r['to_location'].casefold() in facilities
                     and (not vehicle.get('max_range_km') or r['distance'] <= vehicle['max_range_km'])]
            if not edges:
                skipped.append({'vehicle_id': vehicle['id'], 'reason': 'No compatible active outgoing loaded route'})
                continue
            # Stable route choice; no random destinations or invented shipments.
            edge = min(edges, key=lambda r: (r['duration'], r['distance'], r['route_id']))
            try:
                points = [(facilities[edge[key].casefold()]['latitude'], facilities[edge[key].casefold()]['longitude'])
                          for key in ('from_location', 'to_location')]
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for point in points for v in point):
                    raise ValueError('Missing loaded route coordinates')
                duration = max(float(edge['duration']), float(edge['distance']) / float(vehicle.get('avg_speed_kmph') or (700 if mode == 'air' else 45)))
                duration += (float(vehicle.get('loading_time_min') or 0) + float(vehicle.get('unloading_time_min') or 0)) / 60
                if duration <= 0:
                    raise ValueError('Route duration must be positive')
                minutes = max(1, round(duration * 60))
                schedule = Schedule(schedule_id=f"FLEET-{vehicle['id']}", source_sheet='Loaded network', source_row=0,
                    origin_city=edge['from_location'], origin_station=edge['from_location'], gateway=edge['to_location'],
                    lane=str(edge['route_id']), run='NETWORK', mode={'road': 'SURFACE', 'air': 'AIR', 'rail': 'RAIL'}[mode],
                    source_mode=mode, service=vehicle['label'], cutoff_minutes=0, etd_minutes=1,
                    eta_minutes=(1+minutes)%1440, eta_day_offset=(1+minutes)//1440, transit_minutes=minutes,
                    data_source='SYNTHETIC_NETWORK', origin_coordinates=points[0], destination_coordinates=points[-1])
                sim = Simulation(SimulationInput(origin_station=schedule.origin_station, gateway=schedule.gateway,
                    simulation_date=now.date(), shipment_ready_datetime=now.replace(hour=0, minute=0, second=0, microsecond=0),
                    shipment_id=f"FLEET-{vehicle['id']}"), [schedule], runtime.clock(),
                    road_waypoints=points if mode == 'road' else None)
                sim.selected.update(etd=now, eta=now+timedelta(hours=duration), cutoff=now)
                sim.duration=duration*3600; sim.now=now; sim.current_eta=sim.selected['eta']; sim.status='IN_TRANSIT'
                sim.data_source=vehicle.get('data_source', 'USER_NETWORK')
                sim.network_vehicle_ids=[vehicle['id']]
                sim.network_route_ids=[edge['route_id']]
                sim.notice='Calculated playback from loaded fleet and routes; no shipment dispatched or fleet capacity reserved.'
                prepared.append(sim)
            except (RoadRoutingError, ValueError, KeyError) as exc:
                skipped.append({'vehicle_id': vehicle['id'], 'reason': str(exc)})
        if len(runtime.entries)+len(prepared) > runtime.limit:
            raise ValueError('Simulation capacity reached; existing movements were preserved')
        published=runtime.clock()
        for sim in prepared:
            sim.last_wall=published
            runtime.entries[sim.id]=Entry(owner, sim, published)
        result=service.movements(owner)
        result.update(initialized_count=len(prepared), skipped=skipped,
                      initialization_source='Loaded vehicles and compatible active outgoing network routes')
        return result
