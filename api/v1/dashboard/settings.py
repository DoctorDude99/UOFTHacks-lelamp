"""
Settings management endpoints.

Handles reading and writing config.yaml settings.
Also applies certain settings in real-time (volume, RGB, etc.)
"""

import subprocess
from fastapi import APIRouter
from typing import Dict, Any

from api.deps import load_config, save_config

router = APIRouter()


def apply_volume(volume_type: str, volume_percent: int) -> bool:
    """Apply volume change via amixer."""
    volume_percent = max(0, min(100, volume_percent))

    if volume_type == "speaker":
        controls = ["Master", "PCM", "Speaker", "Headphone"]
        # Try default card first, then Device (USB)
        cards = [None, "Device", "3"]
    else:
        # For microphone, use capture-specific controls
        controls = ["Mic", "Capture", "ADC", "ADC PCM"]
        # USB Audio Device is typically card 3 or "Device"
        cards = ["Device", "3", None]

    success = False
    for card in cards:
        for control in controls:
            try:
                cmd = ["amixer"]
                if card:
                    cmd.extend(["-c", card])

                # For mic, set capture channel specifically
                if volume_type == "microphone":
                    cmd.extend(["sset", control, "capture", f"{volume_percent}%"])
                else:
                    cmd.extend(["sset", control, f"{volume_percent}%"])

                result = subprocess.run(cmd, capture_output=True, timeout=5)
                if result.returncode == 0 and b"%" in result.stdout:
                    success = True
            except Exception:
                pass
    return success


def deep_merge(base: dict, updates: dict) -> dict:
    """Deep merge updates into base dict."""
    result = base.copy()
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@router.get("/")
async def get_settings():
    """Get all settings from config.yaml."""
    try:
        config = load_config()
        return {"success": True, "config": config}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/")
async def update_settings(data: Dict[str, Any]):
    """Save settings to config.yaml (deep merge) and apply real-time changes."""
    try:
        current_config = load_config()
        updated_config = deep_merge(current_config, data)
        save_config(updated_config)

        # Apply real-time changes for certain settings
        applied = []

        # Volume changes - apply immediately via amixer
        if "volume" in data:
            apply_volume("speaker", data["volume"])
            applied.append("speaker volume")

        if "microphone_volume" in data:
            apply_volume("microphone", data["microphone_volume"])
            applied.append("microphone volume")

        msg = "Settings saved"
        if applied:
            msg += f" (applied: {', '.join(applied)})"

        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/reset")
async def reset_settings():
    """Reload settings from config.yaml (discard runtime changes)."""
    try:
        config = load_config()
        return {
            "success": True,
            "config": config,
            "message": "Settings reloaded from config.yaml"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
