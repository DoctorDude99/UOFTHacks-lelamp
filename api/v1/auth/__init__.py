"""
Authentication API endpoints.

Provides auth configuration for the frontend.
"""

from fastapi import APIRouter

from api.deps import get_config

router = APIRouter()


@router.get("/config")
async def get_auth_config():
    """
    Get authentication configuration for the frontend.

    Returns the public auth settings (not secrets).
    """
    config = get_config()
    auth_config = config.get("auth", {})

    return {
        "success": True,
        "enabled": auth_config.get("enabled", False),
        "localBypass": auth_config.get("local_bypass", False),  # Default to False - require explicit opt-in
        "clerkPublishableKey": auth_config.get("clerk_publishable_key"),
        # Never expose the secret key!
    }


@router.get("/status")
async def get_auth_status():
    """
    Check if authentication is currently required.

    Used by frontend to determine if sign-in is needed.
    """
    config = get_config()
    auth_config = config.get("auth", {})

    return {
        "success": True,
        "authRequired": auth_config.get("enabled", False),
        "localBypassEnabled": auth_config.get("local_bypass", False),  # Default to False
    }
