"""
Music modifier API endpoints.

Controls the music/beat-sync animation modifier.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from api.deps import get_animation_service, load_config, save_config

router = APIRouter()

# Available joints for music modifier
AVAILABLE_JOINTS = [
    "base_yaw.pos",
    "base_pitch.pos",
    "elbow_pitch.pos",
    "wrist_roll.pos",
    "wrist_pitch.pos"
]


class MusicModifierUpdate(BaseModel):
    amplitude: Optional[float] = None
    beat_divisor: Optional[float] = None
    groove: Optional[float] = None
    joints: Optional[List[str]] = None


@router.get("/")
async def get_music_modifier():
    """Get current music modifier settings."""
    animation = get_animation_service()

    if not animation:
        return {"error": "Animation service not available", "enabled": False}

    try:
        music_mod = animation.get_modifier("music")
        if not music_mod:
            return {"error": "Music modifier not found", "enabled": False}

        # Get cached BPM
        cached_bpm = 0
        if hasattr(music_mod, '_cached_bpm'):
            cached_bpm = music_mod._cached_bpm
        elif hasattr(music_mod, '_current_bpm'):
            cached_bpm = music_mod._current_bpm

        return {
            "enabled": animation.is_modifier_enabled("music"),
            "amplitude": music_mod.config.amplitude,
            "beat_divisor": music_mod.config.beat_divisor,
            "groove": music_mod.config.groove,
            "active_joints": list(music_mod.target_joints),
            "available_joints": AVAILABLE_JOINTS,
            "fallback_bpm": music_mod.config.fallback_bpm,
            "current_bpm": cached_bpm
        }
    except Exception as e:
        return {"error": str(e), "enabled": False}


@router.post("/")
async def update_music_modifier(data: MusicModifierUpdate):
    """Update music modifier settings."""
    animation = get_animation_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        music_mod = animation.get_modifier("music")
        if not music_mod:
            return {"success": False, "error": "Music modifier not found"}

        if data.amplitude is not None:
            music_mod.set_amplitude(data.amplitude)

        if data.beat_divisor is not None:
            music_mod.set_beat_divisor(data.beat_divisor)

        if data.groove is not None:
            music_mod.set_groove(data.groove)

        if data.joints is not None:
            music_mod.update_target_joints(set(data.joints))

        current_bpm = getattr(music_mod, '_current_bpm', 0)
        return {"success": True, "current_bpm": current_bpm}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/enable")
async def enable_music_modifier():
    """Enable the music modifier."""
    animation = get_animation_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        result = animation.enable_modifier("music")
        return {"success": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/disable")
async def disable_music_modifier():
    """Disable the music modifier."""
    animation = get_animation_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        result = animation.disable_modifier("music")
        return {"success": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/save")
async def save_music_modifier_config():
    """Save current music modifier settings to config.yaml."""
    animation = get_animation_service()

    if not animation:
        return {"success": False, "error": "Animation service not available"}

    try:
        music_mod = animation.get_modifier("music")
        if not music_mod:
            return {"success": False, "error": "Music modifier not found"}

        config = load_config()

        # Update music modifier settings
        config.setdefault('modifiers', {})
        config['modifiers'].setdefault('music', {})

        config['modifiers']['music']['enabled'] = animation.is_modifier_enabled("music")
        config['modifiers']['music']['amplitude'] = music_mod.config.amplitude
        config['modifiers']['music']['beat_divisor'] = music_mod.config.beat_divisor
        config['modifiers']['music']['groove'] = music_mod.config.groove
        config['modifiers']['music']['joints'] = list(music_mod.target_joints)
        config['modifiers']['music']['dance_threshold'] = animation._dance_threshold
        config['modifiers']['music']['excited_threshold'] = animation._excited_threshold

        save_config(config)
        return {"success": True, "message": "Settings saved to config.yaml"}
    except Exception as e:
        return {"success": False, "error": str(e)}
