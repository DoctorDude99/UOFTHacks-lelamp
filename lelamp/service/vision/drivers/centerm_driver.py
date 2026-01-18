"""
Centerm camera driver.

Supports Centerm Camera (Alcor Micro) with built-in microphone.
"""

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from .base import CameraDriver, CameraCapabilities

logger = logging.getLogger(__name__)


class CentermDriver(CameraDriver):
    """
    Driver for Centerm Camera (Alcor Micro) with mic.

    Device path: /dev/usbcam_centerm
    Vendor: Alcor Micro (2b46)
    Product: bd01
    """

    @property
    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            name="Centerm Camera",
            vendor_id="2b46",
            product_id="bd01",
            has_mic=True,
            supported_resolutions=[
                (640, 480),
                (320, 240),
            ],
            supported_fps=[30, 15],
            supported_formats=["YUYV"],
            default_resolution=(640, 480),
            default_fps=30,
        )

    def initialize(self) -> bool:
        """Initialize the Centerm camera."""
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

            # Centerm typically uses YUYV format
            # Let OpenCV handle the conversion
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Test read
            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.error(f"Camera opened but failed to read frame from {self.device_path}")
                self._cap.release()
                return False

            self._initialized = True
            logger.info(f"Centerm camera initialized at {self.device_path} ({width}x{height} @ {self.get_fps()}fps)")
            return True

        except Exception as e:
            logger.error(f"Error initializing Centerm camera: {e}")
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
        logger.info("Centerm camera released")
