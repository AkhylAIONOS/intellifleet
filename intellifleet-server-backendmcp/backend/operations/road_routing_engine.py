from __future__ import annotations

import math
import os
import hashlib
import json
import tempfile
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Tuple

import requests


OSRM_BASE_URL = os.getenv(
    "OSRM_BASE_URL",
    "https://router.project-osrm.org",
).rstrip("/")


@dataclass(frozen=True)
class RoadPoint:
    lat: float
    lon: float


@dataclass
class RoadRoute:
    origin: RoadPoint
    destination: RoadPoint
    snapped_origin: RoadPoint
    snapped_destination: RoadPoint

    distance_km: float
    duration_minutes: float

    # IMPORTANT:
    # Internal format is always [lat, lon]
    geometry: List[Tuple[float, float]]

    source: str = "OpenStreetMap / OSRM"
    simulated: bool = True
    route_id: str = ""
    optimization: str = "FASTEST"
    profile: str = "driving"


class RoadRoutingError(RuntimeError):
    def __init__(self, message="Road routing is unavailable. Check the routing endpoint and retry.", code="ROAD_ROUTE_UNAVAILABLE"):
        self.code = code
        super().__init__(f"{code}: {message}")


class RoadRoutingEngine:
    """OSRM's configured driving profile supplies map geometry, not fleet pricing.

    Only FASTEST is supported by this provider. Shortest/cheapest and arbitrary
    segment avoidance are deliberately rejected, not relabeled fastest routes.
    """
    def __init__(self, base_url=None, timeout=None, cache_dir=None, retries=1, min_interval=None):
        self.base_url = (base_url or os.getenv('OSRM_BASE_URL', OSRM_BASE_URL)).rstrip('/')
        self.timeout = float(timeout or os.getenv('OSRM_TIMEOUT_SECONDS', '15'))
        self.cache_dir = Path(cache_dir or os.getenv('OSRM_CACHE_DIR', str(Path(tempfile.gettempdir())/'unifleet-road-routes')))
        self.cache_ttl = float(os.getenv('OSRM_CACHE_TTL_SECONDS', '86400'))
        self.max_snap_m = float(os.getenv('OSRM_MAX_SNAP_METERS', '5000'))
        self.min_interval = float(os.getenv('OSRM_MIN_REQUEST_INTERVAL', '1')) if min_interval is None else min_interval
        self.retries = retries
        self._lock = threading.RLock()
        self._last_request = 0.0

    @lru_cache(maxsize=512)
    def get_route(self, origin_lat, origin_lon, destination_lat, destination_lon,
                  optimization='FASTEST', profile='driving', avoid=()) -> RoadRoute:
        if optimization != 'FASTEST':
            raise RoadRoutingError('This OSRM profile supports FASTEST only. SHORTEST/CHEAPEST need a provider with those objectives and verified costing inputs.', 'ROAD_OPTIMIZATION_UNSUPPORTED')
        if profile != 'driving' or avoid:
            raise RoadRoutingError('The configured provider does not support this profile or blocked-segment avoidance. No reroute was applied.', 'ROAD_AVOIDANCE_UNSUPPORTED')
        for lat, lon in ((origin_lat, origin_lon), (destination_lat, destination_lon)):
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise RoadRoutingError('Valid existing origin and destination coordinates are required.')
        key = hashlib.sha256(json.dumps([2,self.base_url,origin_lat,origin_lon,destination_lat,destination_lon,profile,optimization,avoid,self.max_snap_m]).encode()).hexdigest()
        cache_file = self.cache_dir / (key + '.json')
        # Single flight + paced public-demo requests; no network traffic in telemetry ticks.
        with self._lock:
            try:
                cached = json.loads(cache_file.read_text())
                if time.time()-cached['saved_at'] < self.cache_ttl:
                    return self._parse(cached['payload'], origin_lat, origin_lon, destination_lat, destination_lon, key)
            except (OSError, ValueError, KeyError, TypeError, RoadRoutingError):
                pass
            coordinates = f'{origin_lon},{origin_lat};{destination_lon},{destination_lat}'
            payload = None
            for attempt in range(self.retries+1):
                time.sleep(max(0, self.min_interval-(time.monotonic()-self._last_request)))
                self._last_request = time.monotonic()
                try:
                    response = requests.get(f'{self.base_url}/route/v1/{profile}/{coordinates}',
                        params={'overview':'full','geometries':'geojson','steps':'true','alternatives':'false',
                                'radiuses':f'{self.max_snap_m};{self.max_snap_m}'},
                        headers={'User-Agent':'UniFleet-local-road-simulation/1.0'}, timeout=self.timeout)
                    response.raise_for_status()
                    payload = response.json()
                    break
                except (requests.RequestException, ValueError) as exc:
                    if attempt == self.retries:
                        raise RoadRoutingError() from exc
            route = self._parse(payload, origin_lat, origin_lon, destination_lat, destination_lon, key)
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                temporary = cache_file.with_suffix('.tmp')
                temporary.write_text(json.dumps({'saved_at':time.time(),'payload':payload}, separators=(',',':')))
                temporary.replace(cache_file)
            except OSError:
                pass  # The in-memory cache still works when disk caching is unavailable.
            return route

    def _parse(self, payload, origin_lat, origin_lon, destination_lat, destination_lon, key):
        try:
            if payload.get('code') != 'Ok': raise ValueError('No route')
            raw = payload['routes'][0]
            # The public profile cannot exclude ferries; reject ferry routes rather than
            # depicting a truck driving over water. No fake avoidance is attempted.
            steps = [s for leg in raw['legs'] for s in leg['steps']]
            if not steps or any(s.get('mode') != 'driving' for s in steps):
                raise RoadRoutingError('No road-only route was returned (ferry/non-driving segment). Use a provider supporting explicit avoidance.')
            geometry = [(float(lat),float(lon)) for lon,lat in raw['geometry']['coordinates']]
            if len(geometry)<2 or any(not(math.isfinite(a) and math.isfinite(b) and -90<=a<=90 and -180<=b<=180) for a,b in geometry): raise ValueError('Invalid geometry')
            distance, duration = float(raw['distance'])/1000, float(raw['duration'])/60
            if not (math.isfinite(distance) and math.isfinite(duration) and distance>0 and duration>0): raise ValueError('Invalid metrics')
            waypoints = payload['waypoints']
            if len(waypoints)!=2: raise ValueError('Missing snap positions')
            snapped = [RoadPoint(float(w['location'][1]),float(w['location'][0])) for w in waypoints]
            if any(not (math.isfinite(p.lat) and math.isfinite(p.lon) and -90 <= p.lat <= 90 and -180 <= p.lon <= 180) for p in snapped):
                raise ValueError('Invalid snap positions')
            originals = [RoadPoint(origin_lat,origin_lon),RoadPoint(destination_lat,destination_lon)]
            for original, snap, endpoint in zip(originals,snapped,(geometry[0],geometry[-1])):
                if haversine_km((original.lat,original.lon),(snap.lat,snap.lon))*1000>self.max_snap_m: raise ValueError('Snap too far')
                if haversine_km(endpoint,(snap.lat,snap.lon))>.03: raise ValueError('Geometry and snap disagree')
            return RoadRoute(originals[0],originals[1],snapped[0],snapped[1],distance,duration,geometry,route_id=key)
        except RoadRoutingError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            raise RoadRoutingError('No valid drivable road route was returned. Check coordinates or retry the routing provider.') from exc


road_routing_engine = RoadRoutingEngine()


# -----------------------------------------------------------
# Geometry helpers used by the telemetry simulator
# -----------------------------------------------------------

EARTH_RADIUS_KM = 6371.0088


def haversine_km(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
) -> float:
    lat1, lon1 = p1
    lat2, lon2 = p2

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(d_lambda / 2) ** 2
    )

    return (
        2
        * EARTH_RADIUS_KM
        * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
    )


def point_along_route(
    geometry: List[Tuple[float, float]],
    progress: float,
) -> Tuple[float, float]:
    """
    Return a coordinate ON the road polyline.

    progress:
        0.0 = route start
        1.0 = route destination
    """

    if not geometry:
        raise ValueError("Route geometry cannot be empty.")

    if len(geometry) == 1:
        return geometry[0]

    progress = max(0.0, min(1.0, progress))

    if progress == 0:
        return geometry[0]

    if progress == 1:
        return geometry[-1]

    segment_lengths = []
    total_distance = 0.0

    for i in range(len(geometry) - 1):
        distance = haversine_km(
            geometry[i],
            geometry[i + 1],
        )

        segment_lengths.append(distance)
        total_distance += distance

    if total_distance <= 0:
        return geometry[0]

    target_distance = total_distance * progress

    travelled = 0.0

    for index, segment_distance in enumerate(segment_lengths):
        next_travelled = travelled + segment_distance

        if target_distance <= next_travelled:
            if segment_distance <= 0:
                return geometry[index]

            local_progress = (
                (target_distance - travelled)
                / segment_distance
            )

            lat1, lon1 = geometry[index]
            lat2, lon2 = geometry[index + 1]

            lat = lat1 + (lat2 - lat1) * local_progress
            lon = lon1 + (lon2 - lon1) * local_progress

            return lat, lon

        travelled = next_travelled

    return geometry[-1]


def telemetry_position(
    route: RoadRoute,
    progress_percent: float,
):
    """
    Convenience function for the existing UniFleet simulator.

    Example:
        progress_percent = 25
        -> returns road position at 25% of route.
    """

    progress = max(
        0.0,
        min(100.0, progress_percent),
    ) / 100.0

    lat, lon = point_along_route(
        route.geometry,
        progress,
    )

    return {
        "latitude": lat,
        "longitude": lon,
        "route_progress": progress_percent,
        "distance_km": route.distance_km,
        "duration_minutes": route.duration_minutes,
        "route_source": route.source,
        "simulated": True,
    }
