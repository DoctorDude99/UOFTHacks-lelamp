"""
Innomaker camera drivers.

Supports:
- Innomaker U20CAM-1080p-S1 (video only)
- Innomaker U20CAM-1080PD&N-S1 (Day/Night with mic)
"""

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from .base import CameraDriver, CameraCapabilities

logger = logging.getLogger(__name__)


class InnomakerDriver(CameraDriver):
    """
    Driver for Innomaker U20CAM-1080p-S1 camera (video only).

    Device path: /dev/usbcam_inno
    Vendor: Sonix Technology (0c45)
    Product: 6366
    """

    @property
    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            name="Innomaker U20CAM-1080p-S1",
            vendor_id="0c45",
            product_id="6366",
            has_mic=False,
            supported_resolutions=[
                (1920, 1080),
                (1280, 720),
                (640, 480),
                (320, 240),
            ],
            supported_fps=[30, 15, 10],
            supported_formats=["MJPEG", "YUYV"],
            default_resolution=(640, 480),
            default_fps=30,
        )

    def initialize(self) -> bool:
        """Initialize the camera with optimal settings for Innomaker."""
        try:
            # Try device path first, then try as integer index
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

            # Use MJPEG format for better performance
            self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            # Reduce buffer size for lower latency
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Test read
            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.error(f"Camera opened but failed to read frame from {self.device_path}")
                self._cap.release()
                return False

            self._initialized = True
            logger.info(f"Innomaker camera initialized at {self.device_path} ({width}x{height} @ {self.get_fps()}fps)")
            return True

        except Exception as e:
            logger.error(f"Error initializing Innomaker camera: {e}")
            if self._cap:
                self._cap.release()
            return False

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
        logger.info("Innomaker camera released")


class InnomakerDNDriver(CameraDriver):
    """
    Driver for Innomaker U20CAM-1080PD&N-S1 camera (Day/Night with mic).

    Device path: /dev/usbcam_inno_dn
    Vendor: Realtek (0bda)
    Product: 5856
    """

    @property
    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            name="Innomaker U20CAM-1080PD&N-S1",
            vendor_id="0bda",
            product_id="5856",
            has_mic=True,
            supported_resolutions=[
                (1920, 1080),
                (1280, 720),
                (640, 480),
                (320, 240),
            ],
            supported_fps=[30, 15, 10],
            supported_formats=["MJPEG", "YUYV"],
            default_resolution=(640, 480),
            default_fps=30,
        )

    def initialize(self) -> bool:
        """Initialize the Day/Night camera with optimal settings."""
        try:
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

            # Use MJPEG format for better performance
            self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            # Reduce buffer size for lower latency
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Test read
            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.error(f"Camera opened but failed to read frame from {self.device_path}")
                self._cap.release()
                return False

            self._initialized = True
            logger.info(f"Innomaker D&N camera initialized at {self.device_path} ({width}x{height} @ {self.get_fps()}fps)")
            return True

        except Exception as e:
            logger.error(f"Error initializing Innomaker D&N camera: {e}")
            if self._cap:
                self._cap.release()
            return False

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
        logger.info("Innomaker D&N camera released")
