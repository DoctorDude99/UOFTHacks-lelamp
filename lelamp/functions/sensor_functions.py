"""
Sensor and data function tools for LeLamp

This module contains all sensor and environmental data function tools including:
- Date/time queries
- Weather data
- News headlines
- Face tracking and vision
"""

import logging
from datetime import datetime
import aiohttp
import pytz
import feedparser
from lelamp.service.agent.tools import Tool


class SensorFunctions:
    """Mixin class providing sensor and data function tools"""

    @Tool.register_tool
    async def get_current_datetime(self) -> str:
        """
        Get the current local date and time. Use this when someone asks what time it is,
        what day it is, or needs any time-related information. Perfect for scheduling,
        time-aware greetings (good morning/evening), or answering "what's the date today?"

        Returns:
            Current local date, time, and day of week.
        """
        from lelamp.globals import CONFIG

        print("LeLamp: get_current_datetime function called")
        try:
            location = CONFIG.get("location", {})
            tz_name = location.get("timezone", "UTC")
            tz = pytz.timezone(tz_name)
            now = datetime.now(tz)

            result = (
                f"Current time: {now.strftime('%I:%M %p')} "
                f"on {now.strftime('%A, %B %d, %Y')} "
                f"({location.get('city', 'Unknown')}, {location.get('region', '')})"
            )
            return result
        except Exception as e:
            return f"Error getting time: {str(e)}"

    @Tool.register_tool
    async def get_ip_address(self) -> str:
        """
        Get your network IP addresses! Use this when someone asks for your IP address,
        network info, or connection details. Perfect for network troubleshooting, remote
        access setup, or when someone needs to connect to you.

        Returns both:
        - Local IP: Your address on the local network (e.g., 192.168.10.177)
        - WAN IP: Your public internet address visible to the outside world

        Use when someone asks: "what's your IP?", "what's my IP address?",
        "how do I connect to you?", "network info", etc.

        Returns:
            Local and WAN IP addresses with clear labels
        """
        import socket

        print("LeLamp: get_ip_address function called")
        result_lines = []

        # Get local IP address
        try:
            # Create a socket connection to determine local IP
            # We connect to an external address (Google DNS) but don't actually send data
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            try:
                # Connect to Google's DNS server (doesn't actually send packets)
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
                result_lines.append(f"📡 Local IP: {local_ip}")
            except Exception:
                local_ip = "Unable to determine"
                result_lines.append(f"📡 Local IP: {local_ip}")
            finally:
                s.close()
        except Exception as e:
            result_lines.append(f"📡 Local IP: Error - {str(e)}")

        # Get WAN/public IP address
        try:
            async with aiohttp.ClientSession() as session:
                # Use ipify.org API to get public IP
                async with session.get('https://api.ipify.org?format=text', timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        wan_ip = await response.text()
                        result_lines.append(f"🌐 WAN IP: {wan_ip.strip()}")
                    else:
                        result_lines.append(f"🌐 WAN IP: Unable to determine (API error)")
        except aiohttp.ClientError:
            result_lines.append(f"🌐 WAN IP: Unable to determine (no internet connection)")
        except Exception as e:
            result_lines.append(f"🌐 WAN IP: Error - {str(e)}")

        return "\n".join(result_lines)

    @Tool.register_tool
    async def get_weather(self) -> str:
        """
        Get the current weather conditions for your location. Use this when someone asks
        about the weather, temperature, if they need a jacket, umbrella, or any weather-related
        questions. Great for helping people plan their day!

        Returns:
            Current weather conditions including temperature, description, and humidity.
        """
        from lelamp.globals import CONFIG

        print("LeLamp: get_weather function called")
        try:
            location = CONFIG.get("location", {})
            lat = location.get("lat")
            lon = location.get("lon")
            city = location.get("city", "Unknown")

            if not lat or not lon:
                return "Weather unavailable - location coordinates not configured in config.yaml"

            # Open-Meteo API - completely free, no API key needed
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
                f"&timezone=auto"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        return f"Weather API error: {response.status}"
                    data = await response.json()

            current = data["current"]
            temp = current["temperature_2m"]
            feels_like = current["apparent_temperature"]
            humidity = current["relative_humidity_2m"]
            wind = current["wind_speed_10m"]
            weather_code = current["weather_code"]

            # Weather code to description
            weather_descriptions = {
                0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
                45: "foggy", 48: "depositing rime fog",
                51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
                61: "slight rain", 63: "moderate rain", 65: "heavy rain",
                71: "slight snow", 73: "moderate snow", 75: "heavy snow",
                80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
                95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
            }
            description = weather_descriptions.get(weather_code, "unknown conditions")

            result = (
                f"Weather in {city}: {description.capitalize()}. "
                f"Temperature: {temp:.1f}°C (feels like {feels_like:.1f}°C). "
                f"Humidity: {humidity}%. Wind: {wind} km/h."
            )
            return result
        except Exception as e:
            return f"Error getting weather: {str(e)}"

    @Tool.register_tool
    async def get_news(self, topic: str = "top") -> str:
        """
        Get the latest news headlines. Use this when someone asks about current events,
        what's happening in the world, or wants to know the news. You can search for
        specific topics or get top headlines.

        Args:
            topic: What news to get - "top" for top headlines, or a specific topic like
                   "technology", "sports", "business", "canada", "local"

        Returns:
            Latest news headlines with brief summaries.
        """
        print(f"LeLamp: get_news function called with topic: {topic}")
        try:
            # RSS feeds that don't require API keys
            feeds = {
                "top": "https://news.google.com/rss?hl=en-CA&gl=CA&ceid=CA:en",
                "canada": "https://news.google.com/rss/topics/CAAqJQgKIh9DQkFTRVFvSUwyMHZNRE55YXpBU0JXVnVMVU5CS0FBUAE?hl=en-CA&gl=CA&ceid=CA:en",
                "technology": "https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRGRqTVhZU0JXVnVMVU5CS2dBUQFRAE?hl=en-CA&gl=CA&ceid=CA:en",
                "business": "https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JXVnVMVU5CS2dBUUFRAE?hl=en-CA&gl=CA&ceid=CA:en",
                "sports": "https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRFp1ZEdvU0JXVnVMVU5CS2dBUQFRAE?hl=en-CA&gl=CA&ceid=CA:en",
                "local": "https://news.google.com/rss/search?q=Waterloo+Ontario&hl=en-CA&gl=CA&ceid=CA:en",
            }

            feed_url = feeds.get(topic.lower(), feeds["top"])
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                return f"No news found for topic: {topic}"

            # Get top 5 headlines
            headlines = []
            for entry in feed.entries[:5]:
                title = entry.get("title", "No title")
                headlines.append(f"• {title}")

            result = f"Latest {topic} news:\n" + "\n".join(headlines)
            return result
        except Exception as e:
            return f"Error getting news: {str(e)}"

    @Tool.register_tool
    async def get_face_tracking(self) -> str:
        """
        Detect if someone is looking at you and where they are! Use this to see if
        a person's face is visible, their position relative to you, and how close they are.
        Perfect for: checking if someone is paying attention, tracking where people are,
        responding to their presence, or adjusting your behavior based on if you're being watched.

        Returns:
            Face detection status with position (left/right, up/down) and distance info.
            Position values: -1.0 (far left/top) to +1.0 (far right/bottom), 0.0 is center.
            Size: 0.0 to 1.0, where larger values mean the person is closer to you.
        """
        from lelamp.globals import vision_service

        print("LeLamp: get_face_tracking called")
        try:
            if vision_service is None:
                return "Face tracking is not enabled. Enable it in config.yaml under 'face_tracking'."

            data = vision_service.get_face_data()

            if data is None or not data.detected:
                return "No face detected - I don't see anyone right now."

            pos_x, pos_y = data.position
            size = data.size

            # Describe position
            if abs(pos_x) < 0.2:
                x_desc = "centered"
            elif pos_x > 0:
                x_desc = f"to my right ({pos_x:.2f})"
            else:
                x_desc = f"to my left ({pos_x:.2f})"

            if abs(pos_y) < 0.2:
                y_desc = "at eye level"
            elif pos_y > 0:
                y_desc = f"below me ({pos_y:.2f})"
            else:
                y_desc = f"above me ({pos_y:.2f})"

            # Describe distance
            if size > 0.3:
                dist_desc = "very close"
            elif size > 0.15:
                dist_desc = "close"
            elif size > 0.08:
                dist_desc = "medium distance"
            else:
                dist_desc = "far away"

            response = f"I see a face! Position: {x_desc}, {y_desc}. Distance: {dist_desc} (size: {size:.3f})"

            # Add head pose info if available (MediaPipe)
            if hasattr(data, 'head_pose') and data.head_pose:
                yaw = data.head_pose['yaw']
                pitch = data.head_pose['pitch']
                roll = data.head_pose['roll']
                response += f"\nHead angles: yaw={yaw:.1f}°, pitch={pitch:.1f}°, roll={roll:.1f}°"

            return response

        except Exception as e:
            return f"Error getting face tracking data: {str(e)}"

    @Tool.register_tool
    async def enable_face_tracking_mode(self) -> str:
        """
        Enable face tracking mode - I'll automatically follow faces with my movement!

        When enabled, I'll continuously track detected faces and move to keep them centered
        in my view. I'll use base_yaw (left/right) and base_pitch (up/down) to follow you
        as you move around. Perfect for maintaining eye contact during conversations or
        following someone around the room.

        Use this when someone says:
        - "Track my face"
        - "Follow me"
        - "Keep me in view"
        - "Enable face tracking"

        Returns:
            Confirmation message
        """
        from lelamp.globals import CONFIG, vision_service

        print("LeLamp: enable_face_tracking_mode called")
        try:
            if vision_service is None:
                return "Face tracking is not available. Enable it in config.yaml under 'face_tracking'."

            if self.animation_service.is_face_tracking_mode():
                return "Face tracking mode is already enabled! I'm already following faces."

            # Get motion config with safe defaults
            motion_config = CONFIG.get('face_tracking', {}).get('motion', {})
            motion_scale = motion_config.get('scale', 0.15)
            max_speed = motion_config.get('max_speed', 8.0)
            dead_zone = motion_config.get('dead_zone', 0.08)
            smoothing = motion_config.get('smoothing', 0.85)

            # Smoothing state
            smoothed_yaw = 0.0
            smoothed_pitch = 0.0

            # Create tracking callback that sends targets to animation service
            def track_face(face_data):
                """Callback to send tracking targets to animation service"""
                nonlocal smoothed_yaw, smoothed_pitch
                try:
                    pos_x, pos_y = face_data.position

                    # Dead zone - face is close enough to center
                    if abs(pos_x) < dead_zone and abs(pos_y) < dead_zone:
                        self.animation_service.update_face_tracking_target(0, 0)
                        return

                    # Convert position to adjustment
                    yaw_raw = pos_x * 25.0
                    pitch_raw = -pos_y * 20.0

                    # Apply smoothing
                    smoothed_yaw = smoothing * smoothed_yaw + (1 - smoothing) * yaw_raw
                    smoothed_pitch = smoothing * smoothed_pitch + (1 - smoothing) * pitch_raw

                    # Calculate adjustment (clamped to max_speed)
                    yaw_adj = max(-max_speed, min(max_speed, smoothed_yaw * motion_scale))
                    pitch_adj = max(-max_speed, min(max_speed, smoothed_pitch * motion_scale))

                    # Send to animation service
                    self.animation_service.update_face_tracking_target(yaw_adj, pitch_adj)

                except Exception as e:
                    logging.error(f"Error in face tracking callback: {e}")

            # Enable face tracking mode on animation service
            self.animation_service.set_face_tracking_mode(True)

            # Enable vision tracking with callback
            vision_service.enable_tracking_mode(track_face)

            return "Face tracking mode enabled! I'll now follow faces I see. Tell me to 'stop tracking' when you want me to stop."

        except Exception as e:
            return f"Error enabling face tracking mode: {str(e)}"

    @Tool.register_tool
    async def disable_face_tracking_mode(self) -> str:
        """
        Disable face tracking mode - I'll stop following faces automatically.

        Use this when someone says:
        - "Stop tracking"
        - "Stop following me"
        - "Disable face tracking"
        - "Stop looking at me"

        Returns:
            Confirmation message
        """
        from lelamp.globals import vision_service

        print("LeLamp: disable_face_tracking_mode called")
        try:
            if vision_service is None:
                return "Face tracking is not available."

            if not self.animation_service.is_face_tracking_mode():
                return "Face tracking mode is already disabled."

            # Disable on both services
            vision_service.disable_tracking_mode()
            self.animation_service.set_face_tracking_mode(False)

            # Return to idle position
            self.animation_service.dispatch("play", "idle")

            return "Face tracking mode disabled. I'll stop following faces now."

        except Exception as e:
            return f"Error disabling face tracking mode: {str(e)}"

    @Tool.register_tool
    async def look_at_face(self) -> str:
        """
        Look at the nearest detected face - a one-time adjustment to face whoever is there.

        This is different from face tracking mode - it's a single movement to look at
        whoever is currently visible, without continuously following them. Good for
        acknowledging someone's presence or turning to face them when they start talking.

        Use this when someone says:
        - "Look at me"
        - "Turn to face me"
        - "Look this way"
        - "Over here"
        - "Hey, look"

        Returns:
            Confirmation message
        """
        from lelamp.globals import vision_service

        print("LeLamp: look_at_face called")
        try:
            if vision_service is None:
                return "Vision service is not available."

            # Get current face data
            face_data = vision_service.get_face_data()

            if face_data is None or not face_data.detected:
                return "I don't see anyone right now. Make sure you're in front of my camera!"

            pos_x, pos_y = face_data.position

            # Check if already looking at face (within dead zone)
            if abs(pos_x) < 0.1 and abs(pos_y) < 0.1:
                return "I'm already looking at you!"

            # Calculate how much to move
            # pos_x/pos_y are normalized -1 to 1, convert to degrees
            yaw_adjustment = pos_x * 30.0  # Max ~30 degrees
            pitch_adjustment = -pos_y * 25.0  # Invert Y, max ~25 degrees

            # Read current position and calculate target
            try:
                current_pos = self.animation_service.robot.bus.sync_read("Present_Position")
                current_yaw = current_pos.get('base_yaw', 0.0)
                current_pitch = current_pos.get('base_pitch', 0.0)

                new_yaw = max(-90, min(90, current_yaw + yaw_adjustment))
                new_pitch = max(-45, min(45, current_pitch + pitch_adjustment))

                # Send action through animation service
                action = {
                    'base_yaw.pos': new_yaw,
                    'base_pitch.pos': new_pitch
                }

                with self.animation_service._bus_lock:
                    self.animation_service.robot.send_action(action)

                return "There you are! I see you now."

            except Exception as e:
                logging.error(f"Error moving to face: {e}")
                return f"I tried to look at you but had trouble moving: {str(e)}"

        except Exception as e:
            return f"Error looking at face: {str(e)}"
