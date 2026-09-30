"""Keep simulation regressions offline; real OSM geometry is checked by browser QA.

Only the shared provider boundary is replaced. Fresh RoadRoutingEngine instances
in provider tests exercise parsing, network errors, cache and capabilities.
"""
import pytest


@pytest.fixture(autouse=True)
def offline_road_geometry(monkeypatch):
    from backend.operations.road_routing_engine import RoadRoute, RoadPoint
    from backend.fedex import simulator

    def route(a,b,c,d,optimization='FASTEST',**kwargs):
        from backend.operations.road_routing_engine import RoadRoutingError
        if optimization!='FASTEST':
            raise RoadRoutingError('FASTEST only', 'ROAD_OPTIMIZATION_UNSUPPORTED')
        geometry=[(a,b),(a+(c-a)*.3,b+(d-b)*.2),(a+(c-a)*.6,b+(d-b)*.7),(c,d)]
        return RoadRoute(RoadPoint(a,b),RoadPoint(c,d),RoadPoint(a,b),RoadPoint(c,d),
            sum(simulator.distance_km(x,y) for x,y in zip(geometry,geometry[1:])),600,geometry,
            source='TEST FIXTURE: not map data',route_id=f'test-{a}-{b}-{c}-{d}')
    monkeypatch.setattr(simulator.road_routing_engine,'get_route',route)
