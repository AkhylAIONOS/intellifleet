"""Deterministic operational answers, independent of planner context."""
import re
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
            f"Critical {'yes' if run['critical'] else 'no'} · {run['actual_source'] or 'FEDEX_SOURCE schedule; no execution feed'}")


def answer(owner,message,selected_run_id=None,service_date=None,session_id=None):
    text=message.casefold()
    if re.search(r'\bGPS\b',message,re.I) and re.search(r'\b(?:live|real|exact)\b',text) and re.search(r'\b(?:fedex|con|package)\b',text):
        return reply('Real live FedEx GPS is unavailable. SYNTHETIC_TELEMETRY may provide a simulated location, never real FedEx GPS. FEDEX_SOURCE schedules and CON associations are not live tracking feeds and do not establish an exact live position.')
    con=re.search(r'\b(?:find|locate|track|search|where is)\s+(?:the\s+)?(?:CON|package)\s+([A-Za-z0-9_-]+)',message,re.I)
    followup=bool(re.search(r'\b(?:those|their|these)\b',text) and re.search(r'critical|eta|status|delayed|arrived',text))
    operational=bool(re.search(r'\bruns?\b|critical lanes|control tower|fedex network status|\blanes\b.*(?:delay|risk)|(?:status|eta).*\b[A-Z0-9]{2,}-[A-Z0-9]{2,}\b',message,re.I))
    if not con and not operational and not followup:return None
    service=ControlTower()
    date=datetime.fromisoformat(service_date).date() if service_date else datetime.now(ZoneInfo('Asia/Kolkata')).date()
    if con:
        try:result=service.con(owner,con[1])
        except KeyError:return reply('No CON association exists for that number in your operational network. A generated planning shipment ID is not a CON.')
        run=result['run'];location=run.get('latest_location')
        service.chat_context(owner,run['service_date'],[run['run_id']],session_id)
        return reply(f"CON {con[1]} · {result['con']['source']}\n{run_text(run)}\nLocation: {location or 'Not supplied'} · {run.get('location_source') or 'No tracking feed'}\nLast update: {run['last_update_at']}",[{'type':'focus_operational_run','data':run}])
    rows=service.runs(owner,date)
    if not rows:return reply('No operational runs are loaded for the selected service date. Load the FedEx Network Plan in Live Operations → Control Tower.')
    summary=service.summary(rows)
    network=f"{summary['total_runs']} operational runs are loaded: {summary['air_runs']} Air and {summary['surface_runs']} Surface."
    if re.search(r'current delayed run|critical delayed run|selected run',text):
        remembered=service.chat_context(owner,date,session_id=session_id)
        run=next((r for r in rows if r['run_id']==selected_run_id),None)
        if run is None and selected_run_id is None and remembered and len(remembered)==1:
            run=next((r for r in rows if r['run_id']==remembered[0]),None)
        if run is None:return reply('No Control Tower run is selected/referenced. Select an operational run first.')
        result=run_text(run)
        minutes=re.search(r'(\d+)\s+minutes?\s+later',text)
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
    if mode:candidates=[r for r in candidates if r['schedule']['mode']=='AIR'] if mode=='Air' else [r for r in candidates if r['schedule']['source_sheet']=='Surface']
    loaded_count=summary['air_runs'] if mode=='Air' else summary['surface_runs'] if mode=='Surface' else summary['total_runs']
    location=re.search(r'\bruns?\s+(?:for|in|through)\s+(.+?)[?.!]*$',message,re.I)
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
    if 'critical' in text:candidates=[r for r in candidates if r['critical']]
    service.chat_context(owner,date,[r['run_id'] for r in candidates],session_id)
    noun=f'{mode} runs' if mode else 'operational runs'
    if not candidates:
        if 'critical' in text and wanted:return reply('No critical lanes are currently at risk. '+network)
        if location:return reply(f'No {noun} matching {query} were found for the selected service date. {loaded_count} {noun} are currently loaded.')
        if wanted=={'EXPECTED DELAY','DELAYED'}:
            scoped=[r for r in rows if not mode or (r['schedule']['mode']=='AIR' if mode=='Air' else r['schedule']['source_sheet']=='Surface')]
            scheduled=' and all are currently Scheduled.' if scoped and all(r['status']=='SCHEDULED' for r in scoped) else '.'
            return reply(f'No {noun} are currently delayed. {loaded_count} {noun} are loaded for the selected service date'+scheduled)
        if wanted and len(wanted)==1:
            state={'ON TIME':'On Time','EXPECTED DELAY':'Expected Delay','ARRIVED':'Arrived','SCHEDULED':'Scheduled'}[next(iter(wanted))]
            return reply(f'No {noun} are currently {state}. {loaded_count} {noun} are loaded for the selected service date.')
        return reply(f'No matching {noun} were found for the selected service date. '+network)
    if re.search(r'how many|network status|control tower',text):
        return reply(network+f" Matching {noun}: {len(candidates)}."+(' All are currently Scheduled.' if all(r['status']=='SCHEDULED' for r in candidates) else ''))
    lines=[network,f'Matching {noun}: {len(candidates)}.']
    if all(r['status']=='SCHEDULED' for r in candidates):lines.append('All matching runs are currently Scheduled; no departure event is recorded.')
    if 'critical' in text and not wanted:lines.append('Critical marking is separate from operational delay; Scheduled and On Time critical lanes are not currently at risk.')
    lines.extend(run_text(r) for r in candidates)
    actions=[{'type':'focus_operational_run','data':candidates[0]}] if len(candidates)==1 and (lane or run_number) else []
    return reply('\n'.join(lines),actions)
