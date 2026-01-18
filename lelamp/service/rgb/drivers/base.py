"""
Abstract base class for RGB LED drivers.

All RGB drivers must implement this interface to work with RGBService.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple
import logging


class RGBDriver(ABC):
    """
    Abstract base class for RGB LED hardware drivers.

    Implementations handle the hardware-specific details of controlling
    WS281x-family addressable RGB LEDs on different Raspberry Pi models.
    """

    # Maximum brightness (0-255 scale)
    # Actual brightness is controlled via config's led_brightness setting
    MAX_BRIGHTNESS = 255

    def __init__(self, led_count: int):
        self.led_count = led_count
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialized = False
        self._brightness = min(255, self.MAX_BRIGHTNESS)  # Default to max allowed

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the LED hardware.

        Returns:
            True if initialization was successful, False otherwise.
        """
        pass

    @abstractmethod
    def render(self, frame: List[Tuple[int, int, int]]) -> None:
        """
        Write a frame to the LED strip.

        Args:
            frame: List of (R, G, B) tuples, one per LED.
                   Values are 0-255 for each channel.
        """
        pass

    @abstractmethod
    def set_brightness(self, brightness: int) -> None:
        """
        Set the hardware brightness level.

        Args:
            brightness: Brightness level 0-255.
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """
        Release hardware resources and turn off LEDs.

        Called when the service is stopped.
        """
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if the driver has been successfully initialized."""
        return self._initialized

    @property
    def brightness(self) -> int:
        """Get current brightness level (0-255)."""
        return self._brightness

    def clear(self) -> None:
        """Turn off all LEDs (convenience method)."""
        black_frame = [(0, 0, 0)] * self.led_count
        self.render(black_frame)

    def fill(self, color: Tuple[int, int, int]) -> None:
        """Fill all LEDs with a single color (convenience method)."""
        frame = [color] * self.led_count
        self.render(frame)

    def __enter__(self):
        """Context manager entry."""
        if not self._initialized:
            self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()
        return False
