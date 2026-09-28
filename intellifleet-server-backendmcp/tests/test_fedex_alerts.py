from backend.fedex.alerts import evaluate_compatible_plan
from backend.fedex.disruptions import inject
from backend.fedex.models import DisruptionInput
from test_fedex_simulator import make_sim
from test_fedex_eligibility import schedules
from test_planning import NETWORK, req


def test_alert_is_structured_and_not_executed(schedules):
    s=make_sim(schedules);s.advance(40)
    inject(s, DisruptionInput(expected_delay_minutes=60))
    alert=s.alerts[-1]
    assert alert['severity']=='HIGH'
    assert alert['revised_eta']==s.current_eta.isoformat()
    assert alert['automatically_executed'] is False
    assert alert['eligible_alternatives']==[]
    assert 'No verified recovery' in alert['reason']


def test_existing_planner_adapter():
    result=evaluate_compatible_plan(req(),NETWORK,1)
    assert result['planning_result']['recommended_plan']
    assert result['schedule_validation_required'] and not result['automatically_executed']
