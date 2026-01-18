"""
Character/personality management API endpoints.
"""
import os
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request

from api.deps import get_config, save_config

router = APIRouter()

CHARACTERS_DIR = Path(__file__).parent.parent.parent / "lelamp" / "personality" / "characters"


@router.get("/")
async def list_characters():
    """List available character personality files."""
    try:
        if not CHARACTERS_DIR.exists():
            return {"success": False, "error": "Characters directory not found"}

        characters = []
        for filename in os.listdir(CHARACTERS_DIR):
            if filename.endswith(".json"):
                filepath = CHARACTERS_DIR / filename
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        char_data = json.load(f)
                        characters.append(
                            {
                                "file": str(filepath),
                                "name": char_data.get("name", filename.replace(".json", "")),
                                "description": char_data.get("description", ""),
                            }
                        )
                except Exception as e:
                    logging.error(f"Error loading character {filename}: {e}")

        return {"success": True, "characters": characters}
    except Exception as e:
        logging.error(f"Error listing characters: {e}")
        return {"success": False, "error": str(e)}


@router.post("/")
async def update_character(request: Request):
    """Update the selected character in config."""
    try:
        data = await request.json()
        character_file = data.get("character_file")

        if not character_file or not os.path.exists(character_file):
            return {"success": False, "error": "Invalid character file"}

        # Load character data
        with open(character_file, "r", encoding="utf-8") as f:
            char_data = json.load(f)

        # Extract character ID from filename (e.g., "HaloX.json" -> "HaloX")
        char_id = Path(character_file).stem

        # Update config with full personality info
        config = get_config()
        if "personality" not in config:
            config["personality"] = {}

        config["personality"]["character_file"] = character_file
        config["personality"]["character_id"] = char_id
        config["personality"]["name"] = char_data.get("name", char_id)
        config["personality"]["description"] = char_data.get("description", "")
        config["personality"]["speech_style"] = char_data.get("speech_style", "")
        config["personality"]["voice_model"] = char_data.get("voice_model", "alloy")

        save_config(config)

        return {
            "success": True,
            "message": "Character updated. Restart required for changes to take effect.",
            "character": char_data,
        }
    except Exception as e:
        logging.error(f"Error updating character: {e}")
        return {"success": False, "error": str(e)}


@router.get("/current")
async def get_current_character():
    """Get current character data from file."""
    try:
        config = get_config()
        character_file = config.get("personality", {}).get("character_file")

        if not character_file or not os.path.exists(character_file):
            return {"success": False, "error": "No character file configured"}

        with open(character_file, "r", encoding="utf-8") as f:
            char_data = json.load(f)

        return {"success": True, "character": char_data}
    except Exception as e:
        logging.error(f"Error loading current character: {e}")
        return {"success": False, "error": str(e)}
