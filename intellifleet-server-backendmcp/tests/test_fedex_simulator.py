from datetime import date, datetime
from backend.fedex.models import SimulationInput
from backend.fedex.simulator import Simulation
from test_fedex_eligibility import schedules


def make_sim(schedules, **kwargs):
    request = SimulationInput(origin_station='UDRPU', gateway='DELGW', simulation_date=date(2026,9,29),
        shipment_ready_datetime=datetime(2026,9,29,18), speed=600, **kwargs)
    return Simulation(request, schedules, 0)


def test_completes(schedules):
    s = make_sim(schedules)
    assert s.status == 'ASSIGNED'
    assert s.advance(1)['status'] == 'WAITING_FOR_DEPARTURE'
    assert s.advance(30)['status'] == 'IN_TRANSIT'
    state = s.advance(108)
    assert state['status'] == 'ARRIVED_AT_GTW' and state['progress'] == 1
    assert state['synthetic_data'] and state['location_source'] == 'DEMO_SIMULATION'
    assert state['current_eta'] == state['simulation_timestamp']


def test_pause_resume_speed(schedules):
    s = make_sim(schedules)
    state = s.control('pause', 30)
    assert s.advance(90)['progress'] == state['progress']
    s.control('resume', 90)
    assert s.advance(91)['progress'] > state['progress']
    s.control('speed', 91, 1200)
    assert s.snapshot()['simulation_speed'] == 1200
    s.control('stop', 92)
    progress = s.progress
    s.advance(900)
    assert s.progress == progress


def test_reproducible(schedules):
    a,b = make_sim(schedules),make_sim(schedules)
    for tick in (1, 20, 50, 108):
        x,y=a.advance(tick),b.advance(tick)
        assert (x['progress'], x['latitude'], x['status']) == (y['progress'], y['latitude'], y['status'])
