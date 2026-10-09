"""Schedule-aware adapter around the existing deterministic cost/risk ranker."""
from datetime import datetime, timedelta, timezone
from backend.fedex.models import Schedule, EligibilityInput
from backend.fedex.eligibility import candidate, IST


def calculate(service, legs, request, vehicles, changes=None, warehouses=None, start_at=None):
    changes=changes or {}
    ready=start_at or getattr(request,'shipment_ready_datetime',None) or datetime.now(IST)
    if ready.tzinfo is None: ready=ready.replace(tzinfo=IST)
    ready=ready.astimezone(IST)
    initial=ready
    parts=[]
    for leg in legs:
        if 'schedule' not in leg:
            raise ValueError('Planning requires a client workbook service')
        schedule=Schedule(**leg['schedule'])
        dates=None
        # Daily recurrence is an explicit simulation assumption, never an added run.
        for offset in range(3):
            date=ready.date()+timedelta(days=offset)
            trial=candidate(schedule,EligibilityInput(origin_station=schedule.origin_station,
                gateway=schedule.gateway,simulation_date=date,shipment_ready_datetime=ready))
            if trial['eligible']:
                dates=trial
                break
        if dates is None: return None
        bound=[dict(v,capacity=v.get('available_capacity_kg',v['capacity'])) for v in vehicles
               if v.get('service_id')==schedule.schedule_id]
        local=request.model_copy(update={'source':schedule.origin_station,'destination':schedule.gateway})
        part=service._legacy_candidate([leg],local,bound,changes,warehouses,start_at=dates['etd'])
        if part is None:return None
        delay=float(changes.get('delay_minutes',0))+float(changes.get('service_delays',{}).get(schedule.schedule_id,0))
        arrival=(dates['retrieval'] or dates['eta'])+timedelta(minutes=delay)
        part.update(eta=arrival.astimezone(timezone.utc).isoformat(),
            duration_hours=round((arrival-ready).total_seconds()/3600,2),
            departure_wait_hours=round((dates['etd']-ready).total_seconds()/3600,2),
            scheduled_etd=dates['etd'].isoformat(),scheduled_eta=dates['eta'].isoformat(),
            service_id=schedule.schedule_id,client_service=schedule.service,
            source_schedule=schedule.model_dump(mode='json'),
            warnings=['Daily schedule recurrence and resource capacity are simulation assumptions; operating days are not supplied.'],
            provenance={'source_schedule':'CLIENT_SOURCE','vehicles':'SYNTHETIC_ENRICHMENT',
                'operational_cost':'CALCULATED','eta':'SCENARIO' if delay else 'CALCULATED',
                'delay_minutes':'SCENARIO','vehicle_utilization':'CALCULATED'})
        for v in part['vehicles']:
            original=next(x for x in vehicles if x['id']==v['id'])
            v.update(service_id=schedule.schedule_id,capacity=original['capacity'],
                available_capacity_kg=original['available_capacity_kg'],data_source='SYNTHETIC_ENRICHMENT',
                utilization_percentage=round(v['assigned_load_kg']/original['capacity']*100,2),
                projected_utilization_percentage=round((original['assigned_load_kg']+v['assigned_load_kg'])/original['capacity']*100,2))
        part['vehicle_utilization']=round(request.shipment.weight_kg/sum(v['capacity'] for v in part['vehicles']),4)
        part['utilization_basis']='Planned shipment load / nominal generated capacity; baseline assigned load is reserved before feasibility selection.'
        parts.append(part)
        ready=arrival
    if not parts:return None
    result=parts[0]
    if len(parts)>1:
        result=dict(result,route_legs=legs,vehicles=[v for p in parts for v in p['vehicles']],
            leg_assignments=[dict(route_legs=p['route_legs'],vehicles=p['vehicles'],duration_hours=p['duration_hours'],
                vehicle_utilization=p['vehicle_utilization'],departure_wait_hours=p['departure_wait_hours']) for p in parts],
            mode=parts[0]['mode'] if len({p['mode'] for p in parts})==1 else 'multimodal',
            operational_cost=round(sum(p['operational_cost'] for p in parts),2),
            cost_breakdown={k:round(sum(p['cost_breakdown'][k] for p in parts),2) for k in parts[0]['cost_breakdown']},
            eta=parts[-1]['eta'],duration_hours=round((ready-initial).total_seconds()/3600,2),
            departure_wait_hours=sum(p['departure_wait_hours'] for p in parts),
            vehicle_utilization=sum(p['vehicle_utilization'] for p in parts)/len(parts),
            reliability=min(p['reliability'] for p in parts),risk_score=max(p['risk_score'] for p in parts))
    slack=(request.deadline-ready).total_seconds()/3600 if request.deadline else None
    result.update(sla_met=None if slack is None else slack>=0, sla_slack_hours=max(0,slack) if slack is not None else None,
        sla_delay_hours=max(0,-slack) if slack is not None else None)
    simulated_deadline=initial+timedelta(hours=sum(l['sla_hours'] for l in legs))
    result['simulated_sla_deadline']=simulated_deadline.isoformat()
    result['simulated_sla_met']=ready<=simulated_deadline
    result['provenance']['simulated_sla_deadline']='SYNTHETIC_ENRICHMENT'
    result['provenance']['simulated_sla_met']='CALCULATED'
    result['selling_price']=result['expected_revenue']=round(result['operational_cost']/(1-request.target_margin),2)
    result['profit']=round(result['selling_price']-result['operational_cost'],2)
    return result
