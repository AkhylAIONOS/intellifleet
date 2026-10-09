"""Authenticated workbook views and owner/session-scoped simulation chat."""
from datetime import datetime
from zoneinfo import ZoneInfo
import copy
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from backend.routes.auth import get_current_user
from backend.client_network import network, summary
from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService

router=APIRouter(tags=['Client network'])


@router.get('/chat/history')
def chat_history(user=Depends(get_current_user)):
    return {'success':True,'data':[]}


@router.delete('/chat/history')
def clear_history(user=Depends(get_current_user)):
    for key in list(contexts):
        if key[0]==user['user_id']:contexts.pop(key,None)
    return {'success':True,'data':[]}


@router.get('/client-network')
def model(user=Depends(get_current_user)):
    value=copy.deepcopy(network())
    value['summary']=summary(value)
    from backend.location_labels import labels
    value['locations']=labels(value['schedules'])
    return value


@router.get('/warehouses')
def warehouses(user=Depends(get_current_user)):
    from backend.location_labels import labels
    mapping=labels(network()['schedules'])
    rows=[dict(node,display_name=mapping[node['name']]['label'],location_aliases=mapping[node['name']]['aliases']) for node in network()['warehouses']]
    return {'success':True,'data':{'warehouses':rows,'total_warehouses':len(rows)}}


@router.get('/vehicles')
def vehicles(user=Depends(get_current_user)):
    rows=network()['vehicles']
    return {'success':True,'data':{'vehicles':rows,'total_vehicles':len(rows)}}


@router.get('/inventory')
def inventory(user=Depends(get_current_user)):
    return {'success':True,'data':{'inventory':network()['warehouses']}}


@router.get('/route_session')
def routes(user=Depends(get_current_user)):
    rows=[]
    for r in network()['routes']:
        a,b=r['source_coords'],r['destination_coords']
        geometry=[[a['lat'],a['lng']],[b['lat'],b['lng']]] if a['lat'] is not None and b['lat'] is not None else []
        rows.append(dict(route_id=r['route_id'],is_active=True,created_at=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
            data=dict(source=r['from_location'],destination=r['to_location'],route_type=r['route_type'],
                route_cost=r['cost'],source_coords=a,dest_coords=b,locations=[r['from_location'],r['to_location']],
                optimal_routes=[dict(route=geometry,geometry=geometry,path=[{'lat':p[0],'lng':p[1]} for p in geometry],distance=r['distance'],duration=r['duration'],
                                    data_source='CLIENT_SOURCE')],schedule=r['schedule'],data_source='CLIENT_SOURCE')))
    return {'success':True,'data':{'routes':rows,'alternative_routes':[],'multimodal_routes':[],'air_intermediate_routes':[]}}


class ChatInput(BaseModel):
    message: str
    session_id: str | None=None
    selected_operational_run_id: str | None=None
    selected_operational_run_ids: list[str]=Field(default_factory=list,max_length=38)
    operational_service_date: str | None=None
    workspace: str | None=None


from backend.client_chat import answer, contexts, plan_reply


@router.post('/mcp-agent')
async def chat(req:ChatInput,user=Depends(get_current_user)):
    from backend.chat_normalization import normalize
    try:
        normalized,source=await normalize(req.message)
        result=answer(user['user_id'],req,normalized)
        result['normalization_source']=source
        return result
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
