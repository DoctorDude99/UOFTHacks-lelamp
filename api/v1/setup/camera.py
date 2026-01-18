"""
Camera setup API endpoints.

Provides endpoints for detecting and configuring cameras:
- List available camera devices
- Live camera preview (MJPEG stream)
- Camera selection and configuration
"""

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Generator

import cv2
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import load_config, save_config

router = APIRouter()
logger = logging.getLogger(__name__)

# Preview state
_preview_cap = None
_preview_lock = threading.Lock()


# =============================================================================
# Pydantic Models
# =============================================================================

class CameraSelectRequest(BaseModel):
    """Request to select a camera."""
    device: str
    camera_type: Optional[str] = "auto"


class EnableRequest(BaseModel):
    """Request to enable/disable camera."""
    enabled: bool


# =============================================================================
# Helper Functions
# =============================================================================

def get_available_cameras() -> List[Dict[str, Any]]:
    """
    Get list of available camera devices.

    Checks known symlinks and probes /dev/video* devices.
    """
    cameras = []

    # Known camera symlinks
    known_cameras = [
        {
            "symlink": "/dev/usbcam_inno",
            "name": "Innomaker U20CAM",
            "type": "innomaker",
            "has_mic": False,
        },
        {
            "symlink": "/dev/usbcam_inno_dn",
            "name": "Innomaker D&N",
            "type": "innomaker_dn",
            "has_mic": True,
        },
        {
            "symlink": "/dev/usbcam_centerm",
            "name": "Centerm Camera",
            "type": "centerm",
            "has_mic": True,
        },
        {
            "symlink": "/dev/usbcam",
            "name": "USB Camera (legacy)",
            "type": "generic",
            "has_mic": False,
        },
    ]

    seen_devices = set()

    # Check known symlinks
    for cam in known_cameras:
        path = Path(cam["symlink"])
        if path.exists():
            # Resolve to actual device
            try:
                actual = str(path.resolve())
                if actual in seen_devices:
                    continue
                seen_devices.add(actual)
            except Exception:
                actual = cam["symlink"]

            # Test if it works
            working = _test_camera(cam["symlink"])

            cameras.append({
                "path": cam["symlink"],
                "actual_device": actual,
                "name": cam["name"],
                "type": cam["type"],
                "has_mic": cam["has_mic"],
                "working": working,
            })

    # Probe additional /dev/video* devices
    for i in range(10):
        video_path = f"/dev/video{i}"
        if not Path(video_path).exists():
            continue

        # Skip already-seen devices
        try:
            actual = str(Path(video_path).resolve())
            if actual in seen_devices:
                continue
        except Exception:
            actual = video_path

        # Get device name from sysfs
        name = "Unknown Camera"
        try:
            name_path = Path(f"/sys/class/video4linux/video{i}/name")
            if name_path.exists():
                name = name_path.read_text().strip()
        except Exception:
            pass

        # Skip Pi internal devices
        if any(x in name.lower() for x in ["pispbe", "rpi-hevc", "bcm2835"]):
            continue

        # Test if it works
        working = _test_camera(video_path)
        if not working:
            continue

        seen_devices.add(actual)
        cameras.append({
            "path": video_path,
            "actual_device": actual,
            "name": name,
            "type": "generic",
            "has_mic": False,
            "working": working,
        })

    return cameras


def _test_camera(device_path: str) -> bool:
    """Test if a camera device works by trying to read a frame."""
    try:
        cap = cv2.VideoCapture(device_path)
        if not cap.isOpened():
            return False

        ret, frame = cap.read()
        cap.release()

        return ret and frame is not None
    except Exception:
        return False


def _generate_mjpeg_frames(device_path: str) -> Generator[bytes, None, None]:
    """
    Generate MJPEG frames for streaming.

    Yields frames as multipart/x-mixed-replace content.
    """
    cap = None
    try:
        cap = cv2.VideoCapture(device_path)
        if not cap.isOpened():
            logger.error(f"Failed to open camera at {device_path}")
            return

        # Set reasonable resolution for preview
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Encode as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )

            # Limit frame rate
            time.sleep(1/15)

    except GeneratorExit:
        pass
    except Exception as e:
        logger.error(f"Error generating frames: {e}")
    finally:
        if cap:
            cap.release()


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/status")
async def get_camera_status():
    """
    Check if any camera is available.

    Returns availability status and enabled state.
    """
    try:
        config = load_config()
        vision_config = config.get("vision", {})
        enabled = vision_config.get("enabled", True)

        cameras = get_available_cameras()
        working_cameras = [c for c in cameras if c.get("working", False)]

        return {
            "success": True,
            "enabled": enabled,
            "available": len(working_cameras) > 0,
            "camera_count": len(cameras),
            "working_count": len(working_cameras),
            "current_device": vision_config.get("camera_device"),
        }
    except Exception as e:
        logger.error(f"Error checking camera status: {e}")
        return {
            "success": False,
            "available": False,
            "error": str(e)
        }


@router.post("/enable")
async def set_camera_enabled(request: EnableRequest):
    """
    Enable or disable camera.

    Toggle for users who don't have or don't want camera.
    """
    try:
        config = load_config()
        config.setdefault("vision", {})
        config["vision"]["enabled"] = request.enabled

        # Also update face tracking
        config.setdefault("face_tracking", {})
        config["face_tracking"]["enabled"] = request.enabled

        save_config(config)

        return {
            "success": True,
            "enabled": request.enabled,
            "message": f"Camera {'enabled' if request.enabled else 'disabled'}"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/devices")
async def list_cameras():
    """
    List all available camera devices.

    Returns list of cameras with their paths, names, and working status.
    """
    try:
        cameras = get_available_cameras()
        return {
            "success": True,
            "cameras": cameras
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/preview")
async def camera_preview(device: str = Query(..., description="Camera device path")):
    """
    Get live MJPEG stream from camera.

    Use this endpoint as <img src="..."> to display live preview.
    """
    # Validate device path
    if not device.startswith("/dev/"):
        return {"success": False, "error": "Invalid device path"}

    if not Path(device).exists():
        return {"success": False, "error": f"Device not found: {device}"}

    return StreamingResponse(
        _generate_mjpeg_frames(device),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/snapshot")
async def camera_snapshot(device: str = Query(..., description="Camera device path")):
    """
    Get a single JPEG snapshot from camera.
    """
    try:
        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            return {"success": False, "error": "Failed to open camera"}

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return {"success": False, "error": "Failed to capture frame"}

        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            return {"success": False, "error": "Failed to encode frame"}

        from fastapi.responses import Response
        return Response(content=buffer.tobytes(), media_type="image/jpeg")

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/select")
async def select_camera(request: CameraSelectRequest):
    """
    Select a camera for use.

    Updates the vision config with the selected camera.
    """
    try:
        device = request.device
        camera_type = request.camera_type or "auto"

        # Validate device exists
        if not Path(device).exists():
            return {"success": False, "error": f"Device not found: {device}"}

        # Note: We don't re-test the camera here because the preview stream
        # may still be holding it open. The preview already proves it works.

        # Update config
        config = load_config()

        config.setdefault("vision", {})
        config["vision"]["enabled"] = True
        config["vision"]["camera_device"] = device
        config["vision"]["camera_type"] = camera_type

        # Mark setup step complete
        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"]["steps_completed"]["camera"] = True
        config["setup"].setdefault("camera", {})
        config["setup"]["camera"]["enabled"] = True
        config["setup"]["camera"]["tested"] = True

        save_config(config)

        return {
            "success": True,
            "device": device,
            "camera_type": camera_type,
            "message": "Camera selected"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/skip")
async def skip_camera_setup():
    """
    Skip camera setup.

    Disables camera features and marks step as complete.
    """
    try:
        config = load_config()

        # Disable vision
        config.setdefault("vision", {})
        config["vision"]["enabled"] = False

        # Disable face tracking
        config.setdefault("face_tracking", {})
        config["face_tracking"]["enabled"] = False

        # Mark setup step complete
        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"]["steps_completed"]["camera"] = True
        config["setup"].setdefault("camera", {})
        config["setup"]["camera"]["enabled"] = False
        config["setup"]["camera"]["tested"] = False

        save_config(config)

        return {
            "success": True,
            "message": "Camera setup skipped"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/config")
async def get_camera_config():
    """Get current camera configuration."""
    try:
        config = load_config()
        vision_config = config.get("vision", {})

        return {
            "success": True,
            "enabled": vision_config.get("enabled", False),
            "camera_type": vision_config.get("camera_type", "auto"),
            "camera_device": vision_config.get("camera_device"),
            "resolution": vision_config.get("resolution", [640, 480]),
            "fps": vision_config.get("fps", 30),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
