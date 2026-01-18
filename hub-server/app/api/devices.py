"""
Device Registration and Management API.

Endpoints:
- POST /register - Register a new device
- GET /{serial} - Get device info
- PUT /{serial} - Update device info
- POST /{serial}/heartbeat - Device heartbeat
- POST /{serial}/link - Link device to user account
- DELETE /{serial}/link - Unlink device from user
"""

import random
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import get_db, Device, generate_api_key

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class HardwareInfo(BaseModel):
    """Hardware information from device."""
    serial: Optional[str] = None
    serial_short: Optional[str] = None
    model: Optional[str] = None
    memory_mb: Optional[int] = None
    cpu_cores: Optional[int] = None
    architecture: Optional[str] = None
    os_version: Optional[str] = None
    kernel: Optional[str] = None
    hostname: Optional[str] = None
    lelamp_version: Optional[str] = None


class DeviceRegisterRequest(BaseModel):
    """Device registration request."""
    serial: str
    hardware_info: Optional[HardwareInfo] = None


class DeviceRegisterResponse(BaseModel):
    """Device registration response."""
    device_id: str
    serial: str
    api_key: str
    hub_url: str
    upload_interval_seconds: int = 300


class DeviceUpdateRequest(BaseModel):
    """Device update request."""
    hostname: Optional[str] = None
    lelamp_version: Optional[str] = None
    status: Optional[str] = None


class DeviceLinkRequest(BaseModel):
    """Device linking request."""
    linking_code: str


# =============================================================================
# Authentication Helpers
# =============================================================================

def verify_device_api_key(
    authorization: str = Header(None),
    x_device_serial: str = Header(None),
    db: Session = Depends(get_db)
) -> Device:
    """Verify device API key and return device."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Extract token from "Bearer <token>"
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization

    # Find device by API key
    device = db.query(Device).filter(Device.api_key == token).first()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Verify serial matches if provided
    if x_device_serial and device.serial != x_device_serial:
        raise HTTPException(status_code=401, detail="Serial mismatch")

    return device


def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    # Check for forwarded headers
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/register", response_model=DeviceRegisterResponse)
async def register_device(
    request: DeviceRegisterRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Register a new device or return existing registration.

    If device is already registered, returns existing API key.
    """
    serial = request.serial.strip()
    if not serial:
        raise HTTPException(status_code=400, detail="Serial number required")

    # Check if device already exists
    device = db.query(Device).filter(Device.serial == serial).first()

    if device:
        # Device already registered - update info and return
        if request.hardware_info:
            hw = request.hardware_info
            device.model = hw.model or device.model
            device.hostname = hw.hostname or device.hostname
            device.lelamp_version = hw.lelamp_version or device.lelamp_version
            device.os_version = hw.os_version or device.os_version
            device.kernel = hw.kernel or device.kernel
            device.memory_mb = hw.memory_mb or device.memory_mb
            device.cpu_cores = hw.cpu_cores or device.cpu_cores
            device.architecture = hw.architecture or device.architecture

        device.last_seen = datetime.utcnow()
        device.last_ip = get_client_ip(req)
        db.commit()

        return DeviceRegisterResponse(
            device_id=device.serial,
            serial=device.serial,
            api_key=device.api_key,
            hub_url=str(req.base_url),
            upload_interval_seconds=300
        )

    # Create new device
    api_key = generate_api_key()

    hw = request.hardware_info or HardwareInfo()

    device = Device(
        serial=serial,
        api_key=api_key,
        model=hw.model,
        hostname=hw.hostname or f"lelamp-{serial[-8:]}",
        lelamp_version=hw.lelamp_version,
        os_version=hw.os_version,
        kernel=hw.kernel,
        memory_mb=hw.memory_mb,
        cpu_cores=hw.cpu_cores,
        architecture=hw.architecture,
        status="active",
        last_seen=datetime.utcnow(),
        last_ip=get_client_ip(req)
    )

    db.add(device)
    db.commit()
    db.refresh(device)

    return DeviceRegisterResponse(
        device_id=device.serial,
        serial=device.serial,
        api_key=api_key,
        hub_url=str(req.base_url),
        upload_interval_seconds=300
    )


@router.get("/{serial}")
async def get_device(
    serial: str,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device_api_key)
):
    """Get device information."""
    target_device = db.query(Device).filter(Device.serial == serial).first()
    if not target_device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Only allow access to own device or if admin
    if device.serial != serial and not device.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "success": True,
        "device": target_device.to_dict()
    }


@router.put("/{serial}")
async def update_device(
    serial: str,
    request: DeviceUpdateRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device_api_key)
):
    """Update device information."""
    if device.serial != serial:
        raise HTTPException(status_code=403, detail="Can only update own device")

    if request.hostname:
        device.hostname = request.hostname
    if request.lelamp_version:
        device.lelamp_version = request.lelamp_version
    if request.status:
        device.status = request.status

    device.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "device": device.to_dict()}


@router.post("/{serial}/heartbeat")
async def device_heartbeat(
    serial: str,
    req: Request,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device_api_key)
):
    """Record device heartbeat."""
    if device.serial != serial:
        raise HTTPException(status_code=403, detail="Serial mismatch")

    device.last_seen = datetime.utcnow()
    device.last_ip = get_client_ip(req)
    device.status = "active"
    db.commit()

    return {
        "success": True,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/{serial}/linking-code")
async def get_linking_code(
    serial: str,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device_api_key)
):
    """Generate a 6-digit linking code for the device."""
    if device.serial != serial:
        raise HTTPException(status_code=403, detail="Serial mismatch")

    # Generate 6-digit code
    code = ''.join(random.choices(string.digits, k=6))

    # Set expiration (15 minutes)
    device.linking_code = code
    device.linking_code_expires = datetime.utcnow() + timedelta(minutes=15)
    db.commit()

    return {
        "success": True,
        "code": code,
        "expires_in_seconds": 900,
        "expires_at": device.linking_code_expires.isoformat()
    }


@router.post("/{serial}/link")
async def link_device_to_user(
    serial: str,
    request: DeviceLinkRequest,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Link a device to a user account.

    Requires Clerk JWT token in authorization header.
    """
    # Verify Clerk JWT (simplified - implement proper verification)
    # In production, use clerk-sdk-python or verify JWT manually
    user_id = None
    try:
        # Extract user ID from JWT claims
        # This is a placeholder - implement proper Clerk verification
        import jwt
        token = authorization.replace("Bearer ", "")
        # Decode without verification for now (implement proper verification!)
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    if not user_id:
        raise HTTPException(status_code=401, detail="Could not extract user ID")

    # Find device
    device = db.query(Device).filter(Device.serial == serial).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Verify linking code
    if device.linking_code != request.linking_code:
        raise HTTPException(status_code=400, detail="Invalid linking code")

    if device.linking_code_expires and device.linking_code_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Linking code expired")

    # Link device to user
    device.user_id = user_id
    device.linking_code = None
    device.linking_code_expires = None
    db.commit()

    return {
        "success": True,
        "user_id": user_id,
        "device_serial": serial,
        "message": "Device linked successfully"
    }


@router.delete("/{serial}/link")
async def unlink_device(
    serial: str,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """Unlink a device from user account."""
    # Verify user owns device
    user_id = None
    try:
        import jwt
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    device = db.query(Device).filter(Device.serial == serial).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to unlink this device")

    device.user_id = None
    db.commit()

    return {"success": True, "message": "Device unlinked"}


@router.get("/")
async def list_devices(
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0
):
    """List all registered devices (admin endpoint)."""
    devices = db.query(Device).offset(offset).limit(limit).all()
    total = db.query(Device).count()

    return {
        "success": True,
        "devices": [d.to_dict() for d in devices],
        "total": total,
        "limit": limit,
        "offset": offset
    }
