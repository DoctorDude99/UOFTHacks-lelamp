"""
Personality configuration endpoints.

Handles LeLamp character selection, name, and favorite color settings.
Loads actual character definitions from lelamp/personality/characters/.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import load_config, save_config

router = APIRouter()
logger = logging.getLogger(__name__)

# Path to character files
CHARACTERS_DIR = Path(__file__).parent.parent.parent.parent / "lelamp" / "personality" / "characters"


class CharacterInfo(BaseModel):
    """Character information from JSON file."""
    id: str
    name: str
    description: str
    speech_style: str
    voice_model: str
    visual_description: Optional[str] = None
    ideals: Optional[str] = None
    flaws: Optional[str] = None
    bio: Optional[str] = None


class PersonalityConfig(BaseModel):
    """Request to save personality configuration."""
    name: str = "LeLamp"
    character_id: str = "LeLamp"
    default_color: Optional[List[int]] = None  # RGB array like [0, 0, 150]


def load_characters() -> List[CharacterInfo]:
    """Load all character definitions from the characters directory."""
    characters = []

    if not CHARACTERS_DIR.exists():
        logger.warning(f"Characters directory not found: {CHARACTERS_DIR}")
        return characters

    for json_file in sorted(CHARACTERS_DIR.glob("*.json")):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            character = CharacterInfo(
                id=json_file.stem,  # Filename without extension
                name=data.get("name", json_file.stem),
                description=data.get("description", ""),
                speech_style=data.get("speech_style", ""),
                voice_model=data.get("voice_model", "alloy"),
                visual_description=data.get("visual_description"),
                ideals=data.get("ideals"),
                flaws=data.get("flaws"),
                bio=data.get("bio"),
            )
            characters.append(character)
        except Exception as e:
            logger.error(f"Error loading character {json_file}: {e}")

    return characters


def get_character(character_id: str) -> Optional[CharacterInfo]:
    """Get a specific character by ID."""
    characters = load_characters()
    for char in characters:
        if char.id == character_id:
            return char
    return None


@router.get("/")
async def get_personality():
    """Get current personality configuration and available characters."""
    try:
        config = load_config()
        personality = config.get('personality', {})
        rgb_config = config.get('rgb', {})

        # Load available characters
        characters = load_characters()

        # Get current character
        current_character_id = personality.get('character_id', 'LeLamp')
        current_character = get_character(current_character_id)

        return {
            "success": True,
            "name": personality.get('name', 'LeLamp'),
            "character_id": current_character_id,
            "character": current_character.model_dump() if current_character else None,
            "default_color": rgb_config.get('default_color', [0, 0, 150]),
            "characters": [c.model_dump() for c in characters],
        }
    except Exception as e:
        logger.error(f"Error getting personality: {e}")
        return {"success": False, "error": str(e)}


@router.get("/characters")
async def list_characters():
    """List all available character personalities."""
    try:
        characters = load_characters()
        return {
            "success": True,
            "characters": [c.model_dump() for c in characters],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/characters/{character_id}")
async def get_character_details(character_id: str):
    """Get details for a specific character."""
    try:
        character = get_character(character_id)
        if not character:
            return {"success": False, "error": f"Character not found: {character_id}"}

        return {
            "success": True,
            "character": character.model_dump(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def hex_to_rgb(hex_color: str) -> List[int]:
    """Convert hex color string to RGB list."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
    return [100, 100, 255]  # Default blue if invalid


@router.post("/")
async def save_personality(data: PersonalityConfig):
    """Save personality configuration."""
    try:
        config = load_config()

        # Get character details
        character = get_character(data.character_id)
        if not character:
            return {"success": False, "error": f"Character not found: {data.character_id}"}

        # Update personality config
        config.setdefault('personality', {})
        config['personality']['name'] = data.name
        config['personality']['character_id'] = data.character_id
        config['personality']['description'] = character.description
        config['personality']['speech_style'] = character.speech_style
        config['personality']['voice_model'] = character.voice_model

        # Save default color if provided (RGB array)
        if data.default_color:
            config.setdefault('rgb', {})
            config['rgb']['default_color'] = data.default_color

        # Update ID based on name (for device identification)
        config['id'] = data.name.lower().replace(' ', '_')

        # Mark step complete
        config.setdefault('setup', {})
        config['setup'].setdefault('steps_completed', {})
        config['setup']['steps_completed']['personality'] = True

        save_config(config)

        return {
            "success": True,
            "name": data.name,
            "character_id": data.character_id,
            "character_name": character.name,
            "default_color": data.default_color,
        }
    except Exception as e:
        logger.error(f"Error saving personality: {e}")
        return {"success": False, "error": str(e)}


class FavoriteColorRequest(BaseModel):
    """Request to set favorite color."""
    color: str  # Hex color like "#ff6b6b"


@router.post("/favorite-color")
async def set_favorite_color(data: FavoriteColorRequest):
    """Set the lamp's favorite color and update RGB defaults."""
    try:
        config = load_config()

        # Save to personality
        config.setdefault('personality', {})
        config['personality']['favorite_color'] = data.color

        # Also set as default RGB animation color
        rgb_color = hex_to_rgb(data.color)
        config.setdefault('rgb', {})
        config['rgb']['default_color'] = rgb_color
        config['rgb']['default_animation'] = 'ripple'

        save_config(config)

        return {
            "success": True,
            "favorite_color": data.color,
            "rgb_color": rgb_color,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
