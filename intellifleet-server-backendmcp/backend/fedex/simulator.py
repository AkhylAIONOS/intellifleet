"""Clock-driven synthetic movement. Never reads/writes the UniFleet database."""
import math
from bisect import bisect_right
from itertools import accumulate
from dataclasses import asdict, replace

from backend.operations.road_routing_engine import road_routing_engine
from datetime import timedelta
from uuid import uuid4

from .eligibility import evaluate, local_datetime
from .models import SimulationInput

# Approximate CITY centres, deliberately not asserted to be FedEx facilities.
DEMO_LOCATIONS = {'UDRPU': (24.5854, 73.7125), 'DELGW': (28.6139, 77.2090)}


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


class Simulation:
    def __init__(self, request: SimulationInput, schedules, wall_time: float, road_waypoints=None):
        result = evaluate(schedules, request)
        selected = next((c for c in result['candidates'] if c['schedule_id'] == request.schedule_id and c['eligible']), None) if request.schedule_id else result['selected']
        if not selected:
            raise ValueError('No eligible selected service; inspect cutoff candidates')
        schedule = next(s for s in schedules if s.schedule_id == selected['schedule_id'])
        origin = schedule.origin_coordinates or DEMO_LOCATIONS.get(request.origin_station)
        destination = schedule.destination_coordinates or DEMO_LOCATIONS.get(request.gateway)
        if not origin or not destination:
            raise ValueError('No labelled demo location mapping for this lane; schedule evaluation remains available')
        self.id = str(uuid4())
        self.request = request
        self.schedules = schedules
        self.selected = selected
        self.notice = result['schedule_notice']
        self.origin = origin
        self.destination = destination
        self.road_route = None
        if selected['mode'] == 'SURFACE':
            points = road_waypoints or [origin, destination]
            parts = [road_routing_engine.get_route(*a, *b, optimization=request.road_optimization)
                     for a,b in zip(points, points[1:])]
            self.road_route = parts[0]
            if len(parts) > 1:
                self.road_route = replace(parts[0], destination=parts[-1].destination,
                    snapped_destination=parts[-1].snapped_destination,
                    geometry=[*parts[0].geometry, *[point for part in parts[1:] for point in part.geometry[1:]]],
                    distance_km=sum(part.distance_km for part in parts),
                    duration_minutes=sum(part.duration_minutes for part in parts),
                    route_id=':'.join(part.route_id for part in parts))
            self.route = self.road_route.geometry
        else:
            self.route = [self.origin, self.destination]
        self.data_source = schedule.data_source
        self.now = local_datetime(request.shipment_ready_datetime)
        self.last_wall = wall_time
        self.speed = request.speed
        self.paused = False
        self.stopped = False
        self.progress = 0.0
        self.status = 'ASSIGNED'
        self.state_history = ['READY', 'ASSIGNED']
        self.duration = (selected['eta'] - selected['etd']).total_seconds()
        self.current_eta = selected['eta']
        self.actual_departure_at = None
        self.actual_arrival_at = None
        self.hold_until = None
        self.travel_factor = 1.0
        self.events = []
        self.alerts = []
        self.sequence = 0
        self.random_checked = False

    def advance(self, wall_time):
        elapsed = max(0.0, wall_time - self.last_wall)
        self.last_wall = max(self.last_wall, wall_time)
        if self.paused or self.stopped or self.progress >= 1:
            return self.snapshot()
        previous = self.now
        self.now += timedelta(seconds=elapsed * self.speed)
        travel_start = max(previous, self.selected['etd'], self.hold_until or self.selected['etd'])
        moving_seconds = max(0, (self.now - travel_start).total_seconds())
        self.progress = min(1.0, self.progress + moving_seconds * self.travel_factor / self.duration)
        if self.progress >= 1:
            self.now = self.current_eta
            self.actual_arrival_at = self.current_eta
            state = 'ARRIVED_AT_GTW'
        elif self.now < self.selected['etd']:
            state = 'WAITING_FOR_DEPARTURE'
        elif self.hold_until and self.now < self.hold_until:
            state = 'DELAYED'
        else:
            state = 'IN_TRANSIT'
        if self.status != state:
            self.state_history.append(state)
        self.status = state
        if self.progress > 0 and self.actual_departure_at is None:
            self.actual_departure_at = self.selected['etd']
        self.sequence += 1
        return self.snapshot()

    @property
    def route(self):
        return self._route

    @route.setter
    def route(self, geometry):
        # Prepare once, including when legacy Air/Rail callers supply waypoints.
        self._route = list(geometry)
        self._lengths = [distance_km(a,b) for a,b in zip(self._route,self._route[1:])]
        self._cumulative = [0.0, *accumulate(self._lengths)]
        self._geometry_distance = self._cumulative[-1]

    def snapshot(self):
        segments = getattr(self, 'journey_segments', [])
        timed_segments = [s for s in segments if 'end_progress' in s]
        active_segment = next((s for s in timed_segments if self.progress < s['end_progress']), timed_segments[-1] if timed_segments else None)
        segment_progress = None
        travelled = self._geometry_distance*self.progress
        if active_segment and 'start_progress' in active_segment:
            segment_progress = min(1.0, max(0.0, (self.progress-active_segment['start_progress']) /
                max(active_segment['end_progress']-active_segment['start_progress'], 1e-12)))
            start = self._cumulative[active_segment['start_index']]
            end = self._cumulative[active_segment['end_index']]
            travelled = start + (end-start)*segment_progress
        index = min(len(self._lengths)-1, max(0, bisect_right(self._cumulative, travelled)-1))
        if active_segment is None:
            active_segment = next((s for s in segments if s['start_index'] <= index < s['end_index']), None)
        a,b = self.route[index:index+2]
        fraction = min(1.0, max(0.0, (travelled-self._cumulative[index])/max(self._lengths[index],1e-12)))
        lat = a[0]+(b[0]-a[0])*fraction
        lng = a[1]+(b[1]-a[1])*fraction
        heading = (math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))+360)%360
        moving = self.status == 'IN_TRANSIT' and not self.paused and not self.stopped
        result = dict(data_source=self.data_source, schedule_id=self.selected["schedule_id"], heading=heading, delay_minutes=round((self.current_eta-self.selected["eta"]).total_seconds()/60,2), simulation_id=self.id, shipment_id=self.request.shipment_id,
                    origin_station=self.request.origin_station, gateway=self.request.gateway,
                    risk_score=getattr(self, 'plan_risk', None), journey_id=getattr(self, 'journey_id', None), plan_id=getattr(self, 'plan_revision_id', None),
                    revision=getattr(self, 'plan_revision', None), journey_segments=getattr(self, 'journey_segments', []),
                    active_leg_index=segments.index(active_segment) if active_segment else None,
                    segment_progress=segment_progress, active_vehicles=active_segment.get('vehicles', []) if active_segment else [],
                    mode=active_segment['mode'] if active_segment else next((segment['mode'] for segment in getattr(self, 'journey_segments', []) if segment['start_index'] <= index < segment['end_index']), self.selected['mode']), run=self.selected['run'], service=self.selected['service'],
                    simulation_timestamp=self.now.isoformat(), latitude=lat, longitude=lng,
                    speed_kmph=round(self._geometry_distance / (self.duration/3600) * self.travel_factor, 2) if moving else 0,
                    speed_basis='Map-road distance / existing schedule duration; simulated, not live traffic' if self.road_route else 'Synthetic straight-line distance, not measured vehicle speed',
                    progress=self.progress, status=self.status, paused=self.paused, stopped=self.stopped,
                    scheduled_etd=self.selected['etd'].isoformat(), scheduled_eta=self.selected['eta'].isoformat(),
                    current_eta=self.current_eta.isoformat(), cutoff=self.selected['cutoff'].isoformat(),
                    retrieval=self.selected['retrieval'].isoformat() if self.selected['retrieval'] else None,
                    onward_readiness='Unverified: source retrieval milestone shown separately; no onward uplift schedule supplied',
                    synthetic_data=True, location_source='DEMO_SIMULATION', simulation_speed=self.speed,
                    route=self.route,
                    route_id=self.road_route.route_id if self.road_route else None,
                    route_source=self.road_route.source if self.road_route else 'Approximate mode-specific demo geometry',
                    route_distance_km=self.road_route.distance_km if self.road_route else self._geometry_distance,
                    road_estimated_duration_minutes=self.road_route.duration_minutes if self.road_route else None,
                    optimization_mode=self.road_route.optimization if self.road_route else None,
                    road_routing_status='READY' if self.road_route else 'NOT_APPLICABLE',
                    distance_travelled_km=round(travelled,3),
                    distance_remaining_km=round(self._geometry_distance-travelled,3), current_segment=index,
                    road_snapping={name:asdict(getattr(self.road_route,name)) for name in ('origin','destination','snapped_origin','snapped_destination')} if self.road_route else None,
                    routing_capabilities={'FASTEST':True,'SHORTEST':False,'CHEAPEST':False,'blocked_segment_avoidance':False,'exact_tolls':False} if self.road_route else None,
                    location_notice='Road-network simulation based on OpenStreetMap routing data; approximate facility coordinates snapped to roads, not actual FedEx GPS. Schedule ETA retained; map travel time is an estimate.' if self.road_route else 'Approximate city centres and synthetic straight-line interpolation; not actual GPS or rail geometry.',
                    schedule_notice=self.notice, seed=self.request.seed, random_events=self.request.random_events,
                    sequence=self.sequence, events=self.events, alerts=self.alerts, state_history=self.state_history)
        from backend.control_tower.status import operational_fields
        facts=dict(planned_eta=self.selected['eta'],current_eta=self.current_eta,
                   actual_departure_at=self.actual_departure_at,actual_arrival_at=self.actual_arrival_at,
                   deadline=getattr(self,'plan_deadline',None))
        fields=operational_fields(facts,self.now)
        result.update(business_status=fields.pop('status'),operational_metrics=fields,
                      actual_departure_at=self.actual_departure_at.isoformat() if self.actual_departure_at else None,
                      actual_arrival_at=self.actual_arrival_at.isoformat() if self.actual_arrival_at else None,
                      actual_timestamp_source='SYNTHETIC_TELEMETRY',telemetry_source='SYNTHETIC_TELEMETRY',
                      baseline_sla_met=fields['baseline_sla_met'],current_sla_met=fields['current_sla_met'])
        return result

    def control(self, action, wall_time, speed=None):
        self.advance(wall_time)
        if action == 'pause': self.paused = True
        elif action == 'resume':
            self.paused = False
            # Presenter may finish the hold explicitly. Consume its simulated
            # time, retaining both the frozen position and revised business ETA.
            if self.hold_until and self.now < self.hold_until:
                self.now = self.hold_until
                self.status = 'IN_TRANSIT'
        elif action == 'stop': self.stopped = True
        elif action == 'speed':
            if speed is None: raise ValueError('speed is required')
            self.speed = speed
        self.sequence += 1
        return self.snapshot()
