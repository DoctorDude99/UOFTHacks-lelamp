"""
Dashboard status endpoints.

Provides system status and health information.
"""

from pathlib import Path
from fastapi import APIRouter
from api.deps import (
    load_config,
    get_animation_service,
    get_rgb_service,
    get_vision_service,
    get_audio_service,
    get_lelamp_agent,
)
import lelamp.globals as g

router = APIRouter()


def check_calibration_required(config: dict) -> bool:
    """Check if motor calibration is required.

    Returns True if:
    - motors are enabled AND
    - calibration file doesn't exist (the source of truth)
    """
    motors_enabled = config.get('motors', {}).get('enabled', False)
    if not motors_enabled:
        return False

    # Check if calibration file exists - this is the source of truth
    # Calibration is always at ~/.lelamp/calibration/lelamp.json
    from lelamp.user_data import get_calibration_path
    calibration_file = get_calibration_path()

    return not calibration_file.exists()


@router.get("/status")
async def get_system_status():
    """Get overall system status."""
    try:
        config = load_config()
        agent = get_lelamp_agent()
        animation = get_animation_service()
        rgb = get_rgb_service()
        vision = get_vision_service()
        audio = get_audio_service()

        # Check calibration status
        calibration_required = check_calibration_required(config)

        return {
            "success": True,
            "agent": {
                "running": agent is not None,
                "sleeping": getattr(agent, 'is_sleeping', False) if agent else False,
            },
            "services": {
                "animation": animation is not None,
                "rgb": rgb is not None,
                "vision": vision is not None,
                "audio": audio is not None,
            },
            "config": {
                "name": config.get('personality', {}).get('name', 'LeLamp'),
                "setup_complete": config.get('setup', {}).get('setup_complete', False),
                "calibration_required": calibration_required,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}
