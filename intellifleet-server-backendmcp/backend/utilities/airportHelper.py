from backend.config.config import settings
from backend.config.logger import logger
import requests
import math

GOOGLE_API_KEY = settings.GOOGLE_MAPS_API_KEY

EARTH_RADIUS_KM = 6371
CRUISE_SPEED_KMPH = 600
TAKEOFF_LANDING_OVERHEAD = 0.75 


def fetch_nearest_airport(lat, lng, radius_m=50000):
    url = "https://places.googleapis.com/v1/places:searchNearby"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.location,"
            "places.formattedAddress"
        )
    }

    payload = {
        "includedTypes": ["airport"],
        "maxResultCount": 1,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_m
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()  # Raise HTTPError if status != 200
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
    except ValueError as e:
        print(f"JSON decode error: {e}")
        return None

    try:
        places = data.get("places", [])
        if not places:
            return None

        airport = places[0]
        airport_lat = airport["location"]["latitude"]
        airport_lng = airport["location"]["longitude"]

        distance_km = haversine_distance_km(lat, lng, airport_lat, airport_lng)

        return {
            "airport_name": airport["displayName"]["text"],
            "airport_address": airport.get("formattedAddress"),
            "latitude": airport_lat,
            "longitude": airport_lng,
            "distance_km": distance_km
        }
    except KeyError as e:
        print(f"Missing expected key in API response: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def haversine_distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(EARTH_RADIUS_KM * c, 2)


def estimate_flight_duration(distance_km):
    cruise_time = distance_km / CRUISE_SPEED_KMPH
    return round(cruise_time + TAKEOFF_LANDING_OVERHEAD, 2)

