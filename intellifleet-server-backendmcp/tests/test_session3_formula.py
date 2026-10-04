from backend.fedex.importer import load_schedules,normalize_row
from test_fedex_importer import row


def test_surface_cached_formula_values_and_metadata():
    schedules=load_schedules()
    surface=[s for s in schedules if s.source_sheet=='Surface']
    assert len(surface)==28
    assert all(s.lane and s.lane!='UNSUPPORTED_FORMULA' for s in surface)
    first=next(s for s in surface if s.source_row==2)
    assert first.lane=='KANUPU-DELGW'
    assert first.source['Lane']=='KANUPU-DELGW'
    assert first.source_formulas['Lane']=='=_xlfn.CONCAT(B2,"-",C2)'
    assert first.source_value_provenance['Lane']=='WORKBOOK_CACHED_VALUE'


def test_uncached_lane_only_evaluates_known_source_concat():
    formula='=_xlfn.CONCAT(B2,"-",C2)'
    original=row(Lane=formula)
    result=normalize_row('Surface',2,original,formulas={'Lane':formula})
    assert result.lane==result.origin_station+'-'+result.gateway
    assert result.source['Lane']==formula
    result=normalize_row('Surface',2,row(Lane='=OTHER(B2)'),formulas={'Lane':'=OTHER(B2)'})
    assert result.lane=='Lane unavailable' and result.warnings
