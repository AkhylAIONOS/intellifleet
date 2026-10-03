import asyncio
from types import SimpleNamespace
from backend.agents.grounded_composer import compose, planning_facts


def test_model_cannot_inject_route_cost_or_prose():
    result={'recommended_plan':dict(mode='road',route_legs=[dict(route_id=7,from_location='A',to_location='B')],vehicles=[dict(id=3,label='TRK-3')],operational_cost=100,duration_hours=2,eta='2030-01-01T12:00:00Z',risk_score=.1,reliability=.9,sla_met=True),'reason':'Calculated feasible candidate'}
    class Model:
        async def ainvoke(self,messages):
            return SimpleNamespace(content='{"order":["recommendation","route","vehicle","cost_eta","risk_reliability","sla","reason"],"text":"Invented route 999 costs 1"}')
    text=asyncio.run(compose(result,'Briefly recommend a route',Model()))
    assert '₹100.00' in text and 'Route IDs: 7' in text
    assert 'Invented' not in text and '999' not in text
    assert planning_facts({})=={}


def test_invalid_layout_falls_back_to_exact_facts():
    class Model:
        async def ainvoke(self,messages):raise RuntimeError('Unavailable')
    assert asyncio.run(compose({},'brief',Model())) is None
    result={'recommended_plan':dict(mode='road',route_legs=[dict(route_id=7,from_location='A',to_location='B')],operational_cost=100,duration_hours=2,eta='2030-01-01T12:00:00Z',risk_score=.1,reliability=.9)}
    assert asyncio.run(compose(result,'brief',Model()))=='\n\n'.join(planning_facts(result).values())
