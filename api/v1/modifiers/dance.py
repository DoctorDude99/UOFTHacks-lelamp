"""
Dance mode API endpoints.

Controls energy-based dance animations.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from api.deps import get_animation_service, get_spotify_service

router = APIRouter()


class DanceThresholds(BaseModel):
    dance_threshold: float = 0.25
    excited_threshold: float = 0.6


@router.get("/")
async def get_dance_status():
    """Get current dance mode status and settings."""
    animation = get_animation_service()
    spotify = get_spotify_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        # Get current energy from Spotify
        energy = 0.0
        if spotify and hasattr(spotify, 'get_energy'):
            energy = spotify.get_energy()

        return {
            "success": True,
            "dance_mode": animation.is_dance_mode(),
            "dance_threshold": animation._dance_threshold,
            "excited_threshold": animation._excited_threshold,
            "current_energy": energy,
            "dance_animations": animation._dance_animations,
            "excited_animations": animation._excited_animations,
            "last_animation": animation._last_dance_animation
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/enable")
async def enable_dance_mode():
    """Enable energy-based dance mode."""
    animation = get_animation_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        animation.start_dance_mode()
        return {"success": True, "message": "Dance mode enabled"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/disable")
async def disable_dance_mode():
    """Disable dance mode and return to idle."""
    animation = get_animation_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        animation.stop_dance_mode()
        return {"success": True, "message": "Dance mode disabled"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/thresholds")
async def update_dance_thresholds(data: DanceThresholds):
    """Update dance mode thresholds."""
    animation = get_animation_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        animation.set_dance_thresholds(data.dance_threshold, data.excited_threshold)

        return {
            "success": True,
            "dance_threshold": data.dance_threshold,
            "excited_threshold": data.excited_threshold
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
