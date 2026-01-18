"""
Location function tools for LeLamp

This module contains location-related function tools including:
- Setting location by city name (with geocoding)
- Getting current location
"""

import logging
import httpx
from lelamp.service.agent.tools import Tool


class LocationFunctions:
    """Mixin class providing location function tools"""

    @Tool.register_tool
    async def set_location(self, city: str) -> str:
        """
        Set the user's location by city name. Use this when someone asks you to change
        or set their location, like "set my location to San Francisco" or "I'm in Tokyo now".

        This will:
        - Search for the city using geocoding
        - Update the timezone automatically
        - Enable weather and time-based features for that location

        Examples:
        - "Set my location to San Francisco"
        - "I moved to London"
        - "Change my city to New York"
        - "I'm in Paris now"

        Args:
            city: The city name to search for (e.g., "San Francisco", "Tokyo", "London")

        Returns:
            Confirmation message with location details or error
        """
        from lelamp.globals import CONFIG
        from api.deps import load_config, save_config

        print(f"LeLamp: set_location called with city={city}")

        if not city or len(city) < 2:
            return "Please provide a city name with at least 2 characters."

        try:
            # Search for the city using Nominatim geocoding
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": city,
                        "format": "json",
                        "addressdetails": 1,
                        "limit": 1,
                    },
                    headers={
                        "User-Agent": "LeLamp-RobotLamp/1.0 (https://github.com/boxbots/lelamp; lelamp@boxbots.io)"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()

            if not data:
                return f"Could not find a location matching '{city}'. Please try a different city name or be more specific (e.g., 'San Francisco, California')."

            # Extract location data
            item = data[0]
            address = item.get("address", {})
            city_name = (
                address.get("city") or
                address.get("town") or
                address.get("village") or
                address.get("municipality") or
                item.get("name", city)
            )
            region = address.get("state") or address.get("province") or ""
            country = address.get("country", "")
            lat = float(item.get("lat", 0))
            lon = float(item.get("lon", 0))

            # Determine timezone from coordinates
            timezone = "UTC"
            try:
                from timezonefinder import TimezoneFinder
                tf = TimezoneFinder()
                tz = tf.timezone_at(lat=lat, lng=lon)
                if tz:
                    timezone = tz
            except ImportError:
                logging.warning("timezonefinder not installed, using UTC")

            # Update config
            config = load_config()
            config['location'] = {
                'city': city_name,
                'region': region,
                'country': country,
                'timezone': timezone,
                'lat': lat,
                'lon': lon
            }
            save_config(config)

            # Update globals
            CONFIG['location'] = config['location']

            # Try to update system timezone
            try:
                import subprocess
                subprocess.run(
                    ['sudo', 'timedatectl', 'set-timezone', timezone],
                    capture_output=True,
                    timeout=5
                )
            except Exception as e:
                logging.warning(f"Could not update system timezone: {e}")

            # Build response
            location_parts = [city_name]
            if region:
                location_parts.append(region)
            if country:
                location_parts.append(country)
            location_str = ", ".join(location_parts)

            return f"Location set to {location_str}. Timezone: {timezone}. Weather and time features will now use this location."

        except httpx.TimeoutException:
            return "Location search timed out. Please try again."
        except Exception as e:
            logging.error(f"Error setting location: {e}")
            return f"Error setting location: {str(e)}"

    @Tool.register_tool
    async def get_location(self) -> str:
        """
        Get the current configured location. Use this when someone asks where their
        location is set to, or to check the current timezone.

        Examples:
        - "What's my location set to?"
        - "Where am I?"
        - "What timezone am I in?"

        Returns:
            Current location information
        """
        from lelamp.globals import CONFIG

        print("LeLamp: get_location called")

        try:
            location = CONFIG.get("location", {})
            city = location.get("city", "")
            region = location.get("region", "")
            country = location.get("country", "")
            timezone = location.get("timezone", "UTC")
            lat = location.get("lat", 0)
            lon = location.get("lon", 0)

            if not city:
                return "No location is currently set. You can say 'set my location to [city name]' to configure it."

            # Build location string
            location_parts = [city]
            if region:
                location_parts.append(region)
            if country:
                location_parts.append(country)
            location_str = ", ".join(location_parts)

            if lat != 0 and lon != 0:
                return f"Your location is set to {location_str}. Timezone: {timezone}. Coordinates: {lat:.4f}, {lon:.4f}"
            else:
                return f"Your location is set to {location_str}. Timezone: {timezone}. Note: Coordinates are not configured, which may affect weather accuracy."

        except Exception as e:
            logging.error(f"Error getting location: {e}")
            return f"Error getting location: {str(e)}"
