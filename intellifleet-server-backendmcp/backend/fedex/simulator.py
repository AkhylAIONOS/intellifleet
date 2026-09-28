"""Clock-driven synthetic movement. Never reads/writes the UniFleet database."""
import math
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
    def __init__(self, request: SimulationInput, schedules, wall_time: float):
        result = evaluate(schedules, request)
        selected = next((c for c in result['candidates'] if c['schedule_id'] == request.schedule_id and c['eligible']), None) if request.schedule_id else result['selected']
        if not selected:
            raise ValueError('No eligible selected service; inspect cutoff candidates')
        if request.origin_station not in DEMO_LOCATIONS or request.gateway not in DEMO_LOCATIONS:
            raise ValueError('No labelled demo location mapping for this lane; schedule evaluation remains available')
        self.id = str(uuid4())
        self.request = request
        self.schedules = schedules
        self.selected = selected
        self.notice = result['schedule_notice']
        self.origin = DEMO_LOCATIONS[request.origin_station]
        self.destination = DEMO_LOCATIONS[request.gateway]
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
        self.sequence += 1
        return self.snapshot()

    def snapshot(self):
        lat = self.origin[0] + (self.destination[0] - self.origin[0]) * self.progress
        lng = self.origin[1] + (self.destination[1] - self.origin[1]) * self.progress
        moving = self.status == 'IN_TRANSIT' and not self.paused and not self.stopped
        return dict(simulation_id=self.id, shipment_id=self.request.shipment_id,
                    origin_station=self.request.origin_station, gateway=self.request.gateway,
                    mode=self.selected['mode'], run=self.selected['run'], service=self.selected['service'],
                    simulation_timestamp=self.now.isoformat(), latitude=lat, longitude=lng,
                    speed_kmph=round(distance_km(self.origin, self.destination) / (self.duration/3600) * self.travel_factor, 2) if moving else 0,
                    speed_basis='Synthetic straight-line distance, not measured vehicle speed',
                    progress=self.progress, status=self.status, paused=self.paused, stopped=self.stopped,
                    scheduled_etd=self.selected['etd'].isoformat(), scheduled_eta=self.selected['eta'].isoformat(),
                    current_eta=self.current_eta.isoformat(), cutoff=self.selected['cutoff'].isoformat(),
                    retrieval=self.selected['retrieval'].isoformat() if self.selected['retrieval'] else None,
                    onward_readiness='Unverified: source retrieval milestone shown separately; no onward uplift schedule supplied',
                    synthetic_data=True, location_source='DEMO_SIMULATION', simulation_speed=self.speed,
                    route=[self.origin, self.destination], location_notice='Approximate city centres and synthetic straight-line interpolation; not FedEx GPS or road geometry.',
                    schedule_notice=self.notice, seed=self.request.seed, random_events=self.request.random_events,
                    sequence=self.sequence, events=self.events, alerts=self.alerts, state_history=self.state_history)

    def control(self, action, wall_time, speed=None):
        self.advance(wall_time)
        if action == 'pause': self.paused = True
        elif action == 'resume': self.paused = False
        elif action == 'stop': self.stopped = True
        elif action == 'speed':
            if speed is None: raise ValueError('speed is required')
            self.speed = speed
        self.sequence += 1
        return self.snapshot()
