"""Presentation regressions: bounded operational retrieval and deterministic formatting."""
import copy
import pytest
from backend.operations import chat
from backend.agents.supervisor import _readable_time, _format_planning_result


def movement(index, origin='OTHER', gateway='ELSEWHERE'):
    return {'simulation_id':f'sim-{index}', 'shipment_id':f'SHIP-{index}', 'origin_station':origin,
        'gateway':gateway,'mode':'SURFACE','service':'Pickup','status':'DELAYED','progress':.3,
        'delay_minutes':30,'scheduled_eta':'2026-09-30T12:00:00+05:30',
        'current_eta':'2026-09-30T12:30:00+05:30','data_source':'FEDEX_SOURCE',
        'alerts':[{'recommended_action':'Notify gateway; confirm handover; continue monitoring. No automatic reroute.',
                   'reason':'Verified recovery capacity and onward schedule unavailable.'}]}


@pytest.mark.parametrize('origin,gateway',[('UDRPU','DELGW'),('ALPHA','BETA')])
def test_lane_query_does_not_dump_other_movements(monkeypatch,origin,gateway):
    data=[movement(i) for i in range(100)] + [movement(100,origin,gateway)]
    monkeypatch.setattr(chat,'all_movements',lambda user:{'movements':data})
    answer=chat.answer(1,f'What is happening with the current {origin} to {gateway} shipment? Show its current status, delay, revised ETA and recommended action.', 'sim-2')
    assert 'SHIP-100' in answer['response'] and 'SHIP-2' not in answer['response']
    for expected in ('30 min','30 Sep 2026, 12:00 IST','30 Sep 2026, 12:30 IST','Notify gateway','Verified recovery'):
        assert expected in answer['response']
    assert len(answer['response'])<1000
    assert answer['actions'][0]['data']['selected']=='sim-100'


def test_selected_and_explicit_identifiers_and_ambiguity(monkeypatch):
    data=[movement(i) for i in range(100)]
    monkeypatch.setattr(chat,'all_movements',lambda user:{'movements':data if user['user_id']==1 else []})
    before=copy.deepcopy(data)
    for message, selected, expected in [('Current shipment status','sim-2','SHIP-2'),('Shipment status SHIP-1','sim-2','SHIP-1'),('Tell me about SHIP-1','sim-2','SHIP-1'),('What is its revised ETA?','sim-4','SHIP-4')]:
        result=chat.answer(1,message,selected)['response']
        assert expected in result and result.count('Current shipment:')==1
    assert 'Specify the shipment ID' in chat.answer(1,'Current shipment status')['response']
    assert 'No matching' in chat.answer(1,'Current status from Unknown to Nowhere')['response']
    assert 'Specify' in chat.answer(2,'Current shipment status','sim-2')['response']
    assert chat.answer(1,'Show all delayed movements')['response'].count('Current shipment:')==10
    assert data==before


def test_ist_conversion_rollover_and_naive_honesty():
    assert _readable_time('2026-09-29T23:30:00Z')=='30 Sep 2026, 05:00 IST'
    assert _readable_time('2026-09-30T12:30:00+05:30')=='30 Sep 2026, 12:30 IST'
    assert 'timezone not supplied' in _readable_time('2026-09-30T12:30:00')


def test_default_summary_is_concise_and_details_remain_available():
    plan={'plan_id':'a','product':'Ground','mode':'road','operational_cost':275796.5,'duration_hours':31.19,
      'eta':'2026-09-30T06:30:00Z','risk_score':.1405,'reliability':.95,'score':.3,
      'route_legs':[{'from_location':'Delhi','to_location':'Mumbai','route_type':'road','distance':1400,'duration':30}],
      'vehicles':[{'label':'TRK-031','capacity':7000,'assigned_load_kg':6000,'utilization_percentage':85.71}],
      'score_components':{'normalized_cost':1,'weighted_contributions':{'cost':.3}},'cost_breakdown':{'base_transport':200000},'risk_breakdown':{'route':.1}}
    result={'recommended_plan':plan,'planning_request':{'source':'Delhi','destination':'Mumbai','shipment':{'weight_kg':6000},'objective':'balanced'}}
    concise=_format_planning_result(result)
    assert concise.startswith('Recommended plan: Ground.')
    for value in ('₹275,796.50','31.19','14.05%','95.00%','TRK-031','12:00 IST'):assert value in concise
    assert 'Normalized' not in concise and 'Weighted' not in concise and 'Balanced score:' not in concise
    detailed=_format_planning_result(result,'Show score breakdown and explain calculation')
    for value in ('Normalized Cost','Weighted Contributions','Balanced score:','Cost breakdown'):assert value in detailed
