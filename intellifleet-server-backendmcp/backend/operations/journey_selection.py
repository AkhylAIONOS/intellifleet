"""Canonical current revisions; never collapse independent same-lane shipments."""
import re


def lane_key(journey):
    return tuple(str(journey.get(k) or journey.get('requested_'+k) or '').strip().casefold()
                 for k in ('source','destination'))


def lane_mentioned(journey, text):
    names = [{str(journey.get(prefix+k) or '').strip().casefold() for prefix in ('','requested_')} - {''}
             for k in ('source','destination')]
    return any(re.search(r'(?<!\w)'+re.escape(a)+r'\s*(?:to|→|->)\s*'+re.escape(b)+r'(?!\w)', text.casefold())
               for a in names[0] for b in names[1])


def current_journeys(context, owner=None, active_only=False):
    rows = list((context.get('journeys') or {}).values())
    if context.get('selected_plan_id'):
        rows.append({k:v for k,v in context.items() if k!='journeys'})
    identities={}
    for row in rows:
        if row.get('journey_id'):
            for field in ('movement_id','selected_plan_id'):
                if row.get(field):identities[row[field]]=row['journey_id']
    unique = {}
    for row in rows:
        key = row.get('journey_id') or identities.get(row.get('movement_id')) or identities.get(row.get('selected_plan_id')) or row.get('movement_id') or row.get('selected_plan_id')
        old = unique.get(key)
        revision = lambda c: (c.get('selected_plan') or {}).get('revision', c.get('revision',0)) or 0
        if key and (old is None or revision(row)>=revision(old)):
            unique[key] = row
    result=list(unique.values())
    if active_only and owner is not None:
        from backend.fedex.telemetry import runtime
        def active(row):
            try:
                sim=runtime.get(owner,row.get('movement_id'))
                return not sim.stopped and sim.progress<1
            except KeyError:
                return False
        result=[row for row in result if active(row)]
    return result


def latest_per_lane(journeys):
    # Compatibility name: only repeated logical identities are revisions.
    return current_journeys({'journeys':{str(i):c for i,c in enumerate(journeys)}})
