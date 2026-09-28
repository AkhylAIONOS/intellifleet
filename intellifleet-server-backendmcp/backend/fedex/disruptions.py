import random
from datetime import timedelta

from .alerts import create_alert
from .models import DisruptionInput


def inject(simulation, request: DisruptionInput):
    s = simulation
    if s.stopped or s.paused or s.progress >= 1 or s.now < s.selected['etd']:
        raise ValueError('Inject events into a running, unpaused, in-transit simulation')
    if request.event_type == 'BREAKDOWN' and s.selected['mode'] != 'SURFACE':
        raise ValueError('BREAKDOWN is supported only for Surface movement')
    if len(s.events) >= 100:
        raise ValueError('Maximum 100 events per simulation; reset to begin a new run')
    original_eta = s.current_eta
    delay = timedelta(minutes=request.expected_delay_minutes)
    if request.event_type == 'SLOWDOWN':
        remaining = (1 - s.progress) * s.duration
        old_seconds = remaining / s.travel_factor
        s.travel_factor = remaining / (old_seconds + delay.total_seconds())
    else:
        s.hold_until = max(s.now, s.hold_until or s.now) + delay
        s.status = 'DELAYED'
        s.state_history.append('DELAYED')
    s.current_eta += delay
    severity = 'CRITICAL' if request.event_type == 'BREAKDOWN' else 'HIGH' if request.expected_delay_minutes >= 60 else 'WARNING'
    event = dict(event_id=f'{s.id}:{len(s.events)+1}', simulation_id=s.id, shipment_id=s.request.shipment_id,
                 event_type=request.event_type, severity=severity, timestamp=s.now.isoformat(),
                 location={'latitude':s.snapshot()['latitude'], 'longitude':s.snapshot()['longitude']}, progress=s.progress,
                 original_eta=original_eta.isoformat(), revised_eta=s.current_eta.isoformat(),
                 expected_delay_minutes=request.expected_delay_minutes, reason=request.reason,
                 synthetic_data=True, location_source='DEMO_SIMULATION')
    s.events.append(event)
    s.alerts.append(create_alert(s, event))
    s.sequence += 1
    return event


def maybe_seeded_event(simulation):
    s = simulation
    if not s.request.random_events or s.random_checked or not .25 <= s.progress < 1 or s.paused or s.stopped:
        return
    s.random_checked = True
    rng = random.Random(s.request.seed)
    if rng.random() < .25:
        inject(s, DisruptionInput(event_type='DELAY', expected_delay_minutes=rng.choice([15,30,45]), reason='Seeded synthetic delay'))
