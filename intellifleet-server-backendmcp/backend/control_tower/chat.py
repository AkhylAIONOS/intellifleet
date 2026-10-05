import re
from datetime import datetime
from zoneinfo import ZoneInfo
from .service import ControlTower


def answer(owner,message,selected_run_id=None,service_date=None):
    """Read-only operational queries; never create/import a run from chat."""
    if (re.search(r'\bGPS\b', message, re.I)
            and re.search(r'\b(?:live|real|exact)\b', message, re.I)
            and re.search(r'\b(?:FedEx|CON|package)\b', message, re.I)):
        return {'success': True, 'response':
            'Real live FedEx GPS is unavailable through this demo. Any location labelled '
            'SYNTHETIC_TELEMETRY is an approximate simulated location, not real FedEx GPS. '
            'Source schedules and CON associations do not establish an exact live location.',
            'actions': []}
    con=re.search(r'\b(?:find|locate|track|search|where is)\s+(?:the\s+)?(?:CON|package)\s+([A-Za-z0-9_-]+)',message,re.I)
    overview=bool(re.search(r'control tower|critical lanes|fedex network status',message,re.I))
    operational=bool(re.search(r'\b(?:air|surface|delayed|critical|operational)\s+runs?\b|current delayed run|critical delayed run',message,re.I))
    if not con and not overview and not operational:
        return None
    service=ControlTower()
    if con:
        try:
            result=service.con(owner,con[1])
        except KeyError:
            return {'success':True,'response':'No CON association exists for that number in your operational network. A generated planning shipment ID is not a CON.','actions':[]}
        r=result['run'];s=r['schedule'];location=r.get('latest_location')
        response=f"CON {con[1]} · {result['con']['source']}\n{s['lane']} · Run {s['run']} · {r.get('carrier') or s['service']}\nStatus: {r['status']} · Current ETA: {r['current_eta'] or 'Not supplied'}\nLocation: {location if location else 'Not supplied'} · {r.get('location_source') or 'No tracking feed'}\nLast update: {r['last_update_at']}"
        return {'success':True,'response':response,'actions':[{'type':'focus_operational_run','data':r}]}
    date=datetime.fromisoformat(service_date).date() if service_date else datetime.now(ZoneInfo('Asia/Kolkata')).date()
    rows=service.runs(owner,date)
    if not rows:
        return {'success':True,'response':'No operational runs are loaded for the selected service date.','actions':[]}
    text=message.casefold()
    if re.search(r'current delayed run|critical delayed run',text):
        selected=next((r for r in rows if r['run_id']==selected_run_id),None)
        if selected is None:
            return {'success':True,'response':'No Control Tower run is selected/referenced. Select an operational run first.','actions':[]}
        minutes=re.search(r'(\d+)\s+minutes?\s+later',text)
        response=f"{selected['schedule']['lane']} · Current ETA: {selected['current_eta'] or 'Not supplied'} · {selected['actual_source'] or 'No execution feed'}"
        if minutes:
            from datetime import timedelta
            eta=selected['current_eta']
            response+=f"\nHypothetical ETA: {(datetime.fromisoformat(eta)+timedelta(minutes=int(minutes[1]))).isoformat() if eta else 'Unavailable'}. Operator: verify the latest scan/ETA, assess downstream handover and SLA impact, and escalate the affected lane. This does not modify the run."
        return {'success':True,'response':response,'actions':[]}
    if re.search(r'\bair\b',text):rows=[r for r in rows if r['schedule']['mode']=='AIR']
    if re.search(r'\bsurface\b',text):rows=[r for r in rows if r['schedule']['source_sheet']=='Surface']
    for phrase,status in [('on time','ON TIME'),('scheduled','SCHEDULED'),('arrived','ARRIVED'),('expected delay','EXPECTED DELAY')]:
        if phrase in text:rows=[r for r in rows if r['status']==status]
    city=re.search(r'\bruns?\s+(?:for|in)\s+(.+?)[?.!]*$',message,re.I)
    if city:rows=[r for r in rows if city[1].strip().rstrip('?.!').casefold() in str(r['schedule']).casefold()]
    summary=service.summary(rows)
    risk=[r for r in rows if r['status'] in {'EXPECTED DELAY','DELAYED'}]
    if 'critical' in message.casefold():risk=[r for r in risk if r['critical']]
    elif not re.search(r'delay|risk|control tower|network status',text):risk=rows
    lines=[f"Network status: {summary['total_runs']} runs · {summary['air_runs']} Air · {summary['surface_runs']} Surface.",
           f"Matching runs: {len(risk)} · {summary['critical_lanes_at_risk']} critical lanes at risk."]
    lines.extend(f"{r['schedule']['lane']} · Run {r['schedule']['run']} · {r['status']} · ETA {r['current_eta']} · execution {r['actual_source'] or 'not departed'}" for r in risk)
    lines.append('Next actions: inspect the affected run and verify its latest scan/ETA before requesting a planning alternative.')
    return {'success':True,'response':'\n'.join(lines),'actions':[]}
