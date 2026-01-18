"""
Abstract base class for camera drivers.

Camera drivers provide a unified interface for different camera hardware,
similar to how RGB drivers handle different LED hardware.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any
import numpy as np


@dataclass
class CameraCapabilities:
    """Camera hardware capabilities."""
    name: str
    vendor_id: str
    product_id: str
    has_mic: bool
    supported_resolutions: List[Tuple[int, int]]
    supported_fps: List[int]
    supported_formats: List[str]  # e.g., ["MJPEG", "YUYV"]
    default_resolution: Tuple[int, int]
    default_fps: int


class CameraDriver(ABC):
    """
    Abstract base class for camera drivers.

    Provides a unified interface for different camera hardware (Innomaker, Centerm, etc.)
    with consistent methods for initialization, frame capture, and configuration.
    """

    def __init__(self, device_path: str, resolution: Optional[Tuple[int, int]] = None, fps: Optional[int] = None):
        """
        Initialize the camera driver.

        Args:
            device_path: Path to the video device (e.g., /dev/usbcam_inno)
            resolution: Optional resolution override (width, height)
            fps: Optional FPS override
        """
        self.device_path = device_path
        self._resolution = resolution
        self._fps = fps
        self._cap = None
        self._initialized = False

    @property
    @abstractmethod
    def capabilities(self) -> CameraCapabilities:
        """Get camera capabilities."""
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the camera hardware.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame from the camera.

        Returns:
            Tuple of (success, frame). Frame is BGR numpy array if success, None otherwise.
        """
        pass

    def get_resolution(self) -> Tuple[int, int]:
        """Get current resolution (width, height)."""
        if self._resolution:
            return self._resolution
        return self.capabilities.default_resolution

    def set_resolution(self, width: int, height: int) -> bool:
        """
        Set camera resolution.

        Args:
            width: Frame width
            height: Frame height

        Returns:
            True if resolution was set successfully.
        """
        self._resolution = (width, height)
        return True

    def get_fps(self) -> int:
        """Get current FPS setting."""
        if self._fps:
            return self._fps
        return self.capabilities.default_fps

    def set_fps(self, fps: int) -> bool:
        """
        Set camera FPS.

        Args:
            fps: Target frames per second

        Returns:
            True if FPS was set successfully.
        """
        self._fps = fps
        return True

    @abstractmethod
    def cleanup(self) -> None:
        """Release camera resources."""
        pass

    def is_initialized(self) -> bool:
        """Check if camera is initialized."""
        return self._initialized

    def get_info(self) -> Dict[str, Any]:
        """Get camera information as a dictionary."""
        caps = self.capabilities
        return {
            "name": caps.name,
            "device_path": self.device_path,
            "vendor_id": caps.vendor_id,
            "product_id": caps.product_id,
            "has_mic": caps.has_mic,
            "resolution": self.get_resolution(),
            "fps": self.get_fps(),
            "initialized": self._initialized,
        }
