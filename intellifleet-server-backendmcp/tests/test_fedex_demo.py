import json
from datetime import date, datetime, timedelta
from pathlib import Path
import pytest
from backend.fedex.importer import load_schedules, workbook_path
from backend.fedex.eligibility import evaluate
from backend.fedex.models import SimulationInput, DisruptionInput
from backend.fedex.simulator import Simulation
from backend.fedex.disruptions import inject


def test_workbook_demo_end_to_end():
    if not workbook_path().exists(): pytest.skip('Local customer workbook not supplied')
    config=json.loads((Path(__file__).parents[1]/'backend/fedex/demo_inputs.json').read_text())
    schedules=load_schedules(); selected=[]
    for scenario in ('a','b'):
        request=SimulationInput(origin_station=config['origin_station'],gateway=config['gateway'],simulation_date=date(2026,9,29),
            shipment_ready_datetime=datetime.fromisoformat('2026-09-29T'+config[f'scenario_{scenario}_ready_time']),speed=config['speed'])
        result=evaluate(schedules,request);selected.append(result['selected']['mode'])
        simulation=Simulation(request,schedules,0)
        if scenario=='b':
            simulation.advance(40)
            baseline=simulation.current_eta
            inject(simulation,DisruptionInput(expected_delay_minutes=config['manual_delay_minutes']))
            assert simulation.current_eta==baseline+timedelta(minutes=30)
            assert simulation.alerts[-1]['recommended_action']
        assert simulation.advance(200)['status']=='ARRIVED_AT_GTW'
    assert selected==['AIR','SURFACE']
