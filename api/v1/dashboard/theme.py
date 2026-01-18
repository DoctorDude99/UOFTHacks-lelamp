"""
Theme management endpoints.

Handles listing available themes and switching themes.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import os
from pathlib import Path

from api.deps import load_config, save_config

router = APIRouter()

THEMES_DIR = Path("assets/Theme")


class ThemeSetRequest(BaseModel):
    name: str


@router.get("/")
async def get_themes():
    """Get current theme and list of available themes."""
    try:
        config = load_config()
        current_theme = config.get("theme", {}).get("name", "Lelamp")

        # List available themes
        themes = []
        if THEMES_DIR.exists():
            for item in THEMES_DIR.iterdir():
                if item.is_dir() and (item / "audio").exists():
                    # Count available sounds
                    audio_dir = item / "audio"
                    sound_count = len(list(audio_dir.glob("*.wav")))
                    themes.append({
                        "name": item.name,
                        "sound_count": sound_count,
                        "is_current": item.name == current_theme
                    })

        return {
            "success": True,
            "current": current_theme,
            "themes": sorted(themes, key=lambda x: x["name"])
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/")
async def set_theme(request: ThemeSetRequest):
    """Set the current theme."""
    try:
        # Validate theme exists
        theme_path = THEMES_DIR / request.name / "audio"
        if not theme_path.exists():
            return {"success": False, "error": f"Theme '{request.name}' not found"}

        # Update config
        config = load_config()
        if "theme" not in config:
            config["theme"] = {}
        config["theme"]["name"] = request.name
        save_config(config)

        # Update the running theme service if available
        try:
            from lelamp.service.theme import get_theme_service
            theme_service = get_theme_service()
            if theme_service:
                theme_service.set_theme(request.name)
        except Exception:
            pass  # Theme service may not be running

        return {"success": True, "theme": request.name, "message": f"Theme set to '{request.name}'"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/{theme_name}")
async def get_theme_info(theme_name: str):
    """Get detailed info about a specific theme."""
    try:
        theme_path = THEMES_DIR / theme_name / "audio"
        if not theme_path.exists():
            return {"success": False, "error": f"Theme '{theme_name}' not found"}

        # List all sounds in the theme
        sounds = []
        expected_sounds = [
            "Startup", "Shutdown", "Reboot", "Sleep", "Activate",
            "Alert", "Notify", "CalibrationComplete", "FaceDetect",
            "ManualMode", "Pushable", "Press"
        ]

        for sound_name in expected_sounds:
            sound_path = theme_path / f"{sound_name}.wav"
            sounds.append({
                "name": sound_name,
                "exists": sound_path.exists()
            })

        return {
            "success": True,
            "name": theme_name,
            "path": str(theme_path),
            "sounds": sounds
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
