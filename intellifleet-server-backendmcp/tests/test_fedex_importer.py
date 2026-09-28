from pathlib import Path
import pytest
from backend.fedex.importer import load_schedules, normalize_row, time_minutes, workbook_path


def row(**changes):
    return {'Origin City': ' Udaipur ', 'Origin Station ': ' udrpu ', 'Transit Hub/GTW': 'delgw ',
            'Mode': 'Surface', 'Lane ': 'UDRPU-DELGW', 'Run': '1', 'Details': 'pickup',
            'Handover at Orgn': '21:30', 'ETD': '22:00', 'ETA': '12:00', 'TT (hours)': '14:00', **changes}


def test_normalization():
    s = normalize_row('Surface', 2, row())
    assert (s.origin_station, s.gateway, s.mode) == ('UDRPU', 'DELGW', 'SURFACE')
    assert s.transit_minutes == 840 and s.valid


def test_missing_cutoff_and_train_mismatch():
    s = normalize_row('Surface', 2, row(Mode='Train', ETD='22:15', ETA='08:30', **{'Handover at Orgn': '-'}))
    assert s.mode == 'RAIL' and s.source_mode == 'Train' and s.cutoff_minutes is None
    assert not s.valid and any('TRANSIT_MISMATCH' in x for x in s.warnings)
    assert s.source['TT (hours)'] == '14:00'


@pytest.mark.parametrize('value', ['25:00', '-1', 'nan', 'tomorrow', '12:90'])
def test_bad_times(value):
    with pytest.raises(ValueError): time_minutes(value)


def test_excel_midnight():
    assert time_minutes('0') == 0
    assert time_minutes(0) == 0
    assert time_minutes(str(16.5/24)) == 990


def test_invalid_duration_is_not_normalized():
    s = normalize_row('Surface', 2, row(**{'TT (hours)': '13:60'}))
    assert not s.valid and 'INVALID_TRANSIT_TIME' in s.warnings


def test_real_workbook():
    if not workbook_path().exists(): pytest.skip('Local customer workbook not supplied')
    schedules = load_schedules()
    lane = [x for x in schedules if x.origin_station == 'UDRPU' and x.gateway == 'DELGW']
    assert {s.mode for s in lane} == {'AIR', 'SURFACE'}
    assert all(s.valid for s in lane)
    bad = [s for s in schedules if s.origin_station == 'DDU' and s.gateway == 'NDLS']
    assert bad and all(any('TRANSIT_MISMATCH' in w for w in s.warnings) for s in bad)
