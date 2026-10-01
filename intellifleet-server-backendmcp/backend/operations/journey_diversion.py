"""Airport diversion planning restricted to verified Air edges and Ground links."""
import re
from copy import deepcopy
from backend.planning.lifecycle import resolve, record, explicit_live_recovery
from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService
from backend.operations.journey_queries import reply, route_text


async def answer(owner,message,context,selected_id=None):
    text=message.casefold()
    if not re.search(r'airport|landing|cannot land',text) or not re.search(r'closed|closure|alternative|alternate|diver|cannot land',text):return None
    selected,error=resolve(context,message,selected_id)
    if error:return reply(error)
    air=[l for l in selected.get('route_legs',[]) if l['route_type']=='air']
    if not air:return reply('The selected journey has no Air leg to divert.')
    if explicit_live_recovery(message):return reply('Live aircraft diversion needs verified current position, remaining range and landing access. Those data are not supplied; no live diversion was applied.')
    service=PlanningService();network=service.load_network(owner)
    closed=selected.get('closed_air_endpoint') or air[-1]['to_location']
    nodes={w['name']:w for w in network['warehouses']}
    iata=nodes.get(closed,{}).get('nearest_airport_iata')
    closed_nodes={closed} | ({w['name'] for w in network['warehouses'] if w.get('nearest_airport_iata')==iata} if iata else set())
    changes=deepcopy(selected.get('planning_changes') or {})
    changes['blocked_route_ids']=list(set(changes.get('blocked_route_ids',[])+[r['route_id'] for r in network['routes'] if r['route_type']=='air' and r['to_location'] in closed_nodes]))
    request=PlanningRequest(**selected['planning_request']).model_copy(update={'allowed_modes':['multimodal'],'required_mode_sequence':['air','road']})
    result=service.plan(owner,request,changes=changes)
    candidates=result.get('candidate_plans') or []
    lines=['Verified origin-based Air → Ground diversion options (not live aircraft navigation):']
    for p in candidates:
        landing=[l for l in p['route_legs'] if l['route_type']=='air'][-1]['to_location']
        lines.append(f"Landing node {landing}; airport {nodes.get(landing,{}).get('nearest_airport_iata') or 'no airport identifier supplied'}; cost {p['operational_cost']}; additional cost {p['operational_cost']-selected['cost']:.2f}; duration {p['duration_hours']} h; additional duration {p['duration_hours']-selected['duration_hours']:.2f} h; risk {p['risk_score']}; vehicles {[v.get('label') or v['id'] for v in p['vehicles']]}\n{route_text(p)}")
    if re.search(r'\bcompare\b',text):return reply('\n'.join(lines) if candidates else 'No verified alternate Air-connected landing node with a feasible Ground continuation. '+result['reason'])
    from backend.config.redis import set_active_planning_context
    selected['planning_changes']=changes;selected['closed_air_endpoint']=closed
    if not candidates:
        selected.setdefault('journeys',{})[selected['journey_id']]={k:v for k,v in selected.items() if k!='journeys'}
        await set_active_planning_context(owner,selected)
        return reply('No verified alternate Air-connected landing node with a feasible Ground continuation. '+result['reason'])
    from backend.agents.supervisor import _context_from_result, _format_planning_result
    result['applied_changes']=changes
    updated=record(owner,result,selected,_context_from_result(result,selected),revise=True,planner_reroute=True)
    await set_active_planning_context(owner,updated)
    return {'success':True,'response':lines[0]+'\n'+lines[1].split('\n',1)[0]+'\n'+_format_planning_result(result,message),
            'actions':[{'type':'supply_chain_planning_operation','data':result}]}
