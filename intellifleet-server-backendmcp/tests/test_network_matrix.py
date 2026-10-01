"""All loaded cities/IDs/modes; no city or resource IDs encoded in the matrix."""
import itertools
import json
from collections import Counter
from pathlib import Path
import os
import sqlite3
import pytest


@pytest.fixture
def matrix(tmp_path,monkeypatch):
    from backend.operations.data import DATA_DIR
    from backend.database.database import init_db
    from backend.planning.database import migrate_planning_schema
    source=os.environ.get('UNIFLEET_MATRIX_DB')
    monkeypatch.chdir(tmp_path)
    if source:
        original=sqlite3.connect('file:'+str(Path(source).resolve())+'?mode=ro',uri=True)
        with sqlite3.connect('users.db') as copied:original.backup(copied)
        original.close()
        with sqlite3.connect('users.db') as copied:
            owners=copied.execute("SELECT user_id FROM network_provenance WHERE data_source='SYNTHETIC_NETWORK'").fetchall()
        assert len(owners)==1,'Select an explicit synthetic network snapshot for this matrix'
        owner=owners[0][0]
    else:
        import asyncio,io
        from starlette.datastructures import UploadFile
        from backend.routes.upload.network_upload import upload_network
        init_db();migrate_planning_schema()
        with sqlite3.connect('users.db') as c:
            c.execute("INSERT INTO users(id,first_name,last_name,email,password,verified) VALUES(1,'Matrix','Test','matrix@example.invalid','x',1)")
        files=[UploadFile(io.BytesIO((DATA_DIR/f'{n}.csv').read_bytes()),filename=f'{n}.csv') for n in ('warehouse','vehicle','routes')]
        asyncio.run(upload_network(*files,{'user_id':1}));owner=1
    return PlanningService().load_network(owner),owner

from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService
from backend.operations.journey_queries import answer


def validate_plan(p,request,network):
    routes={r['route_id']:r for r in network['routes']};vehicles={v['id']:v for v in network['vehicles']}
    legs=p['route_legs']
    assert legs and request.shipment.weight_kg>0
    assert legs[0]['from_location']==request.source and legs[-1]['to_location']==request.destination
    assert all(a['to_location']==b['from_location'] for a,b in zip(legs,legs[1:]))
    for leg in legs:
        assert leg['route_id'] in routes
        assert (leg['from_location'],leg['to_location'],leg['route_type'])==tuple(routes[leg['route_id']][k] for k in ('from_location','to_location','route_type'))
    assert p['operational_cost']>=0 and p['duration_hours']>=0 and 0<=p['risk_score']<=1
    assert 0<=p['vehicle_utilization']<=1
    for segment in p.get('leg_assignments') or [{'route_legs':legs,'vehicles':p['vehicles']}]:
        modes={l['route_type'] for l in segment['route_legs']}
        assert sum(v['assigned_load_kg'] for v in segment['vehicles'])==request.shipment.weight_kg
        for vehicle in segment['vehicles']:
            assert vehicle['id'] in vehicles
            assert 0<=vehicle['assigned_load_kg']<=vehicle['capacity']
            actual=vehicles[vehicle['id']]
            assert actual['is_available'] and actual['is_active']
            assert (actual['type'].casefold() in {'plane','aircraft'})==('air' in modes)


def test_all_loaded_cities_routes_vehicles_and_modes(matrix):
    network,owner=matrix;service=PlanningService()
    cities=sorted({w['name'] for w in network['warehouses']})
    assert cities
    for r in network['routes']:
        assert r['from_location'] in cities and r['to_location'] in cities
        assert r['route_id'] is not None and r['route_type'] in {'road','air'}
        assert all(float(r[k])>=0 for k in ('distance','duration','cost'))
        response=answer(owner,f"Show details for route ID {r['route_id']}.",{})
        assert str(r['route_id']) in response['response'] and not response['actions']
    for v in network['vehicles']:
        response=answer(owner,f"Show details for vehicle ID {v['id']}.",{})
        assert str(v['id']) in response['response'] and not response['actions']
    counts=Counter();example={}
    for source,destination in itertools.permutations(cities,2):
        for mode in ('road','air','multimodal'):
            request=PlanningRequest(source=source,destination=destination,shipment={'weight_kg':1},allowed_modes=[mode])
            result=service.plan(owner,request,network=network)
            p=result['recommended_plan'];counts[mode+'_tested']+=1
            if p:
                counts[mode+'_feasible']+=1
                validate_plan(p,request,network)
                actual={l['route_type'] for l in p['route_legs']}
                assert actual==({'road','air'} if mode=='multimodal' else {mode})
                example.setdefault(mode,(source,destination))
            else:
                counts[mode+'_infeasible']+=1
                assert result['reason'] and not result['candidate_plans']
            # Independently check graph connectivity: disconnected endpoints may
            # never acquire a fabricated fallback. Capacity/range can further
            # restrict a connected path and must return a feasibility reason.
            allowed={'road','air'} if mode=='multimodal' else {mode}
            seen={source};pending=[source]
            while pending:
                node=pending.pop()
                for r in network['routes']:
                    if r['from_location']==node and r['route_type'] in allowed and r['status'] in {'active','open','available'} and r['to_location'] not in seen:
                        seen.add(r['to_location']);pending.append(r['to_location'])
            if destination not in seen:assert p is None
    # Ordered multimodal examples are discovered from the graph, not city labels.
    ordered=0
    for source,destination in itertools.permutations(cities,2):
        request=PlanningRequest(source=source,destination=destination,shipment={'weight_kg':1},allowed_modes=['multimodal'],required_mode_sequence=['road','air','road'])
        result=service.plan(owner,request,network=network)
        if result['recommended_plan']:
            ordered+=1;validate_plan(result['recommended_plan'],request,network)
            assert [k for k,g in itertools.groupby(l['route_type'] for l in result['recommended_plan']['route_legs'])]==['road','air','road']
    report={'cities':len(cities),'routes':len(network['routes']),'vehicles':len(network['vehicles']),**counts,'ordered_multimodal_feasible':ordered,'example_pairs':example}
    Path('/private/tmp/unifleet-network-matrix'+('-current' if os.environ.get('UNIFLEET_MATRIX_DB') else '')+'.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
