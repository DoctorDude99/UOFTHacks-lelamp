"""
RGB LED driver for Raspberry Pi 4 (and earlier models).

Uses rpi_ws281x library with PWM/DMA for high-speed LED control.
This is the traditional approach that works on Pi 1/2/3/4.
"""

from typing import List, Tuple
from .base import RGBDriver


class Rpi4Driver(RGBDriver):
    """
    RGB driver for Raspberry Pi 4 using PWM/DMA via rpi_ws281x.

    This driver uses the standard rpi_ws281x library which controls
    WS281x LEDs using PWM (Pulse Width Modulation) and DMA (Direct
    Memory Access) for precise timing without CPU intervention.

    Supported pins:
        - GPIO 12 (PWM0) - default for Pi4
        - GPIO 13 (PWM1)
        - GPIO 18 (PWM0)
        - GPIO 19 (PWM1)

    Note: Requires root/sudo for DMA access.
    """

    def __init__(
        self,
        led_count: int,
        led_pin: int = 12,
        led_freq_hz: int = 800000,
        led_dma: int = 10,
        led_brightness: int = 255,
        led_invert: bool = False,
        led_channel: int = 0,
    ):
        super().__init__(led_count)

        self.led_pin = led_pin
        self.led_freq_hz = led_freq_hz
        self.led_dma = led_dma
        self.led_invert = led_invert
        self.led_channel = led_channel
        # Enforce max brightness from base class
        self._brightness = min(led_brightness, self.MAX_BRIGHTNESS)

        self._strip = None

    def initialize(self) -> bool:
        """Initialize the PixelStrip hardware."""
        try:
            from rpi_ws281x import PixelStrip

            self._strip = PixelStrip(
                self.led_count,
                self.led_pin,
                self.led_freq_hz,
                self.led_dma,
                self.led_invert,
                self._brightness,
                self.led_channel,
            )
            self._strip.begin()
            self._initialized = True
            self.logger.info(
                f"RPi4 RGB driver initialized: {self.led_count} LEDs on GPIO {self.led_pin}"
            )
            return True

        except ImportError:
            self.logger.error(
                "rpi_ws281x library not installed. "
                "Install with: pip install rpi-ws281x"
            )
            return False
        except RuntimeError as e:
            if "sp" in str(e).lower():
                self.logger.error(
                    f"Failed to initialize LED strip: {e}. "
                    "Make sure to run with sudo for DMA access."
                )
            else:
                self.logger.error(f"Failed to initialize LED strip: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error initializing LED strip: {e}")
            return False

    def render(self, frame: List[Tuple[int, int, int]]) -> None:
        """Write frame to LED strip."""
        if not self._initialized or self._strip is None:
            return

        try:
            from rpi_ws281x import Color

            # Set all pixels
            for i, (r, g, b) in enumerate(frame):
                if i < self.led_count:
                    self._strip.setPixelColor(i, Color(r, g, b))

            # Push to hardware
            self._strip.show()

        except Exception as e:
            self.logger.error(f"Error rendering frame: {e}")

    def set_brightness(self, brightness: int) -> None:
        """Set hardware brightness (0-255, capped at MAX_BRIGHTNESS)."""
        # Enforce max brightness from base class to prevent overcurrent
        self._brightness = max(0, min(self.MAX_BRIGHTNESS, brightness))

        if self._strip is not None:
            self._strip.setBrightness(self._brightness)
            self._strip.show()
            self.logger.debug(f"Brightness set to {self._brightness} (max={self.MAX_BRIGHTNESS})")

    def cleanup(self) -> None:
        """Turn off LEDs and release resources."""
        if self._strip is not None:
            # Turn off all LEDs
            self.clear()
            self._strip = None

        self._initialized = False
        self.logger.info("RPi4 RGB driver cleaned up")
