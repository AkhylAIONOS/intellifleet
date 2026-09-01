import requests
from backend.config.config import settings
from backend.config.logger import logger

def geocode_address(address: str):

    if not settings.GOOGLE_MAPS_API_KEY:
        logger.error("GOOGLE_MAPS_API_KEY is not configured")
        return None, None

    try:
        clean_address = address.strip()
        logger.info(f"Geocoding address: {clean_address}")

        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": clean_address,
            "key": settings.GOOGLE_MAPS_API_KEY
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == "OK" and data.get("results"):
            location = data["results"][0]["geometry"]["location"]
            latitude = location["lat"]
            longitude = location["lng"]
            return latitude, longitude

        logger.warning(f"Geocode failed for address: {clean_address} | Status: {data.get('status')}")
        return None, None

    except Exception as e:
        logger.error(f"Error in geocoding {address}: {e}")
        return None, None
