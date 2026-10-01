"""Read-only network/journey queries backed solely by loaded data and plan revisions."""
import re
from datetime import datetime
from backend.operations.journey_selection import current_journeys, lane_mentioned
from backend.planning.lifecycle import resolve
from backend.planning.service import PlanningService


def reply(text):
    return {'success':True,'response':text,'actions':[]}


def readonly(message):
    # A display/description clause following an imperative must not hide a mutation.
    if re.search(r'\b(?:plan|create|replan|apply|discard|delay|block|replace|change|optimize|optimise)\b',message,re.I) and not re.search(r'^\s*(?:what|which|how|show|explain|summari[sz]e|compare|tell|list)',message,re.I):
        return False
    return bool(re.search(r'^\s*(?:please\s+)?(?:what|which|how|show|explain|summari[sz]e|compare|tell|list|where|is|are|top|most|least|highest|lowest)\b',message,re.I))


def route_text(plan):
    return '\n'.join(f"- {l['from_location']} → {l['to_location']}; mode {l['route_type']}; Route ID: {l['route_id']}" for l in plan.get('route_legs',[]))


def warehouse_query(owner,message,network):
    text=message.casefold()
    rows=PlanningService().warehouse_capacity(owner)['warehouses']
    facts={w['warehouse_id']:w for w in network['warehouses']}
    rows=[{**r,**{k:facts[r['warehouse_id']].get(k) for k in ('city','is_active','latitude','longitude')}} for r in rows]
    if 'active' in text: rows=[r for r in rows if r['is_active']]
    named=[w for w in network['warehouses'] if any(re.search(r'(?<!\w)'+re.escape(str(w.get(k) or '').casefold())+r'(?!\w)',text) for k in ('city','name') if w.get(k))]
    if named: rows=[r for r in rows if r['warehouse_id'] in {w['warehouse_id'] for w in named}]
    elif re.search(r'\bwarehouses? in\s+',text): return reply('No warehouse matches that location in the loaded network.')
    count=len(rows)
    metric='utilization_percentage' if 'utiliz' in text else 'current_inventory' if 'most inventory' in text else 'available_storage'
    threshold=re.search(r'\b(?:over|above|greater than)\s+([\d,]+)',text)
    if threshold:rows=[r for r in rows if (r[metric] or 0)>float(threshold[1].replace(',',''))]
    ranked=sorted(rows,key=lambda r:(r[metric] is not None,r[metric] or 0))
    heading=f"{'Active ' if 'active' in text else ''}warehouses: {count}."
    if ranked and 'highest' in text and 'lowest' in text:
        rows=[ranked[-1],ranked[0]];heading+=' Highest then lowest available capacity:'
    elif re.search(r'\b(?:top|highest|most|lowest|least)\b',text):
        n=re.search(r'\btop\s+(\d+)',text)
        rows=(ranked if re.search(r'\b(?:lowest|least)\b',text) else ranked[::-1])[:int(n[1]) if n else 1]
        heading+=f' Ranked by {metric}.'
    location=bool(re.search(r'located|locations?|where',text)) and not re.search(r'capacity|inventory|storage|utiliz',text)
    lines=[heading]
    for r in rows:
        line=f"- {r['warehouse']} (ID {r['warehouse_id']}); city {r['city']}; status {'active' if r['is_active'] else 'inactive'}"
        if location:
            line+=f"; coordinates {r['latitude']}, {r['longitude']}"
        else:
            line+=f"; current inventory {r['current_inventory']}; available inventory {r['available_inventory']}; storage capacity {r['storage_capacity']}; available storage {r['available_storage']}; utilization {r['utilization_percentage']}% (loaded storage units)"
        lines.append(line)
    return reply('\n'.join(lines) if rows else 'No warehouses match those filters.')


def summary(owner,contexts):
    from backend.fedex.telemetry import runtime
    counts=dict(active=len(contexts),delayed=0,disrupted=0,sla_at_risk=0,paused=0,multimodal=0)
    lines=['Current active logical shipments (synthetic runtime):']
    for c in contexts:
        m=runtime.get(owner,c['movement_id']).snapshot();p=c['selected_plan'];changes=c.get('planning_changes') or {}
        disrupted=any(changes.get(k) for k in ('blocked_route_ids','blocked_routes','unavailable_vehicles','unavailable_warehouses'))
        sla=None
        if c.get('deadline'):sla=datetime.fromisoformat(m['current_eta']).timestamp()<=datetime.fromisoformat(c['deadline']).timestamp()
        for key,value in [('delayed',m['delay_minutes']>0),('disrupted',disrupted),('sla_at_risk',sla is False),('paused',m.get('paused')),('multimodal',p.get('mode')=='multimodal')]:counts[key]+=int(bool(value))
        lines.append(f"- {c.get('shipment_id')} / journey {c.get('journey_id')}: {c['source']} → {c['destination']}; {p['mode']}; vehicles {', '.join(str(v.get('label') or v['id']) for v in p['vehicles'])}; status {m['status']}; progress {m['progress']:.1%}; delay {m['delay_minutes']} min; ETA {m['current_eta']}; SLA {'not evaluated' if sla is None else 'met' if sla else 'at risk'}; risk {p['risk_score']:.2%}; paused {bool(m.get('paused'))}; disruptions {changes if disrupted else 'none recorded'}\n{route_text(p)}")
    lines.append('Overall: '+', '.join(f'{k.replace("_"," ")}={v}' for k,v in counts.items()))
    lines.append('Attention: review delayed, paused, disrupted or SLA-at-risk shipments listed above.' if any(counts[k] for k in ('delayed','disrupted','sla_at_risk','paused')) else 'No recorded operational issues requiring attention.')
    return reply('\n'.join(lines))


def answer(owner,message,context,selected_id=None):
    if not readonly(message):return None
    if re.search(r'\b(?:and|then|please)\s+(?:replan|delay|apply|change|replace)\b',message,re.I):return None
    from backend.operations.journey_display import display_intent
    if display_intent(message):return None
    text=message.casefold()
    if re.search(r'what[ -]if|scenario|hypothetical|simulate',text):return None
    explanation=re.fullmatch(r'\s*(?:what is|explain)\s+(?:the\s+)?(plan|schedule|live operations|network)[?.! ]*',text)
    if explanation:
        return reply({'plan':'Plan is the deterministic source, destination, route, mode, vehicles, cost, ETA, risk and SLA recommendation.',
                      'schedule':'Schedule shows time-bound assignments and departures from loaded schedules; these are templates unless an execution is explicitly started.',
                      'live operations':'Live Operations shows running journey status, progress, ETA and delays from the simulation runtime, not verified physical GPS telemetry.',
                      'network':'Network contains the loaded warehouses, vehicles and road/Air connectivity used by the deterministic planner.'}[explanation[1]])
    if re.search(r'summari[sz]e|operational summary',text) and re.search(r'shipments|operational|active',text):
        return summary(owner,current_journeys(context,owner,active_only=True))
    if 'warehouse' in text:
        return warehouse_query(owner,message,PlanningService().load_network(owner))
    if re.search(r'\bcompare\b',text) and re.search(r'\b(?:all|these|those)\s+(?:three|3|shipments)|shipments',text) and 'map' not in text:
        contexts=current_journeys(context,owner,active_only=True)
        ids=context.get('map_comparison_ids') or []
        named=[c for c in contexts if lane_mentioned(c,text)]
        contexts=named or ([c for c in contexts if c.get('movement_id') in ids] if ids else contexts)
        return reply('Existing shipment comparison (read only):\n'+'\n'.join(f"- {c.get('shipment_id')}: {c['source']} → {c['destination']}; cost {c.get('cost')}; ETA {c.get('duration_hours')} hours; risk {c.get('risk')}; reliability {c.get('reliability')}; utilization {(c.get('selected_plan') or {}).get('vehicle_utilization')}" for c in contexts))
    if re.search(r'\bcompare\b',text) and re.search(r'\b(?:road|ground)\b',text) and re.search(r'\bair\b',text):
        selected,error=resolve(context,message,selected_id)
        if error:return reply(error)
        from backend.planning.models import PlanningRequest
        from backend.agents.supervisor import _format_planning_result
        request=PlanningRequest(**selected['planning_request'])
        result=PlanningService().compare_modes(owner,request,changes=selected.get('planning_changes'))
        return reply(_format_planning_result(result,message))
    if re.search(r'\b(?:alternatives?|options)\b',text) and re.search(r'\b(?:show|list|compare)\b',text):
        selected,error=resolve(context,message,selected_id)
        if error:return reply(error)
        from backend.planning.models import PlanningRequest
        from backend.agents.supervisor import _format_planning_result, _objective_from_message
        request=PlanningRequest(**selected['planning_request'])
        objective=_objective_from_message(message)
        if objective:request=request.model_copy(update={'objective':objective})
        result=PlanningService().plan(owner,request,changes=selected.get('planning_changes'))
        return reply(_format_planning_result(result,message))
    route_id=re.search(r'\broute\s+(?:id\s*[:#]?\s*)?(\d+)\b',text)
    vehicle_id=re.search(r'\bvehicle\s+id\s*[:#]?\s*(\d+)\b',text)
    network=None
    # Labels are data, not a fixed AIR/TRK naming convention.
    if route_id or re.search(r'details|assigned to|vehicle|aircraft|truck|route.*id|id.*route|every leg',text):
        network=PlanningService().load_network(owner)
    if route_id:
        rows=[r for r in network['routes'] if str(r['route_id'])==route_id[1]]
        return reply('\n'.join(
            f"Route ID: {r['route_id']}; {r['from_location']} → {r['to_location']}; mode {r['route_type']}; distance {r['distance']} km; duration {r['duration']} hours; status {r.get('status','not supplied')}; loaded cost {r.get('cost')}; reliability {r.get('reliability')}; weather risk {r.get('weather_risk')}; operational risk {r.get('operational_risk')}"
            for r in rows) if rows else 'No such route ID in the loaded network.')
    labeled=[v for v in (network or {}).get('vehicles',[]) if v.get('label') and re.search(r'(?<![\w-])'+re.escape(v['label'].casefold())+r'(?![\w-])',text)]
    if vehicle_id or labeled:
        rows=labeled or [v for v in network['vehicles'] if str(v['id'])==vehicle_id[1]]
        lines=[]
        for v in rows:
            from backend.fedex.telemetry import runtime
            assigned=[entry.simulation.request.shipment_id for entry in runtime.entries.values()
                      if entry.owner==owner and not entry.simulation.stopped and entry.simulation.progress<1
                      and v['id'] in getattr(entry.simulation,'network_vehicle_ids',[])]
            lines.append(f"Vehicle ID: {v['id']}; label {v.get('label')}; type {v.get('type')}; capacity {v.get('capacity')} kg; location {v.get('current_location')}; status {v.get('status')}; available {v.get('is_available')}; compatible modes {v.get('compatible_modes')}; range {v.get('max_range_km')} km; speed {v.get('avg_speed_kmph')} km/h; reliability {v.get('reliability')}; active runtime shipments: {assigned or 'none recorded in runtime'}")
        return reply('\n'.join(lines) if rows else 'No such vehicle ID/label in the loaded network.')
    route_query=bool(re.search(r'route.*ids?|ids?.*route|every leg',text))
    vehicle_query=bool(re.search(r'vehicle|truck|aircraft',text))
    status_query=bool(re.search(r'(?:current|same|this|selected).*shipment|shipment.*status|current route',text))
    if route_query or vehicle_query or status_query:
        selected,error=resolve(context,message,selected_id)
        if error:return reply(error)
        p=selected.get('selected_plan') or {}
        if route_query:
            if re.search(r'\bair leg\b',text):p={**p,'route_legs':[l for l in p.get('route_legs',[]) if l['route_type']=='air']}
            return reply(route_text(p) or 'No matching leg in the current plan.')
        if vehicle_query:
            from backend.agents.supervisor import _vehicle_text
            vehicles=p.get('vehicles',[])
            if re.search(r'\baircraft\b',text) and not re.search(r'truck|vehicles?',text):
                vehicles=[v for v in vehicles if str(v.get('type','')).casefold() in {'aircraft','plane'}]
            if re.search(r'\btrucks?\b',text) and not re.search(r'aircraft|vehicles?',text):
                vehicles=[v for v in vehicles if str(v.get('type','')).casefold()=='truck']
            facts={v['id']:v for v in network['vehicles']}
            extra=[]
            for v in vehicles:
                fact=facts.get(v['id'],{})
                extra.append(f"{v.get('label') or v['id']}: availability {fact.get('is_available')}; compatible modes {fact.get('compatible_modes')}; range {fact.get('max_range_km')} km; speed {fact.get('avg_speed_kmph')} km/h; reliability {fact.get('reliability')}; shipment {selected.get('shipment_id')}")
            return reply(_vehicle_text({**p,'vehicles':vehicles},selected.get('planning_request',{}).get('shipment',{}))+'\n'+'\n'.join(extra))
        from backend.fedex.telemetry import runtime
        try:m=runtime.get(owner,selected['movement_id']).snapshot()
        except KeyError:return reply('The selected journey has no available runtime movement.')
        return reply(f"Shipment {m['shipment_id']}; {selected['source']} → {selected['destination']}; status {m['status']}; progress {m['progress']:.1%}; delay {m['delay_minutes']} min; ETA {m['current_eta']}\n{route_text(p)}")
    return None
