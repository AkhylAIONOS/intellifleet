"""Location aliases for operational filtering; source workbook values stay intact."""
import re
import json


def location_matches(run, query):
    s=run['schedule']
    fields=[s.get(k,'') for k in ('origin_city','origin_station','gateway','lane')]
    fields.extend(str(v) for k,v in s.get('source',{}).items() if any(w in k.casefold() for w in ('city','station','hub','gtw','lane')))
    aliases={'delhi':('delhi','delgw','ndls','del','dli','delmo','delpa','delso'), 'del':('delhi','delgw','ndls','del','dli','delmo','delpa','delso')}
    words=aliases.get(query.casefold(),(query.casefold(),))
    return any(re.search(r'(?<![a-z0-9])'+re.escape(word)+r'(?![a-z0-9])',str(field).casefold()) for field in fields for word in words)


def matches_search(run,query):
    if query.casefold() in {'delhi','del'}:
        return location_matches(run,query)
    return location_matches(run,query) or query.casefold() in json.dumps(run['schedule']).casefold()
