"""
RGB LED setup API endpoints.

Uses the global RGB service (started at boot).
Provides toggle to enable/disable RGB if user doesn't have LEDs.
"""

import asyncio
import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import load_config, save_config
import lelamp.globals as g

router = APIRouter()
logger = logging.getLogger(__name__)


class BrightnessRequest(BaseModel):
    brightness: int  # 0-100


class EnableRequest(BaseModel):
    enabled: bool


class ColorRequest(BaseModel):
    r: int = 0
    g: int = 0
    b: int = 0


def _is_pi5() -> bool:
    try:
        with open("/proc/device-tree/model", "r") as f:
            return "raspberry pi 5" in f.read().lower()
    except Exception:
        return False


def _has_lgpio() -> bool:
    """Check if lgpio is available (used for Pi 5 RGB)."""
    try:
        import lgpio
        return True
    except ImportError:
        return False


@router.get("/status")
async def get_rgb_status():
    """Get RGB status and service state."""
    try:
        config = load_config()
        rgb_config = config.get("rgb", {})

        led_count = rgb_config.get("led_count", 93)
        led_pin = rgb_config.get("led_pin", 10)
        enabled = rgb_config.get("enabled", True)

        is_pi5 = _is_pi5()

        # Hardware availability check
        if is_pi5 and led_pin == 10:
            hardware_ready = _has_lgpio()
            driver_type = "lgpio"
        else:
            hardware_ready = True
            driver_type = "pwm"

        # available = hardware configured AND ready (for frontend auto-skip logic)
        available = led_count > 0 and hardware_ready

        return {
            "success": True,
            "available": available,
            "enabled": enabled,
            "service_running": g.rgb_service is not None,
            "led_count": led_count,
            "led_pin": led_pin,
            "brightness": rgb_config.get("led_brightness", 50),
            "is_pi5": is_pi5,
            "driver_type": driver_type,
            "hardware_ready": hardware_ready,
        }

    except Exception as e:
        logger.error(f"Error checking RGB status: {e}")
        return {"success": False, "error": str(e)}


@router.post("/enable")
async def set_rgb_enabled(request: EnableRequest):
    """
    Enable or disable RGB.

    Toggle for users who don't have LEDs attached.
    Changes take effect on next boot.
    """
    try:
        config = load_config()
        config.setdefault("rgb", {})
        config["rgb"]["enabled"] = request.enabled
        save_config(config)

        return {
            "success": True,
            "enabled": request.enabled,
            "message": f"RGB {'enabled' if request.enabled else 'disabled'}. Takes effect on restart."
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/test")
async def test_rgb():
    """Run RGB led_test animation (R->G->B->White, one LED at a time)."""
    try:
        if g.rgb_service is None:
            return {
                "success": False,
                "error": "RGB service not running. Check that rgb.enabled=true and restart."
            }

        config = load_config()
        brightness = config.get("rgb", {}).get("led_brightness", 25)
        g.rgb_service.set_brightness(brightness)

        # Play led_test animation (R, G, B, White cycle)
        # Duration based on LED count: 4 colors * led_count * 0.1s delay
        led_count = config.get("rgb", {}).get("led_count", 61)
        duration = 4 * led_count * 0.1 + 1.0  # One full cycle plus buffer

        g.rgb_service.handle_event("animation", {
            "name": "led_test",
            "duration": duration
        })

        # Schedule clear after animation completes
        asyncio.create_task(_clear_leds_after_delay(duration + 1.0))

        return {
            "success": True,
            "message": "LED test started (R->G->B->White, one LED at a time)",
            "animation": "led_test",
            "duration": duration
        }

    except Exception as e:
        logger.error(f"Error starting RGB test: {e}")
        return {"success": False, "error": str(e)}


@router.post("/test/welcome")
async def test_rgb_welcome():
    """Run RGB welcome animation (fancy rainbow effects)."""
    try:
        if g.rgb_service is None:
            return {
                "success": False,
                "error": "RGB service not running. Check that rgb.enabled=true and restart."
            }

        config = load_config()
        brightness = config.get("rgb", {}).get("led_brightness", 25)
        g.rgb_service.set_brightness(brightness)

        # Play welcome animation
        duration = 10.0
        g.rgb_service.handle_event("animation", {
            "name": "welcome",
            "duration": duration
        })

        # Schedule clear after animation completes
        asyncio.create_task(_clear_leds_after_delay(duration + 1.0))

        return {
            "success": True,
            "message": "Welcome animation started",
            "animation": "welcome",
            "duration": duration
        }

    except Exception as e:
        logger.error(f"Error starting RGB welcome test: {e}")
        return {"success": False, "error": str(e)}


async def _clear_leds_after_delay(delay: float):
    """Clear LEDs after a delay to ensure they turn off after animation."""
    await asyncio.sleep(delay)
    if g.rgb_service is not None:
        g.rgb_service.clear()


@router.post("/animation/{name}")
async def play_animation(name: str, duration: float = 10.0):
    """Play a specific RGB animation."""
    try:
        if g.rgb_service is None:
            return {"success": False, "error": "RGB service not running"}

        available = g.rgb_service.get_available_animations()
        if name not in available:
            return {
                "success": False,
                "error": f"Unknown animation: {name}",
                "available": list(available.keys())
            }

        g.rgb_service.handle_event("animation", {"name": name, "duration": duration})
        return {"success": True, "animation": name, "duration": duration}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/animations")
async def list_animations():
    """List available RGB animations."""
    try:
        from lelamp.service.rgb.sequences import list_animations as get_anims
        return {"success": True, "animations": get_anims()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/color")
async def set_color(request: ColorRequest):
    """Set solid color."""
    try:
        if g.rgb_service is None:
            return {"success": False, "error": "RGB service not running"}

        g.rgb_service.handle_event("solid", (request.r, request.g, request.b))
        return {"success": True, "color": {"r": request.r, "g": request.g, "b": request.b}}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/off")
async def turn_off():
    """Turn off LEDs."""
    try:
        if g.rgb_service is None:
            return {"success": True, "message": "RGB service not running"}

        g.rgb_service.handle_event("stop_animation")
        g.rgb_service.clear()
        return {"success": True, "message": "LEDs off"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/brightness")
async def get_brightness():
    """Get brightness setting."""
    config = load_config()
    return {
        "success": True,
        "brightness": config.get("rgb", {}).get("led_brightness", 50)
    }


@router.post("/brightness")
async def set_brightness(request: BrightnessRequest):
    """Set brightness."""
    try:
        brightness = max(0, min(100, request.brightness))

        config = load_config()
        config.setdefault("rgb", {})
        config["rgb"]["led_brightness"] = brightness
        save_config(config)

        if g.rgb_service:
            g.rgb_service.set_brightness(brightness)

        return {"success": True, "brightness": brightness}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/complete")
async def complete_rgb_setup():
    """Mark RGB setup step as complete."""
    try:
        config = load_config()

        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"]["steps_completed"]["rgb"] = True

        save_config(config)

        return {"success": True, "message": "RGB setup completed"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/skip")
async def skip_rgb_setup():
    """Skip RGB setup step."""
    try:
        config = load_config()

        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"]["steps_completed"]["rgb"] = True
        config["setup"].setdefault("steps_skipped", {})
        config["setup"]["steps_skipped"]["rgb"] = True

        save_config(config)

        return {"success": True, "message": "RGB setup skipped"}

    except Exception as e:
        return {"success": False, "error": str(e)}
