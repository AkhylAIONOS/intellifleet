"""Explicit draft/compare/discard/apply lifecycle using the existing scenario service."""
from copy import deepcopy
from datetime import datetime, timedelta
import re
from backend.planning.lifecycle import resolve, record
from backend.planning.models import PlanningRequest, normalize_modes
from backend.planning.service import PlanningService
from backend.operations.journey_queries import reply, route_text


def intent(message):
    return bool(re.search(r'what[ -]if|\bscenario\b|\bhypothetical\b|\bsimulate\b|do not apply|\bdraft\b',message,re.I))


def describe(draft):
    a=draft['baseline'].get('recommended_plan') or {};b=draft['scenario'].get('recommended_plan') or {}
    if not b:return 'Draft scenario is infeasible: '+draft['scenario'].get('reason','No feasible plan.')+' Baseline remains unchanged.'
    delta=draft.get('comparison') or {}
    return (f"Draft scenario {draft['scenario_id']}; baseline unchanged.\n"
            f"Cost: {a.get('operational_cost')} → {b.get('operational_cost')}; delta {delta.get('cost_difference')}.\n"
            f"ETA duration: {a.get('duration_hours')} → {b.get('duration_hours')} h; delta {delta.get('eta_difference_hours')} h.\n"
            f"Risk: {a.get('risk_score')} → {b.get('risk_score')}; delta {delta.get('risk_difference')}.\n"
            f"SLA: {a.get('sla_met')} → {b.get('sla_met')}.\nBaseline route:\n{route_text(a)}\nScenario route:\n{route_text(b)}\n"
            f"Vehicles: {[v.get('label') or v['id'] for v in a.get('vehicles',[])]} → {[v.get('label') or v['id'] for v in b.get('vehicles',[])]}.\n"
            'Review the deterministic recommendation; explicitly apply or discard this draft.')


def changes_from_message(message,selected,network):
    text=message.casefold();changes={}
    fuel=re.search(r'fuel.{0,45}?(\d+(?:\.\d+)?)\s*%',text)
    if fuel:changes['fuel_cost_multiplier']=1+float(fuel[1])/100*(-1 if re.search(r'fuel.{0,25}(?:decrease|reduce|lower)',text) else 1)
    risk=re.search(r'risk.{0,30}?(\d+(?:\.\d+)?)\s*(?:%|percentage points)',text)
    if risk:changes['risk_delta']=float(risk[1])/100*(-1 if re.search(r'risk.{0,20}(?:decrease|reduce|lower)',text) else 1)
    weight=re.search(r'(?:weight|demand|load).{0,30}?(\d[\d,]*(?:\.\d+)?)\s*kg',text)
    if weight:changes['demand_weight_kg']=float(weight[1].replace(',',''))
    deadline=re.search(r'(\d+(?:\.\d+)?)\s*hours?\s*(earlier|later)|(?:earlier|later)\s+by\s+(\d+(?:\.\d+)?)\s*hours?',text)
    if deadline:
        baseline=selected.get('deadline') or selected.get('selected_plan',{}).get('eta')
        if baseline:
            hours=float(deadline[1] or deadline[3])*(-1 if 'earlier' in deadline[0] else 1)
            changes['deadline']=(datetime.fromisoformat(baseline)+timedelta(hours=hours)).isoformat()
    elif 'deadline' in text:
        from backend.agents.supervisor import _deadline_from_message
        parsed=_deadline_from_message(message)
        if parsed:changes['deadline']=parsed
    if re.search(r'block|unavailable|closed|cancel',text):
        routes=re.findall(r'route\s+(?:id\s*)?(\d+)',text)
        if routes:
            known={str(r['route_id']) for r in network['routes']}
            if any(r not in known for r in routes):raise ValueError('A requested route ID is absent from the loaded network.')
            changes['blocked_route_ids']=[int(r) for r in routes]
        elif re.search(r'(?:current|this|selected)\s+(?:road\s+|air\s+)?route',text):changes['blocked_route_ids']=selected.get('route_ids',[])
        for resource,field,key in [('vehicles','label','unavailable_vehicles'),('warehouses','name','unavailable_warehouses')]:
            values=[r[field] for r in network[resource] if any(re.search(r'(?<!\w)'+re.escape(str(r.get(k) or '').casefold())+r'(?!\w)',text) for k in ((field,'city') if resource=='warehouses' else (field,)) if r.get(k))]
            if values:changes[key]=values
        if 'assigned vehicle' in text:changes['unavailable_vehicles']=[v['label'] for v in selected.get('assigned_vehicles',[])]
    modes=re.search(r'(?:allow(?:ed)?\s+(?:modes?\s*)?|use\s+)(ground|surface|road|airway|air|multimodal|multi-modal)(?:\s+only)?',text)
    if modes:changes['allowed_modes']=normalize_modes(modes[1])
    if 'fuel' in text and 'fuel_cost_multiplier' not in changes:
        raise ValueError('Specify a numeric fuel percentage; no draft was created.')
    if 'deadline' in text and 'deadline' not in changes:
        raise ValueError('Specify a supported deadline or earlier/later hours; no draft was created.')
    if re.search(r'unavailable|closed|block',text):
        if 'warehouse' in text and not changes.get('unavailable_warehouses'):
            raise ValueError('No matching warehouse in the loaded network; no draft was created.')
        if re.search(r'vehicle|truck|aircraft',text) and not changes.get('unavailable_vehicles'):
            raise ValueError('No matching vehicle in the loaded network; no draft was created.')
    return changes


async def answer(owner,message,context,selected_id=None):
    if not intent(message):return None
    from backend.config.redis import set_active_planning_context
    from backend.agents.supervisor import _context_from_result, _format_planning_result
    text=message.casefold();service=PlanningService()
    draft=context.get('current_scenario')
    if re.search(r'\b(?:compare|discard|apply|keep)\b',text) and not re.search(r'what[ -]if|create|simulate|hypothetical|do not apply',text):
        if not draft:return reply('There is no active draft scenario in this chat.')
        if re.search(r'\bcompare\b',text):return reply(describe(draft))
        if re.search(r'\bkeep\b',text):return reply(describe(draft))
        action='discard' if re.search(r'\bdiscard\b',text) else 'apply'
        selected,error=resolve(context,str(draft.get('journey_id') or ''),draft.get('movement_id'))
        if error:return reply(error)
        if action=='apply' and selected.get('selected_plan_id')!=draft.get('baseline_plan_id'):
            return reply('The baseline has changed since this draft was created. Create a fresh scenario before applying it.')
        if action=='apply':
            from backend.fedex.telemetry import runtime
            try:
                sim=runtime.get(owner,selected.get('movement_id'))
            except KeyError:return reply('The baseline movement is unavailable; no scenario was applied.')
            if sim.stopped or sim.progress>=1:return reply('The baseline movement is stopped or completed; no scenario was applied.')
        try:
            result=service.scenario_action(owner,draft['scenario_id'],action)
        except (ValueError,KeyError) as exc:return reply(str(exc))
        updated=_context_from_result(result,selected if action=='apply' else context)
        if action=='apply':
            updated=record(owner,result,selected,updated,revise=True,planner_reroute=True)
        updated.pop('current_scenario',None);updated.pop('scenario_id',None)
        await set_active_planning_context(owner,updated)
        if action=='discard':return reply('Draft scenario discarded. Baseline and map remain unchanged.')
        result['recommended_plan']=result.get('approved_plan')
        return {'success':True,'response':'Draft scenario applied.\n'+_format_planning_result(result,message),
                'actions':[{'type':'supply_chain_planning_operation','data':result}]}
    selected,error=resolve(context,message,selected_id)
    if error:return reply(error)
    try:
        changes=changes_from_message(message,selected,service.load_network(owner))
        if not changes:return reply('No supported scenario change was specified. Supply fuel %, deadline, route/vehicle/warehouse exclusion, allowed mode, shipment weight or risk change. No plan was modified.')
        merged=deepcopy(selected.get('planning_changes') or {})
        for key,value in changes.items():
            merged[key]=list(dict.fromkeys(merged.get(key,[])+value)) if isinstance(value,list) and key!='allowed_modes' else value
        baseline={'planning_request':selected['planning_request'],'recommended_plan':deepcopy(selected['selected_plan'])}
        result=service.create_scenario(owner,PlanningRequest(**selected['planning_request']),merged,baseline=baseline)
    except (ValueError,KeyError) as exc:return reply(str(exc))
    result.update(journey_id=selected.get('journey_id'),movement_id=selected.get('movement_id'),baseline_plan_id=selected.get('selected_plan_id'))
    updated=deepcopy(context);updated.update(current_scenario=result,scenario_id=result['scenario_id'])
    await set_active_planning_context(owner,updated)
    return reply(describe(result))
