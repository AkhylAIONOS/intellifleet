"""GPT can arrange approved facts; its generated prose never becomes facts."""
import json
from langchain_core.messages import HumanMessage, SystemMessage


def planning_facts(result):
    plan=result.get('recommended_plan')
    if not isinstance(plan,dict) or not plan.get('route_legs'):
        return {}
    legs=plan['route_legs']
    route=' → '.join([legs[0]['from_location'],*[x['to_location'] for x in legs]])
    ids=', '.join(str(x['route_id']) for x in legs)
    vehicles=', '.join(str(v.get('label') or v['id']) for v in plan.get('vehicles',[])) or 'No assigned carrier'
    sla='Not evaluated: no deadline' if plan.get('sla_met') is None else 'Met' if plan['sla_met'] else 'Missed'
    return {
      'recommendation':f"Recommended plan: {plan['mode'].title()} · {result.get('planning_request',{}).get('objective','balanced')} objective.",
      'route':f'Route: {route}\nRoute IDs: {ids}',
      'vehicle':f'Vehicle: {vehicles}',
      'cost_eta':f"Cost & ETA: ₹{plan['operational_cost']:,.2f} · {plan['duration_hours']} hours · {plan['eta']}",
      'risk_reliability':f"Risk & Reliability: {plan['risk_score']:.2%} · {plan['reliability']:.2%}",
      'sla':f'SLA: {sla}',
      'reason':str(result.get('reason') or 'Highest-ranked feasible candidate under the requested constraints.'),
    }


async def compose(result,message,llm=None):
    facts=planning_facts(result)
    if not facts:
        return None
    order=list(facts)
    if llm is not None:
        try:
            response=await llm.ainvoke([
              SystemMessage(content='Arrange these approved fact keys for a concise logistics answer. Return ONLY JSON {"order":[keys]}. Include every key exactly once. Do not create text or calculate facts.'),
              HumanMessage(content=json.dumps({'question':message,'approved_facts':facts}))])
            proposed=json.loads(response.content).get('order')
            if isinstance(proposed,list) and len(proposed)==len(order) and set(proposed)==set(order):
                order=proposed
        except Exception:
            pass
    return '\n\n'.join(facts[key] for key in order)
