"""
Dashboard services endpoints.

Provides enable/disable functionality for configurable services.
Now with live start/stop - changes take effect immediately without restart.
"""

import asyncio
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from api.deps import load_config, save_config, get_animation_service, get_lelamp_agent
import lelamp.globals as g

router = APIRouter()


# Services that can be toggled via config.yaml
# Maps service_key to the config path (dot notation)
CONFIGURABLE_SERVICES = {
    "motors": "motors.enabled",
    "face_tracking": "face_tracking.enabled",
    "motor_tracking": "face_tracking.motor_tracking",
    "vision": "vision.enabled",
    "rgb": "rgb.enabled",
    "audio": "audio.enabled",
    "spotify": "spotify.enabled",
    "music_modifier": "modifiers.music.enabled",
    "breathing_modifier": "modifiers.breathing.enabled",
    "twitch_modifier": "modifiers.twitch.enabled",
    "sway_modifier": "modifiers.sway.enabled",
}


def get_nested_value(config: dict, path: str, default=None):
    """Get a nested value from config using dot notation."""
    keys = path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def set_nested_value(config: dict, path: str, value) -> dict:
    """Set a nested value in config using dot notation."""
    keys = path.split(".")
    current = config
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
    return config


async def _apply_service_change(service: str, enabled: bool) -> str:
    """Apply a service change at runtime. Returns status message."""
    animation = get_animation_service()
    agent = get_lelamp_agent()
    config = load_config()

    try:
        if service == "motors":
            if animation:
                if enabled:
                    # Connect robot if not connected
                    if animation.robot and not animation.robot.is_connected:
                        try:
                            animation.robot.connect(calibrate=False)
                            logging.info("Robot connected")
                        except Exception as e:
                            return f"Failed to connect robot: {e}"

                    # Start the animation service if not running
                    if not animation._running.is_set():
                        animation.start()

                    # Start idle animation
                    animation.dispatch("play", animation.idle_recording)
                    return "Motors connected and started"
                else:
                    # Safety: Play sleep animation first to park lamp safely
                    if animation.robot and animation.robot.is_connected:
                        try:
                            # Apply Gentle preset for safe, slow movement
                            animation.robot.apply_preset("Gentle")
                            logging.info("Applied Gentle preset for safe shutdown")
                        except Exception as e:
                            logging.warning(f"Could not apply Gentle preset: {e}")

                        try:
                            # Play sleep animation to park lamp
                            animation.dispatch("play", "sleep")
                            logging.info("Playing sleep animation before motor shutdown...")
                            # Wait for sleep animation to complete
                            await asyncio.sleep(5.0)
                            logging.info("Sleep animation complete")
                        except Exception as e:
                            logging.warning(f"Could not play sleep animation: {e}")

                        # Now safe to release motors
                        try:
                            animation.robot.bus.disable_torque()
                            animation.robot.bus.disconnect()
                            logging.info("Robot disconnected")
                        except Exception as e:
                            logging.warning(f"Error disconnecting robot: {e}")

                    # Stop animations
                    animation._current_recording = None
                    animation._current_actions = []
                    return "Motors parked safely and disconnected"
            return "Animation service not available"

        elif service == "face_tracking":
            if g.vision_service:
                if enabled:
                    g.vision_service.start()
                    return "Face tracking started"
                else:
                    g.vision_service.stop()
                    # Also disable motor tracking if face tracking is off
                    if animation:
                        animation.set_face_tracking_mode(False)
                    return "Face tracking stopped"
            return "Vision service not available"

        elif service == "motor_tracking":
            if g.vision_service and animation:
                if enabled:
                    # Enable motor tracking - connect vision to animation
                    animation.set_face_tracking_mode(True)
                    g.vision_service.enable_motor_tracking(animation.update_face_position)
                    return "Motor tracking enabled - lamp will follow faces"
                else:
                    # Disable motor tracking
                    animation.set_face_tracking_mode(False)
                    g.vision_service.disable_motor_tracking()
                    return "Motor tracking disabled"
            return "Vision or animation service not available"

        elif service == "vision":
            # Ollama vision service
            if g.ollama_vision_service:
                if enabled:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    g.ollama_vision_service.start(event_loop=loop)
                    return "Vision (Ollama) started"
                else:
                    g.ollama_vision_service.stop()
                    return "Vision (Ollama) stopped"
            return "Ollama vision service not available"

        elif service == "rgb":
            if agent and hasattr(agent, 'rgb_service') and agent.rgb_service:
                if enabled:
                    agent.rgb_service.start()
                    # Start default animation from config
                    rgb_config = config.get("rgb", {})
                    default_anim = rgb_config.get("default_animation", "aura_glow")
                    default_color = tuple(rgb_config.get("default_color", [255, 255, 255]))
                    agent.rgb_service.dispatch("animation", {
                        "name": default_anim,
                        "color": default_color
                    })
                    return f"RGB service started with {default_anim} animation"
                else:
                    # Turn off LEDs and stop service
                    agent.rgb_service.dispatch("solid", (0, 0, 0))
                    import time
                    time.sleep(0.1)  # Give time for LEDs to turn off
                    agent.rgb_service.stop()
                    return "RGB service stopped"
            return "RGB service not available"

        elif service == "audio":
            if agent and hasattr(agent, 'audio_service') and agent.audio_service:
                if enabled:
                    agent.audio_service.start()
                    return "Audio service started"
                else:
                    agent.audio_service.stop()
                    return "Audio service stopped"
            return "Audio service not available"

        elif service == "spotify":
            if agent and hasattr(agent, 'spotify_service') and agent.spotify_service:
                if enabled:
                    # Spotify auto-connects when needed, just mark as enabled
                    return "Spotify enabled"
                else:
                    # Pause and disconnect
                    try:
                        if agent.spotify_service.is_playing():
                            agent.spotify_service.pause()
                    except:
                        pass
                    return "Spotify disabled and paused"
            return "Spotify service not available"

        elif service == "music_modifier":
            if animation:
                if enabled:
                    animation.enable_modifier("music")
                    return "Music modifier enabled"
                else:
                    animation.disable_modifier("music")
                    return "Music modifier disabled"
            return "Animation service not available"

        elif service == "breathing_modifier":
            if animation:
                if enabled:
                    animation.enable_modifier("breathing")
                    return "Breathing modifier enabled"
                else:
                    animation.disable_modifier("breathing")
                    return "Breathing modifier disabled"
            return "Animation service not available"

        elif service == "twitch_modifier":
            if animation:
                if enabled:
                    animation.enable_modifier("twitch")
                    return "Twitch modifier enabled"
                else:
                    animation.disable_modifier("twitch")
                    return "Twitch modifier disabled"
            return "Animation service not available"

        elif service == "sway_modifier":
            if animation:
                if enabled:
                    animation.enable_modifier("sway")
                    return "Sway modifier enabled"
                else:
                    animation.disable_modifier("sway")
                    return "Sway modifier disabled"
            return "Animation service not available"

        return "Unknown service"

    except Exception as e:
        logging.error(f"Error applying service change for {service}: {e}")
        return f"Error: {str(e)}"


@router.get("/")
async def get_services_status():
    """Get status of all configurable services."""
    config = load_config()
    animation = get_animation_service()
    agent = get_lelamp_agent()

    services = {}
    for service_key, config_path in CONFIGURABLE_SERVICES.items():
        enabled = get_nested_value(config, config_path, False)

        # Determine actual running state
        running = enabled
        if service_key.endswith("_modifier"):
            # For modifiers, check if they're actually active
            if animation:
                modifier_name = service_key.replace("_modifier", "")
                modifiers = animation._modifiers.list_modifiers() if hasattr(animation, '_modifiers') else {}
                running = modifiers.get(modifier_name, False)
        elif service_key == "rgb":
            # Check if RGB service is actually running
            if agent and hasattr(agent, 'rgb_service') and agent.rgb_service:
                running = agent.rgb_service._running.is_set()
            else:
                running = False
        elif service_key == "audio":
            # Check if audio service is actually running
            if agent and hasattr(agent, 'audio_service') and agent.audio_service:
                running = getattr(agent.audio_service, '_running', False)
            else:
                running = False
        elif service_key == "motors":
            # Check if animation service is running AND robot is connected
            if animation:
                running = animation._running.is_set() and animation.robot and animation.robot.is_connected
            else:
                running = False
        elif service_key == "motor_tracking":
            # Check if motor tracking is actually running
            if animation and g.vision_service:
                running = animation.is_face_tracking_mode() and g.vision_service.is_motor_tracking_enabled()
            else:
                running = False

        services[service_key] = {
            "enabled": enabled,
            "running": running,
            "config_path": config_path,
        }

    return {
        "success": True,
        "services": services,
    }


class ServiceToggleRequest(BaseModel):
    service: str
    enabled: bool


@router.post("/toggle")
async def toggle_service(request: ServiceToggleRequest):
    """Enable or disable a service with immediate effect."""
    if request.service not in CONFIGURABLE_SERVICES:
        return {
            "success": False,
            "error": f"Unknown service: {request.service}. Available: {list(CONFIGURABLE_SERVICES.keys())}",
        }

    # Update config for persistence
    config_path = CONFIGURABLE_SERVICES[request.service]
    config = load_config()
    set_nested_value(config, config_path, request.enabled)
    save_config(config)

    # Apply change at runtime
    status_msg = await _apply_service_change(request.service, request.enabled)
    logging.info(f"Service toggle: {request.service} -> {request.enabled}: {status_msg}")

    return {
        "success": True,
        "service": request.service,
        "enabled": request.enabled,
        "message": status_msg,
    }


@router.post("/enable/{service}")
async def enable_service(service: str):
    """Enable a specific service with immediate effect."""
    if service not in CONFIGURABLE_SERVICES:
        return {
            "success": False,
            "error": f"Unknown service: {service}",
        }

    # Update config
    config_path = CONFIGURABLE_SERVICES[service]
    config = load_config()
    set_nested_value(config, config_path, True)
    save_config(config)

    # Apply change at runtime
    status_msg = await _apply_service_change(service, True)
    logging.info(f"Service enabled: {service}: {status_msg}")

    return {
        "success": True,
        "service": service,
        "enabled": True,
        "message": status_msg,
    }


@router.post("/disable/{service}")
async def disable_service(service: str):
    """Disable a specific service with immediate effect."""
    if service not in CONFIGURABLE_SERVICES:
        return {
            "success": False,
            "error": f"Unknown service: {service}",
        }

    # Update config
    config_path = CONFIGURABLE_SERVICES[service]
    config = load_config()
    set_nested_value(config, config_path, False)
    save_config(config)

    # Apply change at runtime
    status_msg = await _apply_service_change(service, False)
    logging.info(f"Service disabled: {service}: {status_msg}")

    return {
        "success": True,
        "service": service,
        "enabled": False,
        "message": status_msg,
    }


# ============ RGB Controls ============

class RGBBrightnessRequest(BaseModel):
    brightness: int  # 0-100 percent


@router.get("/rgb/brightness")
async def get_rgb_brightness():
    """Get current RGB LED brightness."""
    agent = get_lelamp_agent()

    if not agent or not hasattr(agent, 'rgb_service') or not agent.rgb_service:
        # Fall back to config value
        config = load_config()
        brightness = config.get("rgb", {}).get("led_brightness", 70)
        return {
            "success": True,
            "brightness": brightness,
            "source": "config",
        }

    brightness = agent.rgb_service.get_brightness()
    return {
        "success": True,
        "brightness": brightness,
        "source": "live",
    }


@router.post("/rgb/brightness")
async def set_rgb_brightness(request: RGBBrightnessRequest):
    """Set RGB LED brightness (0-100%) with immediate effect."""
    brightness = max(0, min(100, request.brightness))
    agent = get_lelamp_agent()

    # Update config for persistence
    config = load_config()
    if "rgb" not in config:
        config["rgb"] = {}
    config["rgb"]["led_brightness"] = brightness
    save_config(config)

    # Apply immediately if RGB service is available
    if agent and hasattr(agent, 'rgb_service') and agent.rgb_service:
        agent.rgb_service.set_brightness(brightness)
        return {
            "success": True,
            "brightness": brightness,
            "message": f"RGB brightness set to {brightness}%",
            "applied": True,
        }

    return {
        "success": True,
        "brightness": brightness,
        "message": f"RGB brightness saved to config (service not running)",
        "applied": False,
    }
