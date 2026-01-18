"""
Camera driver factory.

Auto-detects and creates the appropriate camera driver based on:
1. Explicit camera_type setting in config
2. Available device symlinks (/dev/usbcam_*)
3. Probing /dev/video* devices
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from .base import CameraDriver, CameraCapabilities
from .innomaker_driver import InnomakerDriver, InnomakerDNDriver
from .centerm_driver import CentermDriver
from .generic_driver import GenericDriver

logger = logging.getLogger(__name__)

# Known camera types and their symlinks
CAMERA_TYPES = {
    "innomaker": {
        "driver": InnomakerDriver,
        "symlink": "/dev/usbcam_inno",
        "name": "Innomaker U20CAM",
    },
    "innomaker_dn": {
        "driver": InnomakerDNDriver,
        "symlink": "/dev/usbcam_inno_dn",
        "name": "Innomaker D&N",
    },
    "centerm": {
        "driver": CentermDriver,
        "symlink": "/dev/usbcam_centerm",
        "name": "Centerm Camera",
    },
}


def get_camera_driver(
    camera_type: str = "auto",
    device_path: Optional[str] = None,
    resolution: Optional[Tuple[int, int]] = None,
    fps: Optional[int] = None,
) -> Optional[CameraDriver]:
    """
    Get the appropriate camera driver.

    Args:
        camera_type: Camera type - "auto", "innomaker", "innomaker_dn", "centerm", "generic"
        device_path: Optional explicit device path (overrides auto-detection)
        resolution: Optional resolution (width, height)
        fps: Optional FPS setting

    Returns:
        CameraDriver instance, or None if no camera found.
    """
    # Explicit device path
    if device_path:
        return _create_driver_for_path(camera_type, device_path, resolution, fps)

    # Explicit camera type (not auto)
    if camera_type != "auto" and camera_type in CAMERA_TYPES:
        info = CAMERA_TYPES[camera_type]
        symlink = info["symlink"]
        if Path(symlink).exists():
            return info["driver"](symlink, resolution, fps)
        logger.warning(f"Camera type {camera_type} specified but {symlink} not found")
        return None

    # Auto-detect: try known symlinks first
    for type_name, info in CAMERA_TYPES.items():
        symlink = info["symlink"]
        if Path(symlink).exists():
            logger.info(f"Auto-detected {info['name']} at {symlink}")
            return info["driver"](symlink, resolution, fps)

    # Fallback: try legacy /dev/usbcam
    if Path("/dev/usbcam").exists():
        logger.info("Found legacy /dev/usbcam, using generic driver")
        return GenericDriver("/dev/usbcam", resolution, fps)

    # Last resort: probe /dev/video* devices
    for i in range(10):  # Check video0 through video9
        video_path = f"/dev/video{i}"
        if Path(video_path).exists():
            # Skip Pi internal video devices (pispbe, rpi-hevc, etc.)
            try:
                name_path = Path(f"/sys/class/video4linux/video{i}/name")
                if name_path.exists():
                    name = name_path.read_text().strip()
                    if any(x in name.lower() for x in ["pispbe", "rpi-hevc", "bcm2835"]):
                        continue
            except Exception:
                pass

            # Try to open and read a frame
            driver = GenericDriver(video_path, resolution, fps)
            if driver.initialize():
                logger.info(f"Auto-detected camera at {video_path}")
                return driver
            driver.cleanup()

    logger.warning("No camera found")
    return None


def _create_driver_for_path(
    camera_type: str,
    device_path: str,
    resolution: Optional[Tuple[int, int]],
    fps: Optional[int],
) -> Optional[CameraDriver]:
    """Create a driver for a specific device path."""
    # Use specified type if known
    if camera_type in CAMERA_TYPES:
        driver_class = CAMERA_TYPES[camera_type]["driver"]
        return driver_class(device_path, resolution, fps)

    # Try to detect type from path
    if "inno_dn" in device_path or "innomaker_dn" in device_path:
        return InnomakerDNDriver(device_path, resolution, fps)
    elif "inno" in device_path or "innomaker" in device_path:
        return InnomakerDriver(device_path, resolution, fps)
    elif "centerm" in device_path:
        return CentermDriver(device_path, resolution, fps)

    # Fallback to generic
    return GenericDriver(device_path, resolution, fps)


def list_available_cameras() -> List[Dict[str, Any]]:
    """
    List all available cameras.

    Returns:
        List of dicts with camera info: {path, name, type, available}
    """
    cameras = []

    # Check known symlinks
    for type_name, info in CAMERA_TYPES.items():
        symlink = info["symlink"]
        if Path(symlink).exists():
            # Resolve symlink to actual device
            try:
                actual_device = Path(symlink).resolve()
            except Exception:
                actual_device = symlink

            cameras.append({
                "path": symlink,
                "actual_device": str(actual_device),
                "name": info["name"],
                "type": type_name,
                "available": True,
            })

    # Check legacy symlink
    if Path("/dev/usbcam").exists():
        # Check if it's already in the list (might be a symlink to a known camera)
        usbcam_resolved = str(Path("/dev/usbcam").resolve())
        already_listed = any(c.get("actual_device") == usbcam_resolved for c in cameras)

        if not already_listed:
            cameras.append({
                "path": "/dev/usbcam",
                "actual_device": usbcam_resolved,
                "name": "USB Camera (legacy)",
                "type": "generic",
                "available": True,
            })

    return cameras


def probe_camera(device_path: str) -> Optional[Dict[str, Any]]:
    """
    Probe a camera device to check if it works.

    Args:
        device_path: Path to video device

    Returns:
        Dict with camera info if working, None otherwise.
    """
    import cv2

    try:
        cap = cv2.VideoCapture(device_path)
        if not cap.isOpened():
            return None

        ret, frame = cap.read()
        if not ret or frame is None:
            cap.release()
            return None

        # Get actual properties
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))

        cap.release()

        # Try to get name from sysfs
        name = "Unknown Camera"
        if "/dev/video" in device_path:
            try:
                video_num = device_path.split("video")[-1]
                name_path = Path(f"/sys/class/video4linux/video{video_num}/name")
                if name_path.exists():
                    name = name_path.read_text().strip()
            except Exception:
                pass

        return {
            "path": device_path,
            "name": name,
            "working": True,
            "resolution": (width, height),
            "fps": fps,
        }

    except Exception as e:
        logger.debug(f"Error probing {device_path}: {e}")
        return None
