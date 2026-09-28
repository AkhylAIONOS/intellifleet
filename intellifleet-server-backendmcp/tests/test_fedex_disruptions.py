from datetime import timedelta
import pytest
from backend.fedex.disruptions import inject, maybe_seeded_event
from backend.fedex.models import DisruptionInput
from test_fedex_simulator import make_sim
from test_fedex_eligibility import schedules


@pytest.mark.parametrize('kind', ['DELAY','SLOWDOWN','UNEXPECTED_STOP','BREAKDOWN'])
def test_eta_and_completion(schedules, kind):
    s = make_sim(schedules)
    s.advance(40)
    old = s.current_eta
    event = inject(s, DisruptionInput(event_type=kind, expected_delay_minutes=30))
    assert s.current_eta == old + timedelta(minutes=30)
    assert event['synthetic_data'] and event['expected_delay_minutes'] == 30
    assert s.advance(108)['progress'] < 1
    assert s.advance(112)['status'] == 'ARRIVED_AT_GTW'


def test_stop_holds_position(schedules):
    s=make_sim(schedules); s.advance(40)
    old=s.progress
    inject(s,DisruptionInput(expected_delay_minutes=30))
    assert s.advance(41)['progress'] == old
    assert s.advance(44)['progress'] > old


def test_invalid_event_states(schedules):
    s=make_sim(schedules)
    with pytest.raises(ValueError): inject(s,DisruptionInput())
    s.advance(40); s.selected['mode']='AIR'
    with pytest.raises(ValueError): inject(s,DisruptionInput(event_type='BREAKDOWN'))
    s.advance(200)
    with pytest.raises(ValueError): inject(s,DisruptionInput())


def test_seeded_opt_in(schedules):
    a,b=make_sim(schedules,random_events=True,seed=1),make_sim(schedules,random_events=True,seed=1)
    for s in (a,b): s.advance(50); maybe_seeded_event(s)
    assert len(a.events)==len(b.events)==1 and a.current_eta==b.current_eta
    c=make_sim(schedules); c.advance(50); maybe_seeded_event(c)
    assert not c.events
    d=make_sim(schedules,random_events=True,seed=42); d.advance(50); maybe_seeded_event(d)
    assert not d.events
