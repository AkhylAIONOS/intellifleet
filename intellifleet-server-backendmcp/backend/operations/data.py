"""Canonical demo adapters and cross-file validation. Never reads the FedEx workbook."""
import csv
import math
from pathlib import Path
from backend.fedex.models import Schedule

def validate_network(warehouses, vehicles, routes, strict=True):
    errors=[]
    def number(row,key,minimum=0,maximum=float('inf'),required=False):
        value=row.get(key)
        if value is None or str(value).strip() in {'','nan'}:
            if required: errors.append(f'Missing {key}')
            return None
        try:
            value=float(value)
            if not math.isfinite(value) or not minimum<=value<=maximum: raise ValueError()
            return value
        except (ValueError,TypeError): errors.append(f'Invalid {key}: {value}'); return None
    for group,key in [(warehouses,'Name'),(warehouses,'WarehouseID'),(vehicles,'VehicleID'),(routes,'RouteID')]:
        ids=[str(r[key]).strip() for r in group if r.get(key) and str(r[key])!='nan']
        if len(ids)!=len(set(ids)): errors.append(f'Duplicate {key}')
    names={str(w['Name']).strip() for w in warehouses}
    for w in warehouses:
        number(w,'Latitude',-90,90,required='Latitude' in w); number(w,'Longitude',-180,180,required='Longitude' in w)
        inventory=number(w,'Inventory'); capacity=number(w,'StorageCapacity')
        reserved=number(w,'ReservedInventory')
        if capacity and inventory is not None and inventory>capacity: errors.append('Inventory exceeds capacity')
        if reserved and inventory is not None and reserved>inventory: errors.append('Reserved inventory exceeds inventory')
    for v in vehicles:
        if str(v['WarehouseName']).strip() not in names: errors.append('Orphan vehicle warehouse')
        number(v,'VehicleCapacity',1,150000,True)
        number(v,'AvgSpeedKmph',1,900 if str(v.get('Mode','road')).lower()=='air' else 65)
    facilities={str(w['Name']).strip():w for w in warehouses}
    from backend.fedex.simulator import distance_km
    for r in routes:
        refs=[r['Source'],r['Destination']]+str(r.get('IntermediateLocation') or '').replace('|',',').split(',')
        if any(str(n).strip(' []') not in names for n in refs if str(n).strip(' []') not in {'','nan'}): errors.append('Orphan route warehouse')
        d=number(r,'DistanceKm',.001); t=number(r,'TypicalDurationMin',.001)
        if str(r.get('RouteType')).lower()=='road' and d and t and not 10<=d/(t/60)<=(65 if strict else 90):
            errors.append(f'Implausible road speed: {r.get("RouteID", "route")}')
        if d and str(r['Source']).strip() in facilities and str(r['Destination']).strip() in facilities:
            a,b=facilities[str(r['Source']).strip()],facilities[str(r['Destination']).strip()]
            try:
                straight=distance_km((float(a['Latitude']),float(a['Longitude'])),(float(b['Latitude']),float(b['Longitude'])))
                if strict and d<straight*.95: errors.append('Route distance shorter than geodesic')
            except (ValueError,KeyError,TypeError): pass
        sla=number(r,'SLAHours',.001)
        if sla and t and sla<t/60: errors.append('SLA shorter than transit')
    for group in (warehouses,vehicles,routes):
        for r in group:
            for key in r:
                if 'Cost' in key or key in {'MaxRangeKm','LoadingTimeMin','UnloadingTimeMin','CapacityPerDayKg'}: number(r,key)
                if key.endswith('Score'): number(r,key,0,1)
    if errors: raise ValueError('; '.join(sorted(set(errors))))
    return {'warehouses':len(warehouses),'vehicles':len(vehicles),'routes':len(routes),'validation':'PASS'}


def rows(name):
    raise ValueError('Legacy synthetic CSV network is disabled; use the client workbook')


def synthetic_schedules(records=None):
    if records is not None:
        raise ValueError('Independent schedule topology is disabled')
    from backend.fedex.routes import schedules
    return schedules()
