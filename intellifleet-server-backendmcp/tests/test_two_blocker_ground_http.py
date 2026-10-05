"""One HTTP conversation through real tool validation, planner and context storage."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.routes.auth import get_current_user
from backend.api import chat_api
from backend.agents import supervisor as sup
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.config import redis
from backend.fedex import telemetry
from backend.planning.service import PlanningService
from test_operations import loaded

PROMPT='Plan a 6,000 kg shipment from Mumbai to Bengaluru using the best available option.'


@pytest.mark.parametrize('objective',['best_available','best available','balanced'])
def test_ground_six_requests_one_http_conversation(loaded,monkeypatch,objective,caplog):
    network,runtime,_=loaded
    monkeypatch.setattr(telemetry,'runtime',runtime)
    memory={}
    class MemoryRedis:
        def __init__(self):self.values={}
        async def get(self,key):return self.values.get(key)
        async def set(self,key,value):self.values[key]=value
    storage=MemoryRedis()
    monkeypatch.setattr(redis,'redis_client',storage)
    monkeypatch.setattr(sup,'log_token_usage',lambda *args:None)
    replies=iter(['unified_supply_chain_plan',json.dumps(dict(source='Mumbai',destination='Bengaluru',weight_kg=6000,objective=objective))])
    async def invoke(_):return SimpleNamespace(content=next(replies))
    agent=object.__new__(sup.SchemaAwareSupervisor)
    agent.llm=SimpleNamespace(ainvoke=invoke);agent.tools=asyncio.run(load_mcp_tools());agent.tool_metadata=agent._build_tool_metadata()
    monkeypatch.setattr(chat_api,'supervisor',agent)
    app=FastAPI();app.include_router(chat_api.router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    client=TestClient(app)
    def ask(message):
        r=client.post('/mcp-agent',json={'message':message,'session_id':'one-ground-conversation'})
        assert r.status_code==200,r.text
        body=r.json();assert body['success'],body
        memory['context']=asyncio.run(redis.get_active_planning_context(1))
        assert not any(word in body['response'] for word in ['Traceback','validation error','Pydantic','Network Error'])
        return body
    first=ask(PROMPT)
    data=first['actions'][0]['data'];plan=data['recommended_plan'];before=deepcopy(memory['context'])
    assert plan['mode']=='road' and [l['route_id'] for l in plan['route_legs']]==[65]
    assert plan['vehicles'][0]['label']=='TRK-032' and plan['vehicles'][0]['capacity']==7000
    assert plan['operational_cost']==203091.5 and plan['duration_hours']==23.48
    assert plan['risk_score']==.1276 and plan['reliability']==.95
    assert any(p['mode']=='air' for p in data['candidate_plans'])
    assert plan==memory['context']['selected_plan']
    why=ask('Why did you choose this option?')['response']
    assert all(k in why for k in ['cost','ETA','risk','reliability','utilization','Alternative'])
    assert 'already Ground' in ask('Compare it with Ground.')['response']
    second=ask('Show only the second option.')['response']
    assert data['candidate_plans'][1]['plan_id'] in second and plan['plan_id'] not in second
    all_options=ask('Show all options again.')['response']
    assert all(p['plan_id'] in all_options for p in data['candidate_plans'])
    assert memory['context']==before
    draft=ask('What if that route becomes unavailable?')['response']
    assert 'No supported scenario' not in draft
    scenario=memory['context']['current_scenario']
    assert scenario['changes']['blocked_route_ids']==[65]
    alternate=scenario['scenario']['recommended_plan']
    assert alternate is None or all(l['route_id']!=65 for l in alternate['route_legs'])
    assert memory['context']['selected_plan']==plan
    assert memory['context']['candidate_plans']==data['candidate_plans']
    assert set(storage.values)=={'message_store:user_id:1:history','message_store:user_id:1:active_planning_context'}
