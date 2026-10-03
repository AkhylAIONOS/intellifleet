"""Offline synthetic tick/snapshot profile; no DB, route provider or email."""
import time
from datetime import date, datetime
from backend.fedex.models import Schedule, SimulationInput
from backend.fedex.simulator import Simulation

s=Schedule(schedule_id='profile',source_sheet='Synthetic profile',source_row=0,origin_city='A',origin_station='A',gateway='B',lane='A-B',run='profile',mode='AIR',source_mode='AIR',service='Synthetic',cutoff_minutes=0,etd_minutes=1,eta_minutes=121,data_source='SYNTHETIC_SCHEDULE',origin_coordinates=(10,70),destination_coordinates=(20,80))
for count in [10,100,500]:
    sims=[Simulation(SimulationInput(origin_station='A',gateway='B',simulation_date=date(2030,1,1),shipment_ready_datetime=datetime.fromisoformat('2030-01-01T00:00:00+05:30')),[s],0) for _ in range(count)]
    start=time.perf_counter()
    for tick in range(1,101):
        for sim in sims:sim.advance(tick*.25)
    elapsed=time.perf_counter()-start
    print(f'{count} movements: {elapsed*10:.3f} ms/tick mean; {count*100/elapsed:.0f} snapshots/second')
