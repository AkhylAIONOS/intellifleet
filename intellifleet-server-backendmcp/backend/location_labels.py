"""Display aliases for existing nodes only; never creates or changes topology.

Airport city labels below are retained from the project's verified transport
registry (operations/service.py in HEAD). Airport-to-gateway relationships come
from supplied Air lanes. Unknown gateway names deliberately remain unknown.
"""
import re
from collections import defaultdict

AIRPORT_CITIES={'UDR':'Udaipur','DEL':'Delhi','BOM':'Mumbai','BLR':'Bengaluru'}
STATION_NAMES={'NDLS':'New Delhi Railway Station'}
CITY_ALIASES={'bengaluru':['bangalore'],'cochin':['kochi'],'delhi':['new delhi']}


def labels(schedules):
    names=defaultdict(set);origins=set();gateways=set()
    for s in schedules:
        origins.add(s['origin_station']);gateways.add(s['gateway'])
        if s.get('origin_city'):names[s['origin_station']].add(s['origin_city'].title())
        if s['mode']=='AIR' and re.fullmatch(r'[A-Z]{3}-[A-Z]{3}',s['lane']):
            _,airport=s['lane'].split('-')
            if airport in AIRPORT_CITIES:names[s['gateway']].add(AIRPORT_CITIES[airport])
    result={}
    for code in sorted(origins|gateways):
        if code in STATION_NAMES:names[code]={STATION_NAMES[code]}
        verified=sorted(names[code]);name=verified[0] if len(verified)==1 else None
        aliases=[*verified]
        for value in verified:aliases.extend(CITY_ALIASES.get(value.casefold(),[]))
        result[code]=dict(code=code,name=name,label=f'{name} ({code})' if name else code,
            aliases=aliases,origin=code in origins,gateway=code in gateways,
            name_source='WORKBOOK_OR_VERIFIED_REFERENCE' if name else 'UNAVAILABLE')
    return result


def matching_codes(value,mapping,role=None):
    value=value.strip();parenthesized=re.search(r'\(([A-Z0-9]+)\)\s*$',value,re.I)
    wanted=(parenthesized[1] if parenthesized else value).casefold()
    eligible={k:v for k,v in mapping.items() if not role or v[role]}
    exact=[k for k in eligible if k.casefold()==wanted]
    if exact:return exact
    return [k for k,v in eligible.items() if wanted in [a.casefold() for a in v['aliases']]]


def resolve_pair(origin,destination,model):
    mapping=labels(model['schedules'])
    origins=matching_codes(origin,mapping,'origin');destinations=matching_codes(destination,mapping,'gateway')
    if len(origins)==1 and len(destinations)==1:return origins[0],destinations[0]
    connected=[(a,b) for a in origins for b in destinations if any(r['from_location']==a and r['to_location']==b for r in model['routes'])]
    if len(set(connected))==1:return connected[0]
    return None
