"""
User Authentication and Management API.

Endpoints:
- GET /me - Get current user info
- GET /me/devices - Get user's linked devices
- POST /me/devices/{serial}/unlink - Unlink a device

Authentication is handled via Clerk JWT tokens.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import get_db, Device

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class UserDevice(BaseModel):
    """Device summary for user."""
    serial: str
    hostname: Optional[str] = None
    model: Optional[str] = None
    lelamp_version: Optional[str] = None
    status: str
    last_seen: Optional[str] = None


class UserInfo(BaseModel):
    """User information."""
    user_id: str
    email: Optional[str] = None
    devices: List[UserDevice] = []


# =============================================================================
# Authentication Helper
# =============================================================================

def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> dict:
    """
    Verify Clerk JWT and extract user info.

    In production, implement proper Clerk SDK verification.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    try:
        import jwt

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization

        # Decode JWT (without verification for now)
        # In production, verify with Clerk's public key
        payload = jwt.decode(token, options={"verify_signature": False})

        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        return {
            "user_id": user_id,
            "email": email,
            "claims": payload
        }

    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/me")
async def get_current_user_info(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current authenticated user information."""
    user_id = user["user_id"]

    # Get user's devices
    devices = db.query(Device).filter(Device.user_id == user_id).all()

    device_list = [
        UserDevice(
            serial=d.serial,
            hostname=d.hostname,
            model=d.model,
            lelamp_version=d.lelamp_version,
            status=d.status,
            last_seen=d.last_seen.isoformat() if d.last_seen else None
        )
        for d in devices
    ]

    return {
        "success": True,
        "user": UserInfo(
            user_id=user_id,
            email=user.get("email"),
            devices=device_list
        ).model_dump()
    }


@router.get("/me/devices")
async def get_user_devices(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all devices linked to current user."""
    user_id = user["user_id"]

    devices = db.query(Device).filter(Device.user_id == user_id).all()

    return {
        "success": True,
        "devices": [
            {
                "serial": d.serial,
                "hostname": d.hostname,
                "model": d.model,
                "lelamp_version": d.lelamp_version,
                "os_version": d.os_version,
                "status": d.status,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "registered_at": d.registered_at.isoformat() if d.registered_at else None
            }
            for d in devices
        ],
        "count": len(devices)
    }


@router.post("/me/devices/{serial}/unlink")
async def unlink_user_device(
    serial: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unlink a device from current user."""
    user_id = user["user_id"]

    device = db.query(Device).filter(Device.serial == serial).first()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.user_id != user_id:
        raise HTTPException(status_code=403, detail="Device not linked to your account")

    device.user_id = None
    db.commit()

    return {
        "success": True,
        "message": f"Device {serial} unlinked from your account"
    }


@router.get("/devices/{serial}/check-link")
async def check_device_link_status(
    serial: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if a device is linked to current user."""
    user_id = user["user_id"]

    device = db.query(Device).filter(Device.serial == serial).first()

    if not device:
        return {
            "success": True,
            "exists": False,
            "linked": False,
            "linked_to_me": False
        }

    return {
        "success": True,
        "exists": True,
        "linked": device.user_id is not None,
        "linked_to_me": device.user_id == user_id
    }
