"""
Generic camera driver.

Fallback driver for unknown camera hardware. Uses standard OpenCV settings
that should work with most UVC-compliant cameras.
"""

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from .base import CameraDriver, CameraCapabilities

logger = logging.getLogger(__name__)


class GenericDriver(CameraDriver):
    """
    Generic fallback camera driver.

    Works with most UVC-compliant USB cameras using standard OpenCV settings.
    """

    def __init__(self, device_path: str, resolution: Optional[Tuple[int, int]] = None, fps: Optional[int] = None):
        super().__init__(device_path, resolution, fps)
        self._detected_name = "Unknown Camera"

    @property
    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            name=self._detected_name,
            vendor_id="unknown",
            product_id="unknown",
            has_mic=False,  # Assume no mic for generic
            supported_resolutions=[
                (1920, 1080),
                (1280, 720),
                (640, 480),
                (320, 240),
            ],
            supported_fps=[30, 15, 10],
            supported_formats=["YUYV", "MJPEG"],
            default_resolution=(640, 480),
            default_fps=30,
        )

    def initialize(self) -> bool:
        """Initialize the camera with generic settings."""
        try:
            # Try to detect camera name from sysfs
            self._detect_camera_name()

            if self.device_path.startswith("/dev/"):
                self._cap = cv2.VideoCapture(self.device_path)
            else:
                try:
                    self._cap = cv2.VideoCapture(int(self.device_path))
                except ValueError:
                    self._cap = cv2.VideoCapture(self.device_path)

            if not self._cap.isOpened():
                logger.error(f"Failed to open camera at {self.device_path}")
                return False

            # Set resolution
            width, height = self.get_resolution()
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            # Set FPS
            self._cap.set(cv2.CAP_PROP_FPS, self.get_fps())

            # Reduce buffer size for lower latency
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Test read
            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.error(f"Camera opened but failed to read frame from {self.device_path}")
                self._cap.release()
                return False

            # Get actual resolution
            actual_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            self._initialized = True
            logger.info(f"Generic camera initialized: {self._detected_name} at {self.device_path} ({actual_width}x{actual_height})")
            return True

        except Exception as e:
            logger.error(f"Error initializing generic camera: {e}")
            if self._cap:
                self._cap.release()
            return False

    def _detect_camera_name(self) -> None:
        """Try to detect the camera name from sysfs."""
        try:
            # Extract video number from device path
            if "/dev/video" in self.device_path:
                video_num = self.device_path.split("video")[-1]
                name_path = f"/sys/class/video4linux/video{video_num}/name"

                from pathlib import Path
                path = Path(name_path)
                if path.exists():
                    self._detected_name = path.read_text().strip()
                    logger.debug(f"Detected camera name: {self._detected_name}")
        except Exception:
            pass  # Keep default name

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from the camera."""
        if not self._initialized or self._cap is None:
            return False, None

        try:
            ret, frame = self._cap.read()
            return ret, frame if ret else None
        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            return False, None

    def cleanup(self) -> None:
        """Release camera resources."""
        if self._cap:
            self._cap.release()
            self._cap = None
        self._initialized = False
        logger.info("Generic camera released")
