"""Intent-specific answers over the existing network/planner, with explicit entity priority."""
from copy import deepcopy
from datetime import datetime, timedelta
import re
import json
from zoneinfo import ZoneInfo
from backend.client_network import network,summary
from backend.location_labels import labels,resolve_pair,matching_codes
from backend.chat_normalization import classify
from backend.fedex.models import Schedule,EligibilityInput
from backend.fedex.eligibility import candidate
from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService

IST=ZoneInfo('Asia/Kolkata')
contexts={}


def local_time(value):
    if value is None:return 'Not supplied'
    value=datetime.fromisoformat(value) if isinstance(value,str) else value
    if value.tzinfo is None:value=value.replace(tzinfo=IST)
    return value.astimezone(IST).strftime('%d %b %Y, %H:%M IST')


def _compact(value):return re.sub(r'[^a-z0-9]','',value.casefold())
def _mentioned(value,message):
    if not value or len(value)<3:return False
    expression=re.escape(value).replace(r'\ ',r'\s*')
    return bool(re.search(r'(?<![A-Za-z0-9])'+expression+r'(?![A-Za-z0-9])',message,re.I))


def _reply(text,intent,**extra):
    return dict(success=True,response=text,intent=intent,actions=extra.pop('actions',[]),**extra)


def _date(req,ctx):
    if ctx.get('request') and ctx['request'].shipment_ready_datetime:return ctx['request'].shipment_ready_datetime.astimezone(IST).date()
    return datetime.fromisoformat(req.operational_service_date).date() if req.operational_service_date else datetime.now(IST).date()


def _dates(row,req,ctx):
    day=_date(req,ctx)
    return candidate(Schedule(**row['schedule']),EligibilityInput(origin_station=row['from_location'],gateway=row['to_location'],
        simulation_date=day,shipment_ready_datetime=datetime.combine(day,datetime.min.time(),IST)))


def _service_text(row,req,ctx,mapping):
    s=row['schedule'];d=_dates(row,req,ctx)
    mode={'AIR':'Air','SURFACE':'Surface','RAIL':'Train'}[s['mode']]
    next_day=' (next day)' if d['eta'] and d['etd'] and d['eta'].date()>d['etd'].date() else ''
    return f"{mode} — {s['service'] or 'Service detail not supplied'}, Run {s['run']}\n{s['lane']} · {mapping[s['origin_station']]['label']} → {mapping[s['gateway']]['label']}\nHandover: {local_time(d['cutoff'])}\nETD: {local_time(d['etd'])} · ETA: {local_time(d['eta'])}{next_day}"


def plan_reply(result,prefix=''):
    plans=result.get('candidate_plans',[]);weight=result.get('planning_request',{}).get('shipment',{}).get('weight_kg')
    lines=[]
    for index,p in enumerate(plans[:3]):
        service=' + '.join(f"{l['schedule']['service']} / {l['schedule']['run']}" for l in p['route_legs'])
        mode={'road':'Surface','air':'Air','rail':'Train','multimodal':'Multimodal'}.get(p['mode'],p['mode'])
        lines.append(f"Plan {chr(65+index)} — {mode}: {service}\nEstimated cost: ₹{p['operational_cost']:,.2f} · Shipment ETA: {local_time(p['eta'])}\nAssigned resource: {', '.join(v['label'] for v in p['vehicles'])}")
    if not lines:lines=[result.get('reason','No feasible supplied service meets these constraints.')]
    lead=f"For {weight:,.0f} kg:\n" if weight else ''
    return _reply(prefix+lead+'\n\n'.join(lines)+'\n\nCapacity, load, cost and risk are simulated operational attributes.',
        'PLAN_SHIPMENT',actions=[dict(type='unified_supply_chain_plan',data=result)],planning_result=result)


def _scope(message,normalized,ctx,model,req):
    rows=model['routes'];mapping=labels(model['schedules'])
    # Raw, explicit IDs always outrank model normalization and all stored state.
    resources=[v for v in model['vehicles'] if _mentioned(v['id'],message)]
    shipments=[s for s in model['shipments'] if _mentioned(s['shipment_id'],message) or _mentioned(s['con_id'],message)]
    identifiers={v['service_id'] for v in resources}|{s['service_id'] for s in shipments}
    if not identifiers:
        flights=[r for r in rows if r['schedule']['mode']=='AIR' and _mentioned(r['schedule']['service'],message)]
        identifiers={r['route_id'] for r in flights}
    if not identifiers:
        identifiers={r['route_id'] for r in rows if _mentioned(r['route_id'],message) or _mentioned(r['schedule']['lane'],message)}
    if normalized.identifier and _mentioned(normalized.identifier,message) and not identifiers:
        identifiers={r['route_id'] for r in rows if normalized.identifier.casefold() in {r['route_id'].casefold(),r['schedule']['service'].casefold(),r['schedule']['lane'].casefold()}}
    # Unknown explicit identifiers must not inherit a stale conversational/UI entity.
    flight=re.search(r'(?<![A-Za-z0-9])(?:6E|AI|UK|SG|IX|I5)\s*\d{2,5}(?![A-Za-z0-9])',message,re.I)
    resource=re.search(r'\b(?:SUR|AIR|RAIL)-[A-Za-z0-9-]+',message,re.I)
    if flight and not any(_compact(flight[0])==_compact(r['schedule']['service']) for r in rows if r['schedule']['mode']=='AIR'):
        return [],'That flight number is not present in the supplied network.',True
    if resource and not any(resource[0].casefold()==v['id'].casefold() for v in model['vehicles']):
        return [],'That resource ID is not present in the simulation enrichment.',True
    explicit=bool(identifiers)
    pair=None
    if identifiers:
        scope=[r for r in rows if r['route_id'] in identifiers]
        # Repeated service identifiers must be disambiguated by an explicit pair.
        if normalized.origin and normalized.destination:
            pair=resolve_pair(normalized.origin,normalized.destination,model)
            filtered=[r for r in scope if pair and (r['from_location'],r['to_location'])==pair]
            if filtered:scope=filtered
        pairs={(r['from_location'],r['to_location']) for r in scope}
        if len(pairs)>1:return [],'That identifier belongs to multiple services. Specify a station/gateway pair or run.',True
        pair=next(iter(pairs)) if pairs else None
    elif normalized.origin and normalized.destination:
        explicit=True;pair=resolve_pair(normalized.origin,normalized.destination,model)
        if pair is None:return [],'The location pair is unknown or ambiguous. Choose its station/gateway codes from Network.',True
        scope=[r for r in rows if (r['from_location'],r['to_location'])==pair]
    else:
        # Canonical codes mentioned without "from/to" (including Hindi/Hinglish).
        mentioned=sorted([c for c in mapping if _mentioned(c,message)],key=lambda c:message.casefold().find(c.casefold()))
        if len(mentioned)>=2:
            pair=resolve_pair(mentioned[0],mentioned[1],model);explicit=True
        elif len(mentioned)==1:
            scope=[r for r in rows if mentioned[0] in (r['from_location'],r['to_location'])];explicit=True
            pairs={(r['from_location'],r['to_location']) for r in scope}
            pair=next(iter(pairs)) if len(pairs)==1 else None
        if pair:scope=[r for r in rows if (r['from_location'],r['to_location'])==pair]
        elif len(mentioned)!=1:
            if ctx.get('origin') and ctx.get('destination'):
                pair=(ctx['origin'],ctx['destination']);scope=[r for r in rows if (r['from_location'],r['to_location'])==pair]
            elif normalized.intent in {'NETWORK_LOOKUP','SERVICE_SEARCH'}:scope=rows
            elif req.selected_operational_run_id:
                from backend.control_tower.service import ControlTower
                from backend.control_tower.routes import current_source_run
                try:ui=ControlTower().detail(req_owner(ctx),req.selected_operational_run_id)
                except KeyError:return [],'The selected run is unavailable. Specify a service or station pair.',False
                if not current_source_run(ui):return [],'The selected archived run is outside the current network.',False
                scope=[r for r in rows if r['route_id']==ui['schedule_id']]
                if scope:pair=(scope[0]['from_location'],scope[0]['to_location'])
            else:return [],'Specify a service, flight, resource ID or station/gateway pair.',False
    if pair:
        if pair!=(ctx.get('origin'),ctx.get('destination')):
            ctx.update(request=None,result=None,changes={},resource_id=None,selected_service_id=None)
        ctx.update(origin=pair[0],destination=pair[1])
    if normalized.mode:scope=[r for r in scope if r['schedule']['mode']==normalized.mode]
    run=re.search(r'\brun\s+(\d+|primary\s*\d+)',message,re.I)
    if run:scope=[r for r in scope if _compact(r['schedule']['run'])==_compact(run[1])]
    broad=normalized.intent in {'COMPARE_SERVICES','COST_COMPARISON','RISK_COMPARISON','PLAN_SHIPMENT','CHANGE_SHIPMENT_WEIGHT','RECOVERY'} or re.search(r'carry|feasib|calculation|utilization|available option',message,re.I)
    if not explicit and not normalized.mode and not broad:
        if ctx.get('resource_id') and normalized.intent=='CAPACITY_LOOKUP':
            resource=next((v for v in model['vehicles'] if v['id']==ctx['resource_id']),None)
            if resource:scope=[r for r in scope if r['route_id']==resource['service_id']]
        elif ctx.get('selected_service_id'):scope=[r for r in scope if r['route_id']==ctx['selected_service_id']]
    if resources:ctx['resource_id']=resources[0]['id']
    elif len(scope)==1 and (explicit or normalized.mode):ctx['resource_id']=None
    if len(scope)==1:ctx['selected_service_id']=scope[0]['route_id']
    if not scope:return [],'No matching supplied service is available for that identifier, pair or mode.',explicit
    return scope,None,explicit


def req_owner(ctx):return ctx['owner']


def _planning(owner,ctx,model,objective=None):
    request=ctx.get('request')
    if request is None:return None
    if objective:request=request.model_copy(update={'objective':objective});ctx['request']=request
    result=PlanningService().plan(owner,request,changes=ctx.get('changes',{}))
    ctx['result']=result
    return result


def _resource_reply(scope,ctx,model,intent,message):
    ids={r['route_id'] for r in scope};vehicles=[v for v in model['vehicles'] if v['service_id'] in ids]
    if ctx.get('resource_id') and intent=='CAPACITY_LOOKUP' and not re.search(r'calculation|carry|feasib|utilization',message,re.I):
        vehicles=[v for v in vehicles if v['id']==ctx['resource_id']]
    weight=ctx['request'].shipment.weight_kg if ctx.get('request') else None
    unavailable=set(ctx.get('changes',{}).get('unavailable_vehicles',[]))
    lines=[];facts=[]
    for row in scope:
        bound=[v for v in vehicles if v['service_id']==row['route_id']]
        free=sum(v['available_capacity_kg'] for v in bound if v['is_available'] and v['id'] not in unavailable)
        nominal=sum(v['capacity'] for v in bound)
        feasible=None if weight is None else free>=weight and row['status']=='active'
        for v in bound:
            available=bool(v['is_available'] and v['id'] not in unavailable)
            lines.append(f"{v['label']} — simulation resource for {row['schedule']['service']}\nCapacity: {v['capacity']:,.0f} kg · Baseline assigned load: {v['assigned_load_kg']:,.2f} kg\nAvailable capacity: {v['available_capacity_kg']:,.2f} kg{' (unavailable in this scenario)' if not available else ''}")
            if re.search(r'calculation|utilization',message,re.I):
                lines.append(f"Baseline utilization = {v['assigned_load_kg']:,.2f} ÷ {v['capacity']:,.0f} × 100 = {v['utilization_percentage']:.2f}%.")
                if weight:
                    lines.append(f"Requested load / nominal capacity = {weight:,.0f} ÷ {v['capacity']:,.0f} × 100 = {weight/v['capacity']*100:.2f}%. Available capacity = {v['capacity']:,.0f} − {v['assigned_load_kg']:,.2f} = {v['available_capacity_kg']:,.2f} kg.")
        if weight:
            reason='insufficient capacity' if weight>nominal or free<weight else 'source schedule requires validation'
            lines.append(f"{row['schedule']['service']}: {'FEASIBLE' if feasible else 'NOT FEASIBLE — '+reason} for {weight:,.0f} kg; usable capacity {free:,.2f} kg.")
        facts.append(dict(service_id=row['route_id'],resources=bound,available_capacity_kg=free,required_weight_kg=weight,feasible=feasible))
    if len(vehicles)==1:ctx['resource_id']=vehicles[0]['id'];ctx['selected_service_id']=vehicles[0]['service_id']
    return _reply('\n\n'.join(lines) if lines else 'No simulation resource/capacity is present for this service.',intent,capacity_results=facts)


def answer(owner,req,normalized=None):
    normalized=normalized or classify(req.message);intent=normalized.intent
    model=network();key=(owner,req.session_id or 'default')
    ctx=contexts.setdefault(key,dict(owner=owner,version=model['network_version'],changes={}))
    if ctx.get('version')!=model['network_version']:
        ctx.clear();ctx.update(owner=owner,version=model['network_version'],changes={})
    if len(contexts)>1000:contexts.pop(next(iter(contexts)))
    # General operational lists have no entity to inherit; validate imported topology first.
    if not normalized.origin and not normalized.identifier and re.search(r'\b(?:show all|operational runs|network status|critical lanes|movements)\b',req.message,re.I):
        from backend.control_tower.service import ControlTower
        from backend.control_tower.routes import current_source_run
        rows=ControlTower().runs(owner,_date(req,ctx))
        current=[r for r in rows if current_source_run(r)]
        if rows and not current:return _reply('Reimport the supplied schedule workbook in Live Operations; archived runs are outside the current network.',intent)
        if not current:return _reply('No operational runs are loaded for this date. Import the schedule workbook in Live Operations.',intent)
        if normalized.mode:current=[r for r in current if r['schedule']['mode']==normalized.mode]
        return _reply(f"{len(current)} operational runs match: "+', '.join(f"{r['schedule']['service']} / {r['schedule']['lane']} / {r['status']}" for r in current),intent,operational_runs=current)
    scope,error,explicit=_scope(req.message,normalized,ctx,model,req)
    if error:return _reply(error,intent)
    mapping=labels(model['schedules']);text=req.message.casefold()
    missing=re.search(r'driver|registration|actual gps|exact gps|maintenance|photo|चालक',text)
    if missing:return _reply(f"{missing[0].capitalize()} information is not supplied in the schedule or simulation data.",intent)
    if re.search(r'\b(?:status|position|location|progress|elapsed|remaining|critical|events|why.*delay)\b',text) and intent not in {'PLAN_SHIPMENT','CHANGE_SHIPMENT_WEIGHT','BREAKDOWN_SCENARIO','BLOCK_SERVICE','CAPACITY_LOOKUP'} and not normalized.delay_minutes:
        from backend.control_tower.service import ControlTower
        from backend.control_tower.routes import current_source_run
        tower=ControlTower();wanted={r['route_id'] for r in scope}
        runs=[r for r in tower.runs(owner,_date(req,ctx)) if current_source_run(r) and r['schedule_id'] in wanted]
        if not runs:return _reply('No operational run/event data is loaded for this service date. Its source schedule is available in Schedules.',intent)
        lines=[]
        for run in runs:
            detail=tower.detail(owner,run['run_id']);movement=detail.get('movement')
            line=f"{detail['schedule']['service']} / Run {detail['schedule']['run']}: {detail['status']}\nCurrent ETA: {local_time(detail['current_eta'])} · Critical: {'Yes' if detail['critical'] else 'No'}"
            if movement:line+=f"\nSimulated progress: {movement['progress']:.1%} · Clock: {local_time(movement['simulation_timestamp'])} · Elapsed: {(detail['elapsed_hours'] or 0)*60:.1f} min · Remaining: {(detail['estimated_time_left_hours'] or 0)*60:.1f} min"
            if re.search(r'position|location',text):
                point=detail.get('latest_location') or (detail.get('visualization') or {}).get('position')
                line+=f"\nLocation: {point or 'Not supplied'} · {detail.get('location_source') or 'Schedule-derived city-centre estimate; not GPS'}"
            if re.search(r'events|why.*delay',text):
                reasons=[]
                for event in detail.get('events',[]):
                    payload=json.loads(event.get('payload_json') or '{}')
                    if payload.get('reason'):reasons.append(payload['reason'])
                line+='\nAssociated event reasons: '+('; '.join(reasons) if reasons else 'No event reason is supplied.')
            lines.append(line)
        return _reply('\n\n'.join(lines),intent,operational_runs=runs)
    if intent=='NETWORK_LOOKUP':
        stats=summary(model)
        return _reply(f"{stats['client_services']} services connect {stats['client_nodes']} stations/gateways: {stats['air_runs']} Air, {stats['surface_runs']} Surface and {stats['train_runs']} Train. {stats['generated_resources']} simulation resources and {stats['simulated_shipments']} simulated shipments are attached to these services.",intent)
    if intent in {'PLAN_SHIPMENT','CHANGE_SHIPMENT_WEIGHT'}:
        weight=normalized.weight_kg or (ctx['request'].shipment.weight_kg if ctx.get('request') else None)
        if not weight:return _reply('What is the shipment weight in kg? It is needed only to check planning capacity.',intent)
        if not ctx.get('origin') or not ctx.get('destination'):return _reply('Specify the shipment origin and destination codes or verified names.',intent)
        if ctx.get('request'):
            request=ctx['request'].model_copy(update={'shipment':ctx['request'].shipment.model_copy(update={'weight_kg':weight})})
        else:
            request=PlanningRequest(source=ctx['origin'],destination=ctx['destination'],shipment={'weight_kg':weight},shipment_ready_datetime=datetime.now(IST))
        ctx['request']=request
        result=_planning(owner,ctx,model)
        reply=plan_reply(result,'Shipment weight updated.\n' if intent=='CHANGE_SHIPMENT_WEIGHT' else '')
        reply['intent']=intent
        if weight>0:
            infeasible=[r for r in model['routes'] if (r['from_location'],r['to_location'])==(ctx['origin'],ctx['destination']) and r['route_id'] not in {l['route_id'] for p in result['candidate_plans'] for l in p['route_legs']}]
            if infeasible:reply['response']+='\nNOT FEASIBLE: '+', '.join(r['schedule']['service'] for r in infeasible)+' — insufficient available capacity or scenario constraints.'
        return reply
    if intent in {'BREAKDOWN_SCENARIO','RECOVERY'}:
        target=scope[0] if len(scope)==1 else next((r for r in scope if r['schedule']['mode']=='SURFACE'),None)
        if target is None:return _reply('Specify which supplied service/resource needs a replacement.',intent)
        resources=[v for v in model['vehicles'] if v['service_id']==target['route_id']]
        broken=next((v for v in resources if v['id']==ctx.get('resource_id')),resources[0] if resources else None)
        if broken is None:return _reply('No assigned simulation resource exists for this service.',intent)
        changes=ctx.setdefault('changes',{});changes.setdefault('unavailable_vehicles',[])
        if broken['label'] not in changes['unavailable_vehicles']:changes['unavailable_vehicles'].append(broken['label'])
        spares=[v for v in resources if v['is_available'] and v['id'] not in changes['unavailable_vehicles']]
        weight=ctx['request'].shipment.weight_kg if ctx.get('request') else None
        feasible_spares=spares if weight is None else []
        if weight is not None:
            calculated=_planning(owner,ctx,model)
            same_service=next((p for p in calculated['candidate_plans'] if len(p['route_legs'])==1 and p['route_legs'][0]['route_id']==target['route_id']),None)
            if same_service:
                used={v['label'] for v in same_service['vehicles']}
                feasible_spares=[v for v in spares if v['label'] in used]

        recovery=dict(service_id=target['route_id'],unavailable_resource=broken['label'],replacement_vehicles=feasible_spares,scenario=True)
        if feasible_spares:
            response='Same-service replacement: '+', '.join(v['label'] for v in feasible_spares)+'. These are available simulation resources.'
        else:response='No same-service spare vehicle is available.' if not spares else 'No same-service spare has sufficient available capacity.'
        if ctx.get('request'):
            result=_planning(owner,ctx,model);recovery['alternative_plan']=result.get('recommended_plan')
            if result.get('recommended_plan'):
                response+='\n\n'+plan_reply(result,'Legitimate network alternative:\n')['response']
                actions=[dict(type='unified_supply_chain_plan',data=result)]
            else:response+='\nNo supplied alternative meets the current shipment constraints.';actions=[]
        else:
            alternatives=[r for r in model['routes'] if r['route_id']!=target['route_id'] and (r['from_location'],r['to_location'])==(target['from_location'],target['to_location'])]
            response+='\nOther supplied services: '+(', '.join(r['schedule']['service'] for r in alternatives) or 'none')+'. Shipment weight is needed to confirm recovery capacity.';actions=[]
        return _reply(response,intent,recovery=recovery,actions=actions)
    if intent=='DELAY_SCENARIO':
        if len(scope)!=1:return _reply('Specify one supplied service/run to delay.',intent)
        minutes=normalized.delay_minutes
        if minutes is None:return _reply('Specify the delay in minutes.',intent)
        row=scope[0];d=_dates(row,req,ctx)
        if d['eta'] is None:return _reply('The source ETA is unavailable; a revised ETA cannot be calculated.',intent)
        ctx.setdefault('changes',{}).setdefault('service_delays',{})[row['route_id']]=minutes
        revised=d['eta']+timedelta(minutes=minutes)
        result=_planning(owner,ctx,model)
        return _reply(f"{row['schedule']['service']} / {row['schedule']['run']}\nBaseline ETA: {local_time(d['eta'])}\nScenario ETA: {local_time(revised)}\nDifference: +{minutes:g} min. Source ETD/ETA remain unchanged.",intent,
            scenario={'service_id':row['route_id'],'baseline_eta':d['eta'].isoformat(),'scenario_eta':revised.isoformat(),'delay_minutes':minutes,'provenance':'SCENARIO'},planning_result=result)
    if intent=='BLOCK_SERVICE':
        if len(scope)!=1:return _reply('Specify the supplied flight, lane, run or resource to make unavailable.',intent)
        ctx.setdefault('changes',{}).setdefault('blocked_route_ids',[]).append(scope[0]['route_id'])
        result=_planning(owner,ctx,model)
        return plan_reply(result,'Service unavailable in this scenario.\n') if result else _reply('The supplied service is unavailable in this scenario. Provide shipment weight only if you need capacity-feasible recovery.',intent)
    if intent=='COST_COMPARISON':
        if 'fuel' in text:
            percentage=re.search(r'(\d+(?:\.\d+)?)\s*%',text)
            if not percentage:return _reply('Specify the fuel increase percentage.',intent)
            ctx.setdefault('changes',{})['fuel_cost_multiplier']=1+float(percentage[1])/100
        result=_planning(owner,ctx,model,'cheapest')
        if result:return plan_reply(result,'Cheapest capacity-feasible option using the active shipment weight:\n')
        ranked=sorted(scope,key=lambda r:r['base_transport_cost']+r['fuel_cost'])
        return _reply('Service-level simulated cost profiles (shipment-specific allocation excluded):\n'+'\n'.join(f"{r['schedule']['service']}: ₹{r['base_transport_cost']+r['fuel_cost']:,.2f}" for r in ranked),intent)
    if intent=='RISK_COMPARISON':
        result=_planning(owner,ctx,model,'lowest-risk')
        if result:return plan_reply(result,'Lowest simulated risk among capacity-feasible options:\n')
        return _reply('\n'.join(f"{r['schedule']['service']}: simulated risk input {r['operational_risk']:.1%}, reliability {r['reliability']:.1%}" for r in sorted(scope,key=lambda r:r['operational_risk'])),intent)
    if intent in {'RESOURCE_LOOKUP','CAPACITY_LOOKUP'}:
        return _resource_reply(scope,ctx,model,intent,req.message)
    if intent=='VOLUME_LOOKUP':
        ids={r['route_id'] for r in scope}
        if 'affected' in text:ids=set(ctx.get('changes',{}).get('service_delays',{}))|set(ctx.get('changes',{}).get('blocked_route_ids',[])) or ids
        shipments=[s for s in model['shipments'] if s['service_id'] in ids]
        return _reply(f"{len(shipments)} simulated shipments, totalling {sum(s['weight_kg'] for s in shipments):,.2f} kg, are attached to these supplied services.",intent,simulated_shipments=shipments)
    if intent=='COMPARE_SERVICES':
        ranked=sorted(scope,key=lambda r:_dates(r,req,ctx)['eta'] or datetime.max.replace(tzinfo=IST))
        first=ranked[0];d=_dates(first,req,ctx)
        return _reply(f"{first['schedule']['service']} ({first['schedule']['source_mode']}) arrives first at {local_time(d['eta'])}.\n\n"+'\n\n'.join(_service_text(r,req,ctx,mapping) for r in ranked),intent,services=[r['schedule'] for r in ranked])
    if intent=='FOLLOW_UP_REFERENCE' and ctx.get('result'):
        if 'why' in text:return plan_reply(ctx['result'],ctx['result'].get('reason','')+'\n')
        if 'sla' in text:
            plan=ctx['result'].get('recommended_plan')
            return _reply(f"Simulated SLA {'met' if plan and plan.get('simulated_sla_met') else 'missed'}; deadline {local_time(plan.get('simulated_sla_deadline')) if plan else 'unavailable'}.",intent)
    if len(scope)>6:
        return _reply(f"{len(scope)} supplied services are available. Specify an origin and destination name/code to list the relevant schedules; no shipment weight is needed for service lookup.",intent,services=[r['schedule'] for r in scope])
    heading='Supplied services:\n' if normalized.language=='en' else 'उपलब्ध सेवाएँ:\n' if normalized.language=='hi' else 'Available services yeh hain:\n'
    return _reply(heading+'\n\n'.join(_service_text(r,req,ctx,mapping) for r in scope),intent,services=[r['schedule'] for r in scope])
