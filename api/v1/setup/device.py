"""
Device Registration and Identity API endpoints.

Provides endpoints for:
- Getting device information
- Registering device with Hub
- Generating linking codes
- Checking registration status
"""

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import load_config, save_config
from lelamp.user_data import (
    get_device_serial,
    get_device_serial_short,
    get_device_info,
    get_lelamp_version,
    save_device_info,
    USER_DATA_DIR,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class DeviceInfo(BaseModel):
    """Device information response."""
    serial: str
    serial_short: str
    model: str
    hostname: str
    lelamp_version: str
    os_version: str
    kernel: str
    memory_mb: int
    registered: bool
    user_linked: bool


class HubRegistrationRequest(BaseModel):
    """Hub registration request."""
    hub_url: Optional[str] = None


class HubRegistrationResponse(BaseModel):
    """Hub registration response."""
    success: bool
    device_id: Optional[str] = None
    api_key_stored: bool = False
    message: str = ""


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/info")
async def get_device_info_endpoint():
    """
    Get device information including serial number.

    Serial number is always read from hardware for security.
    """
    try:
        info = get_device_info()

        # Check registration status
        config = load_config()
        device_config = config.get("device", {})

        return {
            "success": True,
            "device": {
                "serial": info.get("serial"),
                "serial_short": info.get("serial_short"),
                "model": info.get("model"),
                "hostname": info.get("platform", {}).get("node", "unknown"),
                "lelamp_version": get_lelamp_version(),
                "os_version": info.get("os", {}).get("name", "Unknown"),
                "kernel": info.get("kernel", "Unknown"),
                "memory_mb": info.get("memory_mb", 0),
                "cpu_cores": info.get("cpu", {}).get("cores", 0),
                "architecture": info.get("cpu", {}).get("architecture", "Unknown"),
                "registered": device_config.get("registered", False),
                "user_linked": device_config.get("user_linked", False),
            }
        }
    except Exception as e:
        logger.error(f"Error getting device info: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/register")
async def register_with_hub(request: HubRegistrationRequest):
    """
    Register this device with the Hub server.

    Sends device info to Hub and stores the returned API key.
    """
    try:
        import httpx

        config = load_config()
        datacollection_config = config.get("datacollection", {})

        hub_url = request.hub_url or datacollection_config.get("hub_url", "http://192.168.10.10:8000")

        # Get device info
        info = get_device_info()
        info["lelamp_version"] = get_lelamp_version()

        # Register with Hub
        response = httpx.post(
            f"{hub_url}/api/v1/devices/register",
            json={
                "serial": info.get("serial"),
                "hardware_info": {
                    "serial": info.get("serial"),
                    "serial_short": info.get("serial_short"),
                    "model": info.get("model"),
                    "memory_mb": info.get("memory_mb"),
                    "cpu_cores": info.get("cpu", {}).get("cores"),
                    "architecture": info.get("cpu", {}).get("architecture"),
                    "os_version": info.get("os", {}).get("name"),
                    "kernel": info.get("kernel"),
                    "hostname": info.get("platform", {}).get("node"),
                    "lelamp_version": info.get("lelamp_version"),
                }
            },
            timeout=30.0
        )

        if response.status_code == 200:
            result = response.json()

            # Store API key in .env
            api_key = result.get("api_key")
            if api_key:
                env_path = USER_DATA_DIR / ".env"
                env_path.parent.mkdir(parents=True, exist_ok=True)

                # Read existing .env
                existing_content = ""
                if env_path.exists():
                    existing_content = env_path.read_text()
                    # Remove existing HUB_API_KEY line
                    lines = [l for l in existing_content.splitlines() if not l.startswith("HUB_API_KEY=")]
                    existing_content = "\n".join(lines)

                # Append API key
                with open(env_path, "w") as f:
                    if existing_content:
                        f.write(existing_content.rstrip() + "\n")
                    f.write(f"HUB_API_KEY={api_key}\n")

                env_path.chmod(0o600)

            # Update config
            config.setdefault("device", {})
            config["device"]["registered"] = True
            config["device"]["hub_url"] = hub_url

            config.setdefault("datacollection", {})
            config["datacollection"]["hub_url"] = hub_url

            save_config(config)

            return {
                "success": True,
                "device_id": result.get("device_id"),
                "api_key_stored": bool(api_key),
                "message": "Device registered successfully"
            }
        else:
            return {
                "success": False,
                "error": f"Hub returned status {response.status_code}",
                "details": response.text
            }

    except httpx.ConnectError:
        return {
            "success": False,
            "error": "Could not connect to Hub server",
            "message": "Make sure the Hub server is running"
        }
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/registration-status")
async def get_registration_status():
    """Check if device is registered with Hub."""
    config = load_config()
    device_config = config.get("device", {})

    # Check for API key
    has_api_key = False
    env_path = USER_DATA_DIR / ".env"
    if env_path.exists():
        content = env_path.read_text()
        has_api_key = "HUB_API_KEY=" in content and "HUB_API_KEY=\n" not in content

    return {
        "success": True,
        "registered": device_config.get("registered", False),
        "has_api_key": has_api_key,
        "hub_url": device_config.get("hub_url"),
        "user_linked": device_config.get("user_linked", False)
    }


@router.get("/linking-code")
async def get_linking_code():
    """
    Generate a 6-digit linking code for this device.

    The code can be used to link this device to a user account.
    """
    try:
        import httpx

        config = load_config()
        datacollection_config = config.get("datacollection", {})
        hub_url = datacollection_config.get("hub_url", "http://192.168.10.10:8000")

        # Get API key
        api_key = None
        env_path = USER_DATA_DIR / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("HUB_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

        if not api_key:
            return {
                "success": False,
                "error": "Device not registered with Hub",
                "message": "Register device first"
            }

        serial = get_device_serial()

        # Request linking code from Hub
        response = httpx.get(
            f"{hub_url}/api/v1/devices/{serial}/linking-code",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Device-Serial": serial
            },
            timeout=30.0
        )

        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "code": result.get("code"),
                "expires_in_seconds": result.get("expires_in_seconds"),
                "expires_at": result.get("expires_at")
            }
        else:
            return {
                "success": False,
                "error": f"Hub returned status {response.status_code}"
            }

    except Exception as e:
        logger.error(f"Error getting linking code: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/save-info")
async def save_device_info_endpoint():
    """Save current device info to disk."""
    try:
        path = save_device_info()
        return {
            "success": True,
            "path": str(path),
            "message": "Device info saved"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
