"""Read-only city-centre lane estimates. Never stores scans or modifies schedules."""
from datetime import datetime
from functools import lru_cache
import re

@lru_cache(maxsize=1)
def city_coordinates():
    from backend.client_network import CITY_CENTRES, network
    locations=dict(CITY_CENTRES)
    for node in network()['warehouses']:
        if node['latitude'] is not None:
            locations[node['name']]=(node['latitude'],node['longitude'])
            locations['city:'+node['city'].casefold()]=locations[node['name']]
    return locations

def visualization(run, now, imported_schedules=None):
    schedule=run['schedule']
    codes=schedule['lane'].split('-') if re.fullmatch(r'[A-Z]{3}-[A-Z]{3}',schedule['lane']) else [schedule['origin_station'],schedule['gateway']]
    coords=city_coordinates()
    # Resolve operational station codes only from the imported workbook itself.
    # Air lane IATA pairs tie station/gateway codes to city reference coordinates.
    stations={}
    for s in imported_schedules or []:
        if s['mode']=='AIR' and re.fullmatch(r'[A-Z]{3}-[A-Z]{3}',s['lane']):
            a,b=s['lane'].split('-')
            if coords.get(a):stations[s['origin_station']]=coords[a]
            if coords.get(b):stations[s['gateway']]=coords[b]
        city=coords.get('city:'+s['origin_city'].casefold())
        if city and s['origin_station'] not in stations:stations[s['origin_station']]=city
    origin=schedule.get('origin_coordinates') or stations.get(schedule['origin_station']) or coords.get(codes[0]) or coords.get('city:'+schedule['origin_city'].casefold())
    destination=schedule.get('destination_coordinates') or stations.get(schedule['gateway']) or coords.get(codes[1])
    position=None
    if origin and destination and run.get('planned_etd') and run.get('planned_eta'):
        etd=datetime.fromisoformat(run['planned_etd']);eta=datetime.fromisoformat(run['planned_eta'])
        duration=(eta-etd).total_seconds()
        if duration>0:
            progress=min(1,max(0,(now-etd).total_seconds()/duration))
            position=[origin[i]+(destination[i]-origin[i])*progress for i in (0,1)]
    return dict(origin=origin,destination=destination,position=position,location_source='Schedule-derived position',geometry_source='Imported endpoint mapping + planning-network city-centre reference; not facility coordinates or road routing')
