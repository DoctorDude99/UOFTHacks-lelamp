"""
Motor calibration API endpoints.

Provides endpoints for the motor calibration workflow.
"""

import asyncio
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from api.deps import load_config, save_config, get_animation_service
import lelamp.globals as g

logger = logging.getLogger(__name__)

router = APIRouter()

# Global calibration service instance for this module
_calibration_service = None


@router.post("/start")
async def start_calibration():
    """Start motor calibration process.

    This will:
    1. Play the sleep animation to safely park the lamp
    2. Disconnect the animation service from the motors
    3. Start the calibration service
    """
    global _calibration_service

    try:
        from lelamp.service.motors.calibration_service import CalibrationService

        config = load_config()
        port = config.get("motors", {}).get("port", "/dev/lelamp")

        # Step 1: Gracefully take over from animation service
        animation = get_animation_service()
        if animation and animation.robot and animation.robot.is_connected:
            logger.info("Taking over motors from animation service...")

            # Switch to Gentle preset for safe, slow movement
            try:
                animation.robot.apply_preset("Gentle")
                logger.info("Applied Gentle preset for safe transition")
            except Exception as e:
                logger.warning(f"Could not apply Gentle preset: {e}")

            # Play sleep animation to park the lamp safely (tucked position)
            try:
                animation.dispatch("play", "sleep")
                logger.info("Playing sleep animation...")
                # Wait for sleep animation to complete (5+ seconds)
                await asyncio.sleep(5.0)
                logger.info("Sleep animation complete, lamp is parked")
            except Exception as e:
                logger.warning(f"Could not play sleep animation: {e}")

            # Now disconnect and release motors - lamp is in safe tucked position
            try:
                animation.robot.bus.disconnect(disable_torque=True)
                logger.info("Disconnected animation service and released motors")
            except Exception as e:
                logger.warning(f"Error disconnecting animation robot: {e}")

        # Step 2: Start calibration service
        _calibration_service = CalibrationService(port=port)
        result = _calibration_service.connect()

        if result["success"]:
            g.calibration_in_progress = True

        return result
    except Exception as e:
        logger.error(f"Failed to start calibration: {e}")
        return {"success": False, "error": str(e)}


@router.get("/status")
async def get_calibration_status():
    """Get current calibration status."""
    if _calibration_service is None:
        return {
            "connected": False,
            "step": "not_started",
            "calibration_required": g.calibration_required,
        }

    status = _calibration_service.get_status()
    status["calibration_required"] = g.calibration_required

    # Include min/max ranges if they've been recorded
    status["range_mins"] = _calibration_service.range_mins
    status["range_maxs"] = _calibration_service.range_maxes
    status["homing_offsets"] = _calibration_service.homing_offsets

    return status


@router.get("/positions")
async def get_calibration_positions():
    """Get current motor positions during calibration."""
    if _calibration_service is None:
        return {"success": False, "error": "Calibration not started"}

    positions = _calibration_service.get_current_positions()
    return {
        "success": True,
        "positions": positions,
        "step": _calibration_service.current_step,
        "range_mins": _calibration_service.range_mins,
        "range_maxs": _calibration_service.range_maxes,
    }


@router.post("/prepare-homing")
async def prepare_for_homing():
    """Disable torque so user can manually position the lamp.

    Call this when user is ready to physically move the lamp to center position.
    """
    if _calibration_service is None:
        return {"success": False, "error": "Calibration not started"}

    return _calibration_service.prepare_for_homing()


@router.post("/record-homing")
async def record_homing():
    """Record homing positions (center/zero point)."""
    if _calibration_service is None:
        return {"success": False, "error": "Calibration not started"}

    return _calibration_service.record_homing()


@router.post("/start-range")
async def start_range_recording():
    """Start recording range of motion."""
    if _calibration_service is None:
        return {"success": False, "error": "Calibration not started"}

    return _calibration_service.start_range_recording()


@router.post("/record-ranges")
async def record_ranges():
    """Record min/max range for all motors."""
    if _calibration_service is None:
        return {"success": False, "error": "Calibration not started"}

    return _calibration_service.record_ranges()


async def _reconnect_animation_service():
    """Reconnect the animation service to motors after calibration."""
    animation = get_animation_service()
    if animation and animation.robot:
        try:
            if not animation.robot.is_connected:
                logger.info("Reconnecting animation service to motors...")
                animation.robot.connect(calibrate=False)
                # Return to idle animation
                animation.dispatch("play", animation.idle_recording)
                logger.info("Animation service reconnected")
        except Exception as e:
            logger.error(f"Failed to reconnect animation service: {e}")


@router.post("/finalize")
async def finalize_calibration():
    """Finalize and save calibration."""
    global _calibration_service

    if _calibration_service is None:
        return {"success": False, "error": "Calibration not started"}

    result = _calibration_service.finalize_calibration()

    if result["success"]:
        # Load and update config
        config = load_config()

        # Enable motors in config
        if "motors" not in config:
            config["motors"] = {}
        config["motors"]["enabled"] = True

        # Mark calibration step as complete
        if "setup" not in config:
            config["setup"] = {}
        if "steps_completed" not in config["setup"]:
            config["setup"]["steps_completed"] = {}
        config["setup"]["steps_completed"]["motor_calibration"] = True

        save_config(config)

        # Clear calibration flags
        g.calibration_required = False
        g.calibration_in_progress = False

        # Disconnect calibration service
        _calibration_service.disconnect()
        _calibration_service = None

        # Reconnect animation service
        await _reconnect_animation_service()

    return result


@router.post("/cancel")
async def cancel_calibration():
    """Cancel calibration and disconnect."""
    global _calibration_service

    if _calibration_service:
        _calibration_service.disconnect()
        _calibration_service = None

    g.calibration_in_progress = False

    # Reconnect animation service
    await _reconnect_animation_service()

    return {"success": True}
