"""Read-only follow-ups over the saved deterministic candidate set."""
import re
from backend.planning.lifecycle import resolve


def facts(plan):
    from backend.agents.supervisor import _mode_label
    def percentage(value):
        return f'{value:.2%}' if isinstance(value,(int,float)) else 'Not supplied'
    return (f"{_mode_label(plan)} · Plan {plan.get('plan_id')} · cost ₹{plan.get('operational_cost')} · "
            f"ETA {plan.get('duration_hours')} h · risk {percentage(plan.get('risk_score'))} · "
            f"reliability {percentage(plan.get('reliability'))} · utilization {percentage(plan.get('vehicle_utilization'))} · "
            f"Route IDs {[leg.get('route_id') for leg in plan.get('route_legs', [])]} · "
            f"vehicles {', '.join(str(v.get('label') or v.get('id')) for v in plan.get('vehicles', []))}")



def answer(owner, message, context, selected_id=None):
    text=message.casefold()
    why=bool(re.search(r'why.*(?:choose|chose|chosen|recommend|option)|explain.*(?:choice|recommendation)',text))
    second=bool(re.search(r'show\s+(?:only\s+)?(?:the\s+)?second\s+option',text))
    all_options=bool(re.search(r'show\s+all\s+(?:the\s+)?options\s+again',text))
    ground=bool(re.search(r'compare\s+(?:it|this|that|the current option)\s+with\s+ground',text))
    if not any((why,second,all_options,ground)):return None
    selected,error=resolve(context,message,selected_id)
    def reply(value):return {'success':True,'response':value,'actions':[]}
    if error:return reply(error)
    plan=selected.get('selected_plan') or {}
    candidates=selected.get('candidate_plans') or [plan]
    if second:
        return reply('Candidate #2: '+facts(candidates[1]) if len(candidates)>1 else 'There is no second candidate in the saved candidate set.')
    if all_options:
        return reply('Saved options for the current shipment:\n'+'\n'.join(f'{i}. {facts(p)}' for i,p in enumerate(candidates,1)))
    others=[p for p in candidates if p.get('plan_id')!=plan.get('plan_id')]
    from backend.agents.supervisor import _actual_mode
    if ground:
        already=_actual_mode(plan)=='road'
        alternatives=[p for p in others if _actual_mode(p)=='road']
        if already:alternatives=alternatives or others
        return reply(('The current recommended option is already Ground.\n' if already else '')+facts(plan)+'\n'+('Feasible alternative: '+facts(alternatives[0]) if alternatives else 'No other matching feasible alternative exists in the saved candidate set.'))
    objective=selected.get('planning_request',{}).get('objective','balanced')
    reason={'balanced':'best calculated balance of cost, ETA, risk, reliability and utilization', 'cheapest':'lowest calculated cost', 'fastest':'shortest calculated ETA','lowest-risk':'lowest calculated risk'}.get(objective,objective)
    return reply(f'Chosen for the {reason} among feasible candidates.\n'+facts(plan)+'\n'+('\n'.join('Alternative: '+facts(p) for p in others[:2]) if others else 'No other feasible candidate was returned.'))
