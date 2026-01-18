"""
Location configuration endpoints.

Handles location and timezone settings with geocoding support.
"""

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
import subprocess
import logging

from api.deps import load_config, save_config

router = APIRouter()


class GeocodingResult(BaseModel):
    """Result from geocoding search."""
    city: str
    region: str
    country: str
    lat: float
    lon: float
    display_name: str


@router.get("/search")
async def search_city(q: str) -> dict:
    """
    Search for a city using OpenStreetMap Nominatim geocoding.

    Args:
        q: Search query (city name)

    Returns:
        List of matching locations with coordinates
    """
    if not q or len(q) < 2:
        return {"success": False, "error": "Search query too short", "results": []}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "json",
                    "addressdetails": 1,
                    "limit": 5,
                },
                headers={
                    "User-Agent": "LeLamp-RobotLamp/1.0 (https://github.com/boxbots/lelamp; lelamp@boxbots.io)"
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data:
                address = item.get("address", {})
                city = (
                    address.get("city") or
                    address.get("town") or
                    address.get("village") or
                    address.get("municipality") or
                    item.get("name", "")
                )
                region = address.get("state") or address.get("province") or ""
                country = address.get("country", "")

                results.append({
                    "city": city,
                    "region": region,
                    "country": country,
                    "lat": float(item.get("lat", 0)),
                    "lon": float(item.get("lon", 0)),
                    "display_name": item.get("display_name", ""),
                })

            return {"success": True, "results": results}

    except httpx.TimeoutException:
        return {"success": False, "error": "Search timed out", "results": []}
    except Exception as e:
        logging.error(f"Geocoding error: {e}")
        return {"success": False, "error": str(e), "results": []}


class LocationConfig(BaseModel):
    city: str
    region: Optional[str] = ""
    country: Optional[str] = ""
    lat: float = 0.0
    lon: float = 0.0


@router.get("/")
async def get_location():
    """Get current location configuration."""
    try:
        config = load_config()
        location = config.get('location', {})
        return {
            "success": True,
            "city": location.get('city', ''),
            "region": location.get('region', ''),
            "country": location.get('country', ''),
            "timezone": location.get('timezone', 'UTC'),
            "lat": location.get('lat', 0.0),
            "lon": location.get('lon', 0.0)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/")
async def save_location(data: LocationConfig):
    """Save location configuration."""
    try:
        if not data.city:
            return {"success": False, "error": "City is required"}

        # Try to determine timezone from coordinates
        timezone = "UTC"
        try:
            from timezonefinder import TimezoneFinder
            tf = TimezoneFinder()
            tz = tf.timezone_at(lat=data.lat, lng=data.lon)
            if tz:
                timezone = tz
        except ImportError:
            pass  # timezonefinder not installed, use UTC

        # Update config
        config = load_config()
        config['location'] = {
            'city': data.city,
            'region': data.region or '',
            'country': data.country or '',
            'timezone': timezone,
            'lat': data.lat,
            'lon': data.lon
        }

        # Mark location step as complete
        config.setdefault('setup', {})
        config['setup'].setdefault('steps_completed', {})
        config['setup']['steps_completed']['location'] = True

        save_config(config)

        # Try to update system timezone
        system_tz_message = ""
        try:
            result = subprocess.run(
                ['sudo', 'timedatectl', 'set-timezone', timezone],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                system_tz_message = f"System timezone updated to {timezone}"
            else:
                system_tz_message = f"Could not update system timezone: {result.stderr}"
        except Exception as e:
            system_tz_message = f"Could not update system timezone: {str(e)}"

        return {
            "success": True,
            "message": "Location saved",
            "timezone": timezone,
            "system_timezone_update": system_tz_message
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
