"""Local in-process benchmark; no production DB, network or credentials needed."""
import gc
import json
import logging
import statistics
import time
import tracemalloc
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.fedex import routes
from backend.fedex.disruptions import inject
from backend.fedex.importer import load_schedules
from backend.fedex.models import SimulationInput, DisruptionInput
from backend.fedex.telemetry import Runtime
from backend.routes.auth import get_current_user


def benchmark(count):
    schedules = load_schedules()
    now = [0.0]
    runtime = Runtime(clock=lambda: now[0])
    request = SimulationInput(origin_station='UDRPU', gateway='DELGW', simulation_date=date(2026,9,29),
                              shipment_ready_datetime=datetime(2026,9,29,18), speed=600)
    gc.collect(); tracemalloc.start(); before = tracemalloc.get_traced_memory()[0]
    sims = [runtime.create(1, request, schedules) for _ in range(count)]
    now[0] = 40; runtime.tick()
    latencies=[]
    for s in sims:
        start=time.perf_counter(); inject(s,DisruptionInput()); latencies.append((time.perf_counter()-start)*1000)
    iterations=40; started=time.perf_counter(); baseline=runtime.updates
    for _ in range(iterations):
        now[0]+=.25; runtime.tick()
    elapsed=time.perf_counter()-started
    updates=runtime.updates-baseline
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    old_runtime=routes.runtime;routes.runtime=runtime
    api_times=[];http_errors=0
    try:
        with TestClient(app) as client:
            for i in range(20):
                start=time.perf_counter(); response=client.get(f'/fedex/simulations/{sims[i%count].id}')
                api_times.append((time.perf_counter()-start)*1000)
                http_errors+=response.status_code!=200
    finally: routes.runtime=old_runtime
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    return {'simulations':count,'telemetry_snapshots_per_second':round(updates/elapsed),
            'mean_event_latency_ms':round(statistics.mean(latencies),3),'mean_asgi_get_latency_ms':round(statistics.mean(api_times),3),
            'errors':runtime.errors+http_errors,'dropped_updates':count*iterations-updates,
            'dropped_events':count-sum(len(s.events) for s in sims),
            'dropped_simulations':count-len(runtime.entries),
            'retained_growth_mb':round((current-before)/1e6,3),'peak_growth_mb':round((peak-before)/1e6,3),
            'scope':'In-process snapshots and TestClient ASGI; excludes network fan-out and browser rendering'}


if __name__=='__main__':
    logging.getLogger('httpx').setLevel(logging.WARNING)
    for count in (10,50,100): print(json.dumps(benchmark(count)))
