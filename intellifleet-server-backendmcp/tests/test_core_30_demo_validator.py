from tests.run_core_30_demo_validation import validate_decision_support_answer


def test_ps27_accepts_natural_language_planner_grounded_explanation():
    answer = (
        "For this shipment, I'd recommend the Ground plan.\n\n"
        "Why: It provides the strongest calculated balance of cost, time, "
        "reliability, risk and utilization."
    )
    assert validate_decision_support_answer(answer)[0] is True


def test_ps27_rejects_bare_recommendation():
    valid, reason = validate_decision_support_answer("I recommend Ground.")
    assert valid is False
    assert "reason" in reason
