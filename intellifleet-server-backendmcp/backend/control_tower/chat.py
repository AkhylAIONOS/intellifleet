"""Deterministic operational answers, independent of planner context."""
import re
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .service import ControlTower
from .search import location_matches


def reply(text, actions=None):
    return {'success': True, 'response': text, 'actions': actions or []}


def run_text(run):
    s=run['schedule']
    return (f"{s['lane']} · Run {s['run']} · {s['mode']} · {run['status']} · "
            f"Scheduled ETA {run['planned_eta'] or 'Not supplied'} · Current ETA {run['current_eta'] or 'Not supplied'} · "
            f"Delay {round(run['delay_hours']*60,2) if run.get('delay_hours') is not None else 'Not supplied'} min · "
            f"Critical {'yes' if run['critical'] else 'no'} · {run['actual_source'] or 'Client workbook schedule; no execution feed'}")


def answer(owner,message,selected_run_id=None,service_date=None,session_id=None,workspace=None):
    text=message.casefold()
    # Explicit planning requests remain routed to the deterministic planner.
    explicit_plan=bool(re.search(r'^\s*(?:please\s+)?(?:plan|create)\b.*\bfrom\s+.+?\s+to\s+.+',text))
    if explicit_plan:return None
    if workspace!='LIVE OPERATIONS' and not selected_run_id and re.search(r'\b(?:AIR|TRK|VEH)-\d+\b',message,re.I):return None
    selected_query=bool(selected_run_id and re.search(r'\b(?:it|its|this|selected|run|eta|etd|delay|driver|registration|weight|cargo|aircraft|position|location|option|unavailable|recover)\b',text))
    if re.search(r'\bGPS\b',message,re.I) and re.search(r'\b(?:live|real|exact)\b',text) and re.search(r'\b(?:fedex|con|package)\b',text):
        return reply('Real live FedEx GPS is unavailable. SYNTHETIC_TELEMETRY may provide a simulated location, never real FedEx GPS. FEDEX_SOURCE schedules and CON associations are not live tracking feeds and do not establish an exact live position.')
    con=re.search(r'\b(?:find|locate|track|search|where is)\s+(?:the\s+)?(?:CON|package)\s+([A-Za-z0-9_-]+)',message,re.I)
    followup=bool(re.search(r'\b(?:those|their|these)\b',text) and re.search(r'critical|eta|status|delayed|arrived',text))
    operational=bool(re.search(r'\bruns?\b|critical lanes|control tower|fedex network status|\blanes\b.*(?:delay|risk)|(?:status|eta).*\b[A-Z0-9]{2,}-[A-Z0-9]{2,}\b',message,re.I))
    operational=operational or bool(workspace=='LIVE OPERATIONS' and re.search(r'\b(?:operational|movements?|services?|lanes|attention)\b',text))
    if not con and not operational and not followup and not selected_query and workspace!='LIVE OPERATIONS':return None
    service=ControlTower()
    date=datetime.fromisoformat(service_date).date() if service_date else datetime.now(ZoneInfo('Asia/Kolkata')).date()
    if con:
        try:result=service.con(owner,con[1])
        except KeyError:return reply('No CON association exists for that number in your operational network. A generated planning shipment ID is not a CON.')
        run=result['run'];location=run.get('latest_location')
        service.chat_context(owner,run['service_date'],[run['run_id']],session_id)
        return reply(f"CON {con[1]} · {result['con']['source']}\n{run_text(run)}\nLocation: {location or 'Not supplied'} · {run.get('location_source') or 'No tracking feed'}\nLast update: {run['last_update_at']}",[{'type':'focus_operational_run','data':run}])
    rows=service.runs(owner,date)
    if not rows:return reply('No operational runs are loaded for the selected service date. Import the client workbook in Live Operations.')
    summary=service.summary(rows)
    network=f"{summary['total_runs']} operational runs are loaded: {summary['air_runs']} Air and {summary['surface_runs']} Surface."
    if 'compare' in text:
        identifiers=re.findall(r'\b[A-Z0-9]{2,}-[A-Z0-9]{2,}\b',message,re.I)
        remembered=service.chat_context(owner,date,session_id=session_id) or []
        comparisons=[r for r in rows if r['run_id'] in message or r['schedule']['lane'].casefold() in [i.casefold() for i in identifiers]] if identifiers or any(r['run_id'] in message for r in rows) else [r for r in rows if r['run_id'] in remembered]
        if len(comparisons)!=2:return reply('Specify two operational run identifiers or first query exactly two runs. A lane can contain multiple services; no pair has been assumed.')
        return reply('Operational comparison (source facts):\n'+'\n'.join(run_text(r) for r in comparisons)+'\nOperational cost, cargo and vehicle details are unavailable unless supplied by the source.')
    if selected_query or re.search(r'current delayed run|critical delayed run|selected run',text):
        remembered=service.chat_context(owner,date,session_id=session_id)
        run=next((r for r in rows if r['run_id']==selected_run_id),None)
        if run is None and selected_run_id is None and remembered and len(remembered)==1:
            run=next((r for r in rows if r['run_id']==remembered[0]),None)
        if run is None:return reply('No Control Tower run is selected/referenced. Select an operational run first.')
        if re.search(r'\b(?:driver|registration|cargo|weight|contents|customer|aircraft type|gps)\b',text):
            return reply('That operational fact is unavailable from the imported workbook and associated events. No value has been inferred.')
        run=service.detail(owner,run['run_id'])
        if re.search(r'next option|next eligible',text):
            departures=[r for r in rows if r['schedule']['origin_station']==run['schedule']['origin_station'] and r['schedule']['gateway']==run['schedule']['gateway'] and r['planned_etd'] and run['planned_etd'] and r['planned_etd']>run['planned_etd']]
            departures.sort(key=lambda r:r['planned_etd'])
            return reply(('Next scheduled departure after this run: '+run_text(departures[0])+f" · ETD {departures[0]['planned_etd']}" if departures else 'No later imported service is available for this station and service date.')+' Shipment-ready time and cutoff eligibility must be evaluated in Planning → Schedules; readiness has not been assumed.')
        if re.search(r'unavailable|recovery',text):
            return reply(run_text(run)+'\nScenario: source record unchanged. Recovery requires an explicit Planning calculation with origin, destination, shipment weight and constraints. No recovery alternative has been calculated yet.')
        result=run_text(run)+f" · Scheduled ETD {run['planned_etd'] or 'Unavailable'}"
        if re.search(r'why.*delay',text):
            reasons=[]
            for event in run.get('events',[]):
                try:payload=json.loads(event.get('payload_json') or '{}')
                except (ValueError,TypeError):continue
                if payload.get('reason'):reasons.append(str(payload['reason']))
            result+='\nAssociated event reason: '+ '; '.join(reasons) if reasons else '\nA delay reason is unavailable from the associated events.'
        if re.search(r'eta.*chang|chang.*eta',text):
            result+=f"\nETA {'has changed from the scheduled baseline' if run['current_eta']!=run['planned_eta'] else 'matches the scheduled baseline'}. No new scan has been inferred."
        if re.search(r'location|position',text):
            location=run.get('latest_location') if run.get('location_source')=='FEDEX_SCAN' else (run.get('visualization') or {}).get('position')
            result+=f"\nLocation: {location or 'Unavailable'} · {'Reported scan location' if run.get('location_source')=='FEDEX_SCAN' else 'Schedule-derived position (city-centre estimate, not GPS)' if location else 'No coordinates supplied'}"
        minutes=re.search(r'(\d+)\s*[- ]?\s*min(?:ute)?s?',text)
        if minutes:
            eta=run['current_eta']
            result+=f"\nHypothetical ETA: {(datetime.fromisoformat(eta)+timedelta(minutes=int(minutes[1]))).isoformat() if eta else 'Unavailable'}. Operator: verify the latest scan/ETA, assess downstream handover and SLA impact, and escalate the affected lane. This does not modify the run."
        return reply(result)
    candidates=rows
    if followup:
        ids=service.chat_context(owner,date,session_id=session_id)
        if ids is None:return reply('No previous Control Tower result set is referenced for this service date. Query operational runs first.')
        candidates=[r for r in rows if r['run_id'] in ids]
    mode='Air' if re.search(r'\bair\b',text) else 'Surface' if re.search(r'\bsurface\b',text) else ''
    if mode:candidates=[r for r in candidates if r['schedule']['mode']=='AIR'] if mode=='Air' else [r for r in candidates if r['schedule']['mode']=='SURFACE']
    loaded_count=summary['air_runs'] if mode=='Air' else summary['surface_runs'] if mode=='Surface' else summary['total_runs']
    location=re.search(r'\b(?:runs?|services?)\s+(?:for|in|through|depart(?:ing)? from|from)\s+(.+?)[?.!]*$',message,re.I)
    if location:
        query=location[1].strip().rstrip('?.!')
        candidates=[r for r in candidates if location_matches(r,query)]
    lane=re.search(r'\b([A-Z0-9]{2,}-[A-Z0-9]{2,})\b',message,re.I)
    if lane:candidates=[r for r in candidates if r['schedule']['lane'].casefold()==lane[1].casefold()]
    run_number=re.search(r'\brun\s+(\d+)\b',text)
    if run_number:candidates=[r for r in candidates if str(r['schedule']['run'])==run_number[1]]
    wanted=None
    if re.search(r'expected\s+delay(?:ed)?',text):wanted={'EXPECTED DELAY'}
    elif re.search(r'delay|at risk',text):wanted={'EXPECTED DELAY','DELAYED'}
    elif 'on time' in text:wanted={'ON TIME'}
    elif 'arrived' in text:wanted={'ARRIVED'}
    elif 'scheduled' in text:wanted={'SCHEDULED'}
    if wanted:candidates=[r for r in candidates if r['status'] in wanted]
    if 'attention' in text:candidates=[r for r in candidates if r['critical'] or r['status'] in {'DELAYED','EXPECTED DELAY'}]
    if 'critical' in text:candidates=[r for r in candidates if r['critical']]
    service.chat_context(owner,date,[r['run_id'] for r in candidates],session_id)
    noun=f'{mode} runs' if mode else 'operational runs'
    if not candidates:
        if 'critical' in text and wanted:return reply('No critical lanes are currently at risk. '+network)
        if location:return reply(f'No {noun} matching {query} were found for the selected service date. {loaded_count} {noun} are currently loaded.')
        if wanted=={'EXPECTED DELAY','DELAYED'}:
            scoped=[r for r in rows if not mode or (r['schedule']['mode']=='AIR' if mode=='Air' else r['schedule']['mode']=='SURFACE')]
            scheduled=' and all are currently Scheduled.' if scoped and all(r['status']=='SCHEDULED' for r in scoped) else '.'
            return reply(f'No {noun} are currently delayed. {loaded_count} {noun} are loaded for the selected service date'+scheduled)
        if wanted and len(wanted)==1:
            state={'ON TIME':'On Time','EXPECTED DELAY':'Expected Delay','ARRIVED':'Arrived','SCHEDULED':'Scheduled'}[next(iter(wanted))]
            return reply(f'No {noun} are currently {state}. {loaded_count} {noun} are loaded for the selected service date.')
        return reply(f'No matching {noun} were found for the selected service date. '+network)
    if workspace=='LIVE OPERATIONS' and not operational and not followup and not selected_query:
        return reply('Select an imported operational run or ask about Air/Surface runs, lanes, status or timings. Missing operational facts are unavailable. Use Planning for shipment calculations.')
    if re.search(r'how many|network status|control tower',text):
        return reply(network+f" Matching {noun}: {len(candidates)}."+(' All are currently Scheduled.' if all(r['status']=='SCHEDULED' for r in candidates) else ''))
    lines=[network,f'Matching {noun}: {len(candidates)}.']
    if all(r['status']=='SCHEDULED' for r in candidates):lines.append('All matching runs are currently Scheduled; no departure event is recorded.')
    if 'critical' in text and not wanted:lines.append('Critical marking is separate from operational delay; Scheduled and On Time critical lanes are not currently at risk.')
    lines.extend(run_text(r) for r in candidates)
    actions=[{'type':'focus_operational_run','data':candidates[0]}] if len(candidates)==1 and (lane or run_number) else []
    return reply('\n'.join(lines),actions)
