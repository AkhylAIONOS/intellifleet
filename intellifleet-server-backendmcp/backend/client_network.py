"""Workbook-only topology with deterministic, service-bound operational enrichment.

No CSV fallback. Missing resource count defaults to one; explicit zero stays zero.
Coordinates are optional city-centre references, never new facilities or GPS.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import os
import random

from backend.fedex.importer import load_schedules, workbook_path
from backend.fedex.eligibility import IST, candidate
from backend.fedex.models import EligibilityInput


@dataclass(frozen=True)
class EnrichmentConfig:
    seed: int = 42
    enabled: bool = True
    missing_resource_count: int = 1
    shipments_per_resource: int = 8
    weight_min_kg: float = 25
    weight_max_kg: float = 100
    packages_min: int = 1
    packages_max: int = 12
    air_capacity_kg: float = 12000
    surface_capacity_kg: float = 2500
    train_capacity_kg: float = 18000
    availability_probability: float = 1
    cost_min: float = 1500
    cost_max: float = 4500
    air_cost_multiplier: float = 3
    reliability_min: float = .90
    reliability_max: float = .99
    risk_min: float = .01
    risk_max: float = .08
    fuel_fraction: float = .3
    sla_buffer_hours: float = 4
    disruption_probability: float = 0
    station_capacity_kg: float = 50000
    station_inventory_units: int = 10000

    def __post_init__(self):
        if self.shipments_per_resource < 0 or self.missing_resource_count < 0:
            raise ValueError('Counts must be nonnegative')
        if not 0 <= self.availability_probability <= 1 or not 0 <= self.disruption_probability <= 1:
            raise ValueError('Probabilities must be between zero and one')
        import math
        if any(isinstance(v,(float,int)) and not math.isfinite(v) for v in asdict(self).values()):raise ValueError('Configuration values must be finite')
        if not 0 <= self.reliability_min <= self.reliability_max <= 1 or not 0 <= self.risk_min <= self.risk_max <= 1:raise ValueError('Invalid reliability/risk range')
        if not 0 <= self.cost_min <= self.cost_max or not 0 <= self.fuel_fraction <= 1:raise ValueError('Invalid costs')
        if not 1 <= self.packages_min <= self.packages_max:raise ValueError('Invalid package range')
        if self.sla_buffer_hours < 0 or self.station_capacity_kg < 0:raise ValueError('Invalid SLA/station capacity')
        if min(self.air_capacity_kg, self.surface_capacity_kg, self.train_capacity_kg) <= 0:
            raise ValueError('Capacities must be positive')
        if not 0 < self.weight_min_kg <= self.weight_max_kg:
            raise ValueError('Invalid shipment weight range')


def configuration():
    values = json.loads(os.environ.get('SYNTHETIC_ENRICHMENT_CONFIG', '{}'))
    values['seed'] = int(os.environ.get('SYNTHETIC_ENRICHMENT_SEED', values.get('seed', 42)))
    values['enabled'] = os.environ.get('SYNTHETIC_ENRICHMENT_ENABLED', str(values.get('enabled', True))).lower() == 'true'
    return EnrichmentConfig(**values)


# Optional display references for supplied city/station codes only.
# Unresolved endpoints stay unpositioned. These never define topology.
CITY_CENTRES = {
    'CJB': (11.0168, 76.9558), 'BLR': (12.9716, 77.5946),
    'DEL': (28.6139, 77.2090), 'UDR': (24.5854, 73.7125),
    'BOM': (19.0760, 72.8777), 'MAA': (13.0827, 80.2707),
    'HYD': (17.3850, 78.4867), 'CCU': (22.5726, 88.3639),
    'AMD': (23.0225, 72.5714), 'PNQ': (18.5204, 73.8567),
    'COK': (9.9312, 76.2673), 'JAI': (26.9124, 75.7873),
    'LKO': (26.8467, 80.9462), 'NAG': (21.1458, 79.0882),
    'IDR': (22.7196, 75.8577), 'BBI': (20.2961, 85.8245),
    'GAU': (26.1445, 91.7362), 'PAT': (25.5941, 85.1376),
    'VNS': (25.3176,82.9739), 'KAN': (26.4499,80.3319), 'CNB': (26.4499,80.3319),
    'NDL': (28.6139,77.2090), 'AGR': (27.1767,78.0081), 'LUH': (30.9010,75.8573),
    'LDH': (30.9010,75.8573), 'DDU': (25.2819,83.1199), 'BDQ': (22.3072,73.1812),
    'AWY': (10.1076,76.3516), 'BNC': (12.9716,77.5946), 'CBE': (11.0168,76.9558),
    'MAS': (13.0827,80.2707), 'IXM': (9.9252,78.1198), 'LB': (9.9252,78.1198),
    'MDU': (9.9252,78.1198), 'SMV': (12.9716,77.5946),
    'IXC': (30.7333, 76.7794), 'VGA': (16.5062, 80.6480),
}


def generate(path=None, config=None):
    path = Path(path or workbook_path())
    config = config or configuration()
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    schedules = load_schedules(path)
    routes, vehicles, shipments = [], [], []
    nodes = {}
    topology_fields = ('origin_city', 'origin_station', 'gateway', 'lane', 'run', 'mode',
                       'source_mode', 'service', 'cutoff_minutes', 'etd_minutes',
                       'eta_minutes', 'retrieval_minutes', 'transit_minutes', 'vehicle_count')
    for s in schedules:
        rng = random.Random(hashlib.sha256(f'{version}:{config.seed}:{s.schedule_id}'.encode()).hexdigest())
        for code in (s.origin_station, s.gateway):
            if code not in nodes:
                coord = CITY_CENTRES.get(code[:3])
                nodes[code] = dict(warehouse_id=len(nodes)+1, id=len(nodes)+1, name=code,
                    city=s.origin_city if code == s.origin_station else '', is_active=1,
                    latitude=coord[0] if coord else None, longitude=coord[1] if coord else None,
                    inventory=config.station_inventory_units if config.enabled else 0, reserved_inventory=0,
                    storage_capacity=config.station_capacity_kg if config.enabled else 0,
                    processing_capacity_kg=config.station_capacity_kg if config.enabled else 0,
                    current_load_kg=0, reliability=config.reliability_min, disruption_risk=0,
                    data_source='CLIENT_SOURCE', coordinate_source='City-centre estimate; not GPS',
                    provenance={'name':'CLIENT_SOURCE','city':'CLIENT_SOURCE' if code == s.origin_station else 'CALCULATED',
                                'latitude':'SYNTHETIC_ENRICHMENT','longitude':'SYNTHETIC_ENRICHMENT',
                                'processing_capacity_kg':'SYNTHETIC_ENRICHMENT','current_load_kg':'CALCULATED'})
        nodes[s.origin_station]['city']=s.origin_city
        nodes[s.origin_station]['provenance']['city']='CLIENT_SOURCE'
        duration = s.transit_minutes if s.transit_minutes is not None else ((s.eta_minutes-s.etd_minutes)%1440 if s.eta_minutes is not None and s.etd_minutes is not None else None)
        capacity = {'AIR':config.air_capacity_kg,'SURFACE':config.surface_capacity_kg,'RAIL':config.train_capacity_kg}[s.mode]
        count = (s.vehicle_count if s.vehicle_count is not None else config.missing_resource_count) if config.enabled else 0
        mode = {'AIR':'air','SURFACE':'road','RAIL':'rail'}[s.mode]
        base = round(rng.uniform(config.cost_min,config.cost_max)*(config.air_cost_multiplier if s.mode == 'AIR' else 1),2) if config.enabled else 0
        route = dict(route_id=s.schedule_id, schedule_id=s.schedule_id, from_location=s.origin_station,
            to_location=s.gateway, route_type=mode, distance=0, duration=(duration or 0)/60,
            cost=base, base_transport_cost=base, fuel_cost=round(base*config.fuel_fraction,2),
            reliability=round(rng.uniform(config.reliability_min,config.reliability_max),4),
            operational_risk=round(rng.uniform(config.risk_min,config.risk_max),4), weather_risk=0,
            status='active' if s.valid else 'source_validation_required', schedule=s.model_dump(mode='json'),
            capacity_per_day_kg=count*capacity, current_utilization_pct=0,
            sla_hours=(duration or 0)/60+config.sla_buffer_hours, data_source='CLIENT_SOURCE',
            source_coords={'lat':nodes[s.origin_station]['latitude'],'lng':nodes[s.origin_station]['longitude']},
            destination_coords={'lat':nodes[s.gateway]['latitude'],'lng':nodes[s.gateway]['longitude']},
            provenance={**{f:'CLIENT_SOURCE' for f in topology_fields},'duration':'CALCULATED',
                        'distance':'CALCULATED','cost':'SYNTHETIC_ENRICHMENT','reliability':'SYNTHETIC_ENRICHMENT',
                        'operational_risk':'SYNTHETIC_ENRICHMENT','current_utilization_pct':'CALCULATED'})
        a,b=nodes[s.origin_station],nodes[s.gateway]
        if a['latitude'] is not None and b['latitude'] is not None:
            from backend.fedex.simulator import distance_km
            route['distance']=round(distance_km((a['latitude'],a['longitude']),(b['latitude'],b['longitude'])),2)
        for instance in range(count):
            resource_id=f"{'AIR' if s.mode=='AIR' else 'SUR' if s.mode=='SURFACE' else 'TRN'}-{s.schedule_id}-{instance+1:02d}"
            available = rng.random() < config.availability_probability
            disrupted=config.disruption_probability>0 and rng.random()<config.disruption_probability
            available=available and not disrupted
            vehicle = dict(id=resource_id,label=resource_id,warehouse_id=nodes[s.origin_station]['warehouse_id'],
                type={'AIR':'plane','SURFACE':'truck','RAIL':'train'}[s.mode],
                capacity=capacity,current_location=s.origin_station,is_available=int(available),is_active=1,
                status='breakdown' if disrupted else 'available' if available else 'unavailable',service_id=s.schedule_id,
                client_service=s.service,compatible_modes=[mode],reliability=route['reliability'],
                breakdown_risk=route['operational_risk'],assigned_load_kg=0,available_capacity_kg=capacity,
                data_source='SYNTHETIC_ENRICHMENT', provenance={'id':'SYNTHETIC_ENRICHMENT',
                    'capacity':'SYNTHETIC_ENRICHMENT','service_id':'CLIENT_SOURCE','client_service':'CLIENT_SOURCE',
                    'assigned_load_kg':'CALCULATED','available_capacity_kg':'CALCULATED'})
            for n in range(config.shipments_per_resource):
                # Bound generated loads to the attached resource capacity.
                weight=round(min(rng.uniform(config.weight_min_kg,config.weight_max_kg),capacity/max(1,config.shipments_per_resource)),2)
                shipment_id=f'SIM-{resource_id}-{n+1:03d}'
                shipment=dict(shipment_id=shipment_id,con_id=f'CON-{shipment_id}',service_id=s.schedule_id,
                    resource_id=resource_id,origin_station=s.origin_station,gateway=s.gateway,
                    weight_kg=weight,quantity=rng.randint(config.packages_min,config.packages_max),
                    priority=rng.choice(['standard','express']),ready_minutes=rng.randrange(1440),
                    simulated_sla_hours=route['sla_hours'],data_source='SYNTHETIC_ENRICHMENT',
                    provenance={'origin_station':'CLIENT_SOURCE','gateway':'CLIENT_SOURCE','service_id':'CLIENT_SOURCE',
                                'weight_kg':'SYNTHETIC_ENRICHMENT','ready_minutes':'SYNTHETIC_ENRICHMENT'})
                shipments.append(shipment)
                vehicle['assigned_load_kg']+=weight
            vehicle['assigned_load_kg']=round(vehicle['assigned_load_kg'],2)
            vehicle['available_capacity_kg']=round(capacity-vehicle['assigned_load_kg'],2)
            vehicle['utilization_percentage']=round(vehicle['assigned_load_kg']/capacity*100,2)
            nodes[s.origin_station]['current_load_kg']+=vehicle['assigned_load_kg']
            vehicles.append(vehicle)
        attached=[v for v in vehicles if v['service_id']==s.schedule_id]
        route['current_utilization_pct']=round(sum(v['assigned_load_kg'] for v in attached)/max(1,count*capacity)*100,2)
        routes.append(route)
    for node in nodes.values():
        node['current_load_kg']=round(node['current_load_kg'],2)
        node['available_processing_capacity_kg']=round(max(0,node['processing_capacity_kg']-node['current_load_kg']),2)
        node['utilization_percentage']=round(node['current_load_kg']/node['processing_capacity_kg']*100,2) if node['processing_capacity_kg'] else 0
        node['provenance'].update(available_processing_capacity_kg='CALCULATED',utilization_percentage='CALCULATED')
    for collection,default in ((routes,'SYNTHETIC_ENRICHMENT'),(vehicles,'SYNTHETIC_ENRICHMENT'),(shipments,'SYNTHETIC_ENRICHMENT'),(list(nodes.values()),'SYNTHETIC_ENRICHMENT')):
        for item in collection:
            item['provenance']={**{k:default for k in item if k!='provenance'},**item.get('provenance',{})}
    for route in routes:
        route['provenance'].update(route_id='CALCULATED',schedule_id='CALCULATED',from_location='CLIENT_SOURCE',to_location='CLIENT_SOURCE',route_type='CALCULATED',schedule='CLIENT_SOURCE',source_coords='SYNTHETIC_ENRICHMENT',destination_coords='SYNTHETIC_ENRICHMENT',capacity_per_day_kg='CALCULATED',status='CALCULATED')
    for resource in vehicles:
        resource['provenance'].update(current_location='CLIENT_SOURCE',warehouse_id='CALCULATED',compatible_modes='CALCULATED',utilization_percentage='CALCULATED')
    return dict(network_version=version,config=asdict(config),data_source='CLIENT_SOURCE',
        routes=routes,warehouses=list(nodes.values()),vehicles=vehicles,shipments=shipments,
        schedules=[s.model_dump(mode='json') for s in schedules])


@lru_cache(maxsize=4)
def _cached(path, mtime, config_json):
    return generate(path,EnrichmentConfig(**json.loads(config_json)))


def network():
    path=workbook_path()
    return _cached(str(path),path.stat().st_mtime_ns,json.dumps(asdict(configuration()),sort_keys=True))


def validate_topology(model):
    """Fail closed even when callers inject a network into the planning API."""
    canonical=network()
    services={r['route_id']:r for r in canonical['routes']}
    codes={n['name'] for n in canonical['warehouses']}
    if any(n['name'] not in codes for n in model['warehouses']):
        raise ValueError('Station is absent from the client workbook')
    for r in model['routes']:
        source=services.get(r['route_id'])
        if source is None or any(r[k]!=source[k] for k in ('from_location','to_location','route_type')) or r.get('schedule')!=source['schedule']:
            raise ValueError('Service is absent from the client workbook')
    resources={v['id']:(v['service_id'],v['current_location']) for v in canonical['vehicles']}
    if any(resources.get(v['id'])!=(v.get('service_id'),v.get('current_location')) for v in model['vehicles']):
        raise ValueError('Resource is not bound to a generated client service')


def summary(model=None):
    model=model or network()
    resources=model['vehicles']
    capacity=sum(v['capacity'] for v in resources)
    load=sum(v['assigned_load_kg'] for v in resources)
    return dict(client_services=len(model['routes']),client_nodes=len(model['warehouses']),
        air_runs=sum(s['mode']=='AIR' for s in model['schedules']),
        surface_runs=sum(s['mode']=='SURFACE' for s in model['schedules']),
        train_runs=sum(s['mode']=='RAIL' for s in model['schedules']),
        generated_resources=len(resources),simulated_shipments=len(model['shipments']),
        simulated_volume_kg=round(load,2),utilization_percentage=round(load/capacity*100,2) if capacity else 0,
        source_validation_issues=sum(not s['valid'] for s in model['schedules']),network_version=model['network_version'])
