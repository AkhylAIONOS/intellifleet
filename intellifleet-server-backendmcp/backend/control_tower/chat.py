import re
from datetime import datetime
from zoneinfo import ZoneInfo
from .service import ControlTower


def answer(owner,message):
    """Read-only operational queries; never create/import a run from chat."""
    con=re.search(r'\b(?:find|locate|track|search|where is)\s+(?:the\s+)?(?:CON|package)\s+([A-Za-z0-9_-]+)',message,re.I)
    overview=bool(re.search(r'control tower|critical lanes|fedex network status',message,re.I))
    if not con and not overview:
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
    date=datetime.now(ZoneInfo('Asia/Kolkata')).date()
    rows=service.runs(owner,date)
    if not rows:
        return {'success':True,'response':'No FedEx operational runs are loaded for today. Load the FedEx Network Plan in Live Operations → Network Overview. Planning alternatives remain separate.','actions':[]}
    summary=service.summary(rows)
    risk=[r for r in rows if r['status'] in {'EXPECTED DELAY','DELAYED'}]
    if 'critical' in message.casefold():risk=[r for r in risk if r['critical']]
    lines=[f"Network status: {summary['total_runs']} runs · {summary['air_runs']} Air · {summary['surface_runs']} Surface.",
           f"At risk: {len(risk)} matching runs · {summary['critical_lanes_at_risk']} critical lanes at risk."]
    lines.extend(f"{r['schedule']['lane']} · Run {r['schedule']['run']} · {r['status']} · ETA {r['current_eta']} · execution {r['actual_source'] or 'not departed'}" for r in risk[:10])
    lines.append('Next actions: inspect the affected run and verify its latest scan/ETA before requesting a planning alternative.')
    return {'success':True,'response':'\n'.join(lines),'actions':[]}
