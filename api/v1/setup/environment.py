"""
Environment configuration endpoints.

Handles API keys and credentials setup:
- OpenAI API key
- LiveKit credentials
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import os

from api.deps import load_config, save_config, get_config_path

router = APIRouter()


class EnvConfig(BaseModel):
    openai_key: str
    livekit_url: Optional[str] = None
    livekit_key: Optional[str] = None
    livekit_secret: Optional[str] = None


@router.get("/check")
async def check_env():
    """Check current environment configuration.

    If OpenAI key is already set, auto-marks the environment step as complete.
    """
    try:
        env_file = get_config_path().parent / ".env"

        if not env_file.exists():
            return {
                "success": True,
                "exists": False,
                "has_openai": False,
                "has_livekit": False,
                "auto_skip": False
            }

        with open(env_file, 'r') as f:
            content = f.read()

        # Check for non-empty values
        has_openai = 'OPENAI_API_KEY=' in content and 'OPENAI_API_KEY=\n' not in content
        has_livekit_url = 'LIVEKIT_URL=' in content and 'wss://' in content
        has_livekit_key = 'LIVEKIT_API_KEY=' in content and 'LIVEKIT_API_KEY=\n' not in content
        has_livekit_secret = 'LIVEKIT_API_SECRET=' in content and 'LIVEKIT_API_SECRET=\n' not in content

        # Auto-mark environment step as complete if OpenAI key exists
        auto_skip = False
        if has_openai:
            config = load_config()
            steps_completed = config.get('setup', {}).get('steps_completed', {})
            if not steps_completed.get('environment', False):
                config.setdefault('setup', {})
                config['setup'].setdefault('steps_completed', {})
                config['setup']['steps_completed']['environment'] = True
                save_config(config)
                auto_skip = True

        return {
            "success": True,
            "exists": True,
            "has_openai": has_openai,
            "has_livekit": has_livekit_url and has_livekit_key and has_livekit_secret,
            "auto_skip": auto_skip
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/save")
async def save_env(data: EnvConfig):
    """Save environment configuration."""
    try:
        if not data.openai_key:
            return {"success": False, "error": "OpenAI API key is required"}

        env_file = get_config_path().parent / ".env"

        content = f"OPENAI_API_KEY={data.openai_key}\n"

        if data.livekit_url and data.livekit_key and data.livekit_secret:
            content += f"LIVEKIT_URL={data.livekit_url}\n"
            content += f"LIVEKIT_API_KEY={data.livekit_key}\n"
            content += f"LIVEKIT_API_SECRET={data.livekit_secret}\n"

        with open(env_file, 'w') as f:
            f.write(content)

        # Secure the file (readable only by owner)
        os.chmod(env_file, 0o600)

        # Mark step as complete in config
        config = load_config()
        config.setdefault('setup', {})
        config['setup'].setdefault('steps_completed', {})
        config['setup']['steps_completed']['environment'] = True
        save_config(config)

        return {"success": True, "message": "Environment configured"}
    except Exception as e:
        return {"success": False, "error": str(e)}
