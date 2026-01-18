"""
LiveKit Cloud Configuration API endpoints.

Handles LiveKit Cloud setup:
- Credential configuration (URL, API Key, API Secret)
- Connection testing
- Room name generation (based on device serial)
"""

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import load_config, save_config
from lelamp.user_data import USER_DATA_DIR, get_device_serial_short

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class LiveKitConfig(BaseModel):
    """LiveKit configuration."""
    url: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None


class LiveKitTestResult(BaseModel):
    """Result of LiveKit connection test."""
    success: bool
    message: str
    room_name: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def get_env_value(key: str) -> Optional[str]:
    """Get a value from .env file."""
    env_path = USER_DATA_DIR / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
        except Exception:
            pass
    return None


def update_env_file(updates: dict):
    """Update .env file with new values."""
    env_path = USER_DATA_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                existing[key.strip()] = value.strip()

    # Merge updates
    existing.update(updates)

    # Write back
    with open(env_path, "w") as f:
        for key, value in existing.items():
            if value:  # Only write non-empty values
                f.write(f"{key}={value}\n")

    env_path.chmod(0o600)


def get_room_name() -> str:
    """Generate room name from device serial."""
    serial = get_device_serial_short()
    return f"lelamp_{serial}"


def is_livekit_configured() -> bool:
    """Check if LiveKit credentials are configured."""
    url = os.getenv("LIVEKIT_URL") or get_env_value("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY") or get_env_value("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET") or get_env_value("LIVEKIT_API_SECRET")

    return bool(url and api_key and api_secret)


async def test_livekit_connection(url: str, api_key: str, api_secret: str) -> tuple:
    """
    Test LiveKit connection by generating a token and verifying credentials.

    Returns (success, message)
    """
    try:
        from livekit import api as livekit_api

        # Create access token to verify credentials work
        token = livekit_api.AccessToken(api_key, api_secret)
        token.with_identity("test_connection")
        token.with_name("Connection Test")

        room_name = get_room_name()
        token.with_grants(livekit_api.VideoGrants(
            room_join=True,
            room=room_name,
        ))

        # Generate the JWT - this validates the key/secret format
        jwt = token.to_jwt()

        if jwt and len(jwt) > 50:
            return True, "Credentials valid"
        else:
            return False, "Failed to generate access token"

    except ImportError:
        return False, "LiveKit SDK not installed"
    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower():
            return False, "Invalid API key or secret"
        return False, f"Connection test failed: {error_msg}"


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/status")
async def get_livekit_status():
    """
    Get current LiveKit configuration and service status.

    Returns configuration status and live service status if available.
    """
    try:
        # Try to get status from livekit_service if available
        import lelamp.globals as g
        if g.livekit_service:
            status_dict = g.livekit_service.get_status_dict()
            return {
                "success": True,
                "configured": status_dict["configured"],
                "room_name": status_dict["room_name"],
                "service_status": status_dict["status"],
                "connected": status_dict["connected"],
                "missing_keys": status_dict["missing_keys"],
                "openai_voice": status_dict["openai_voice"],
                "url": g.livekit_service.credentials.url if g.livekit_service.credentials else "",
                "api_key": g.livekit_service.credentials.api_key if g.livekit_service.credentials else "",
                "api_secret_masked": "****" if g.livekit_service.credentials and g.livekit_service.credentials.api_secret else "",
            }

        # Fallback to reading from env/files if service not initialized
        url = os.getenv("LIVEKIT_URL") or get_env_value("LIVEKIT_URL") or ""
        api_key = os.getenv("LIVEKIT_API_KEY") or get_env_value("LIVEKIT_API_KEY") or ""
        api_secret = os.getenv("LIVEKIT_API_SECRET") or get_env_value("LIVEKIT_API_SECRET") or ""

        configured = bool(url and api_key and api_secret)
        room_name = get_room_name()

        # Mask the secret for display
        masked_secret = ""
        if api_secret:
            masked_secret = api_secret[:4] + "..." + api_secret[-4:] if len(api_secret) > 8 else "****"

        return {
            "success": True,
            "configured": configured,
            "room_name": room_name,
            "service_status": "unknown",
            "connected": False,
            "url": url,
            "api_key": api_key,
            "api_secret_masked": masked_secret,
        }

    except Exception as e:
        logger.error(f"Error getting LiveKit status: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/configure")
async def configure_livekit(config: LiveKitConfig):
    """
    Configure LiveKit credentials.

    Saves to .env file and marks setup step complete.
    """
    try:
        # Validate required fields
        if not config.url:
            return {"success": False, "error": "LiveKit URL is required"}
        if not config.api_key:
            return {"success": False, "error": "API Key is required"}
        if not config.api_secret:
            return {"success": False, "error": "API Secret is required"}

        # Validate URL format
        if not config.url.startswith("wss://"):
            return {"success": False, "error": "URL must start with wss://"}

        # Test connection before saving
        success, message = await test_livekit_connection(
            config.url, config.api_key, config.api_secret
        )

        if not success:
            return {
                "success": False,
                "error": f"Connection test failed: {message}"
            }

        # Save to .env file
        update_env_file({
            "LIVEKIT_URL": config.url,
            "LIVEKIT_API_KEY": config.api_key,
            "LIVEKIT_API_SECRET": config.api_secret,
        })

        # Mark setup step complete
        app_config = load_config()
        app_config.setdefault("setup", {})
        app_config["setup"].setdefault("steps_completed", {})
        app_config["setup"]["steps_completed"]["livekit"] = True
        save_config(app_config)

        # Reload credentials in livekit_service if available
        import lelamp.globals as g
        if g.livekit_service:
            g.livekit_service.reload_credentials()
            logger.info("LiveKit service credentials reloaded")

        room_name = get_room_name()

        return {
            "success": True,
            "message": "LiveKit configured successfully",
            "room_name": room_name,
            "restart_required": True,
        }

    except Exception as e:
        logger.error(f"Error configuring LiveKit: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/test")
async def test_connection():
    """
    Test current LiveKit configuration.

    Verifies that stored credentials can connect to LiveKit Cloud.
    """
    try:
        url = os.getenv("LIVEKIT_URL") or get_env_value("LIVEKIT_URL")
        api_key = os.getenv("LIVEKIT_API_KEY") or get_env_value("LIVEKIT_API_KEY")
        api_secret = os.getenv("LIVEKIT_API_SECRET") or get_env_value("LIVEKIT_API_SECRET")

        if not all([url, api_key, api_secret]):
            return {
                "success": False,
                "error": "LiveKit not configured. Please add credentials first."
            }

        success, message = await test_livekit_connection(url, api_key, api_secret)
        room_name = get_room_name()

        return {
            "success": success,
            "message": message,
            "room_name": room_name if success else None,
        }

    except Exception as e:
        logger.error(f"Error testing LiveKit: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/room-name")
async def get_device_room_name():
    """
    Get the room name for this device.

    Room name is based on device serial: lelamp_<serial>
    """
    try:
        room_name = get_room_name()
        serial = get_device_serial_short()

        return {
            "success": True,
            "room_name": room_name,
            "serial": serial,
        }

    except Exception as e:
        logger.error(f"Error getting room name: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/guide")
async def get_setup_guide():
    """
    Get LiveKit Cloud setup instructions.

    Returns step-by-step guide for users to get their credentials.
    """
    return {
        "success": True,
        "steps": [
            {
                "step": 1,
                "title": "Create LiveKit Cloud Account",
                "description": "Go to cloud.livekit.io and sign up for a free account.",
                "url": "https://cloud.livekit.io",
            },
            {
                "step": 2,
                "title": "Create a Project",
                "description": "After signing in, create a new project. You can name it 'LeLamp' or anything you prefer.",
            },
            {
                "step": 3,
                "title": "Get Your Credentials",
                "description": "In your project settings, find the API Keys section. Copy the WebSocket URL, API Key, and API Secret.",
            },
            {
                "step": 4,
                "title": "Enter Credentials Below",
                "description": "Paste your credentials in the form below. Your room will be automatically named based on your device.",
            },
        ],
        "room_name": get_room_name(),
        "free_tier_info": "LiveKit Cloud offers a generous free tier with 50GB of bandwidth per month.",
    }


@router.get("/viewer-token")
async def get_viewer_token(identity: str = "desktop_viewer"):
    """
    Generate a token to join the LiveKit room as a viewer/listener.

    Use this to connect from your desktop and listen to the audio stream.

    Usage:
    1. Get the token from this endpoint
    2. Go to https://meet.livekit.io or LiveKit Playground
    3. Use custom connection with the returned URL and token
    """
    try:
        import livekit.api as livekit_api

        url = os.getenv("LIVEKIT_URL") or get_env_value("LIVEKIT_URL")
        api_key = os.getenv("LIVEKIT_API_KEY") or get_env_value("LIVEKIT_API_KEY")
        api_secret = os.getenv("LIVEKIT_API_SECRET") or get_env_value("LIVEKIT_API_SECRET")

        if not all([url, api_key, api_secret]):
            return {
                "success": False,
                "error": "LiveKit not configured"
            }

        room_name = get_room_name()

        # Create access token for viewer
        token = livekit_api.AccessToken(api_key, api_secret)
        token.with_identity(identity)
        token.with_name(f"Viewer ({identity})")
        token.with_ttl(3600 * 24)  # 24 hour token

        # Grant permissions - can subscribe to audio/video but not publish
        token.with_grants(livekit_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_subscribe=True,
            can_publish=False,  # Viewer only, no publishing
        ))

        jwt = token.to_jwt()

        return {
            "success": True,
            "url": url,
            "room_name": room_name,
            "token": jwt,
            "identity": identity,
            "instructions": [
                "1. Go to https://meet.livekit.io",
                "2. Click 'Custom' in the connection dropdown",
                f"3. Enter URL: {url}",
                f"4. Enter Token: (the token field above)",
                "5. Click Connect to join as viewer",
                "",
                "Or use LiveKit Playground: https://agents-playground.livekit.io",
            ]
        }

    except ImportError:
        return {
            "success": False,
            "error": "livekit package not installed"
        }
    except Exception as e:
        logger.error(f"Error generating viewer token: {e}")
        return {
            "success": False,
            "error": str(e)
        }
