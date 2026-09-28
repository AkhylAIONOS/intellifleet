from datetime import date, datetime, timedelta
import pytest
from backend.fedex.eligibility import evaluate
from backend.fedex.importer import load_schedules, normalize_row, workbook_path
from backend.fedex.models import EligibilityInput


def request(ready='2026-09-29T16:00:00'):
    return EligibilityInput(origin_station='udrpu', gateway='delgw', simulation_date=date(2026,9,29), shipment_ready_datetime=datetime.fromisoformat(ready))


@pytest.fixture
def schedules():
    return [normalize_row('Air', 2, {'Origin Station':'UDRPU','Transit GTW':'DELGW','Mode':'Air','Run':'1','Handover':'16:30','ETD':'20:00','ETA':'21:20','Retrieval':'23:50'}),
            normalize_row('Surface', 2, {'Origin Station':'UDRPU','Transit Hub/GTW':'DELGW','Mode':'Surface','Run':'1','Handover at Orgn':'21:30','ETD':'22:00','ETA':'12:00','TT (hours)':'14:00'})]


def test_before_cutoff_and_equal(schedules):
    assert evaluate(schedules, request())['selected']['mode'] == 'AIR'
    assert evaluate(schedules, request('2026-09-29T16:30'))['selected']['mode'] == 'AIR'


def test_after_air_cutoff_surface_overnight(schedules):
    result = evaluate(schedules, request('2026-09-29T18:00'))
    assert result['selected']['mode'] == 'SURFACE'
    assert result['selected']['eta'].date() == date(2026,9,30)
    assert 'after handover cutoff' in result['candidates'][0]['reason']


def test_no_eligible(schedules):
    assert evaluate(schedules, request('2026-09-29T23:00'))['selected'] is None


def test_missing_and_bad_cutoff(schedules):
    for value in ('-', 'bad'):
        schedules[0] = normalize_row('Air', 2, {'Origin Station':'UDRPU','Transit GTW':'DELGW','Mode':'Air','Handover':value,'ETD':'20:00','ETA':'21:20'})
        assert not evaluate(schedules, request())['candidates'][0]['eligible']


def test_departure_rollover(schedules):
    s = schedules[0].model_copy(update={'cutoff_minutes':1380, 'etd_minutes':60, 'eta_minutes':120})
    c = evaluate([s], request())['selected']
    assert c['etd'].date() == date(2026,9,30) and c['eta'] > c['etd']


def test_selection_not_mode_priority(schedules):
    s = schedules[1].model_copy(update={'eta_minutes':1200, 'etd_minutes':1080, 'cutoff_minutes':1020})
    assert evaluate([*schedules[:1], s], request())['selected']['mode'] == 'SURFACE'


def test_actual_workbook():
    if not workbook_path().exists(): pytest.skip('Local customer workbook not supplied')
    ss = load_schedules()
    assert evaluate(ss, request())['selected']['mode'] == 'AIR'
    assert evaluate(ss, request('2026-09-29T18:00'))['selected']['mode'] == 'SURFACE'


def test_inconsistent_not_selected(schedules):
    schedules[0].valid = False
    assert evaluate(schedules, request())['selected']['mode'] == 'SURFACE'
