"""Bounded, single-process ephemeral demo runtime. No database or Redis writes."""
import asyncio
import time
from dataclasses import dataclass

from .disruptions import maybe_seeded_event
from .simulator import Simulation


@dataclass
class Entry:
    owner: int
    simulation: Simulation
    created: float


class Runtime:
    def __init__(self, clock=time.monotonic, limit=500, ttl=21600):
        self.clock, self.limit, self.ttl = clock, limit, ttl
        self.entries = {}
        self.errors = 0
        self.updates = 0

    def cleanup(self):
        now = self.clock()
        for key, entry in list(self.entries.items()):
            if now-entry.created > self.ttl:
                del self.entries[key]

    def create(self, owner, request, schedules, road_waypoints=None):
        self.cleanup()
        if len(self.entries) >= self.limit:
            raise ValueError('Simulation limit reached; reset old simulations')
        s = Simulation(request, schedules, self.clock(), road_waypoints=road_waypoints)
        s.last_wall = self.clock()  # Route calculation latency must not advance the simulation clock.
        self.entries[s.id] = Entry(owner, s, self.clock())
        return s

    def get(self, owner, simulation_id):
        self.cleanup()
        entry = self.entries.get(simulation_id)
        if not entry or entry.owner != owner:
            raise KeyError('Simulation not found or expired')
        entry.simulation.advance(self.clock())
        return entry.simulation

    def remove(self, owner, simulation_id):
        self.get(owner, simulation_id)
        del self.entries[simulation_id]

    def tick(self):
        self.cleanup()
        for entry in list(self.entries.values()):
            try:
                entry.simulation.advance(self.clock())
                maybe_seeded_event(entry.simulation)
                self.updates += 1
            except Exception:
                self.errors += 1
                entry.simulation.stopped = True

    async def run(self):
        while True:
            self.tick()
            await asyncio.sleep(.25)


runtime = Runtime()
