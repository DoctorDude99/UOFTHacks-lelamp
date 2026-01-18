"""
RGB LED driver for Raspberry Pi 5 using PIO (Programmable I/O).

Uses the Adafruit NeoPixel library with Pi 5 PIO support.
This is the recommended method for WS2812B LEDs on Pi 5.

REQUIREMENTS:
- Pi 5 with PIO support (firmware update may be needed if /dev/pio0 doesn't exist)
- pip install adafruit-circuitpython-neopixel adafruit-blinka-raspberry-pi5-neopixel

WIRING:
- Connect LED data line to any GPIO (default GPIO 10)
- Connect LED ground to Pi ground
- Connect LED power to 3.3V-5V power supply
- If using external power, connect external GND to Pi GND
"""

from typing import List, Tuple
from .base import RGBDriver


class Pi5PioDriver(RGBDriver):
    """
    RGB driver for Raspberry Pi 5 using PIO-based NeoPixel control.

    This driver uses the Adafruit CircuitPython NeoPixel library with
    the Pi 5 specific PIO backend, which provides hardware-accurate
    timing for WS2812B LEDs.

    Advantages:
        - Hardware-accurate timing via PIO
        - Works on any GPIO pin
        - No kernel module required
        - Officially supported by Adafruit

    Requirements:
        - Raspberry Pi 5 with PIO support (/dev/pio0 must exist)
        - adafruit-circuitpython-neopixel
        - adafruit-blinka-raspberry-pi5-neopixel
    """

    def __init__(
        self,
        led_count: int,
        led_pin: int = 10,
        led_brightness: int = 255,
        pixel_order: str = "GRB",
        auto_write: bool = False,
    ):
        """
        Initialize Pi 5 PIO driver.

        Args:
            led_count: Number of LEDs in the strip
            led_pin: GPIO pin number (BCM numbering, default 10)
            led_brightness: Brightness 0-255
            pixel_order: Color order (GRB for most WS2812, RGB for some)
            auto_write: If True, write to LEDs on every pixel change
        """
        super().__init__(led_count)

        self._pin_num = led_pin
        # Enforce max brightness from base class
        self._brightness = min(led_brightness, self.MAX_BRIGHTNESS)
        self._pixel_order_str = pixel_order.upper()
        self._auto_write = auto_write

        self._pixels = None
        self._board_pin = None

    def _check_pio_available(self) -> bool:
        """Check if PIO device is available."""
        import os
        if not os.path.exists("/dev/pio0"):
            self.logger.error(
                "PIO device /dev/pio0 not found. "
                "Pi 5 firmware update may be needed for PIO support."
            )
            return False
        return True

    def _get_board_pin(self, pin_num: int):
        """Get board pin object for GPIO number."""
        import board
        pin_map = {
            0: board.D0, 1: board.D1, 2: board.D2, 3: board.D3,
            4: board.D4, 5: board.D5, 6: board.D6, 7: board.D7,
            8: board.D8, 9: board.D9, 10: board.D10, 11: board.D11,
            12: board.D12, 13: board.D13, 14: board.D14, 15: board.D15,
            16: board.D16, 17: board.D17, 18: board.D18, 19: board.D19,
            20: board.D20, 21: board.D21, 22: board.D22, 23: board.D23,
            24: board.D24, 25: board.D25, 26: board.D26, 27: board.D27,
        }
        return pin_map.get(pin_num, board.D10)

    def initialize(self) -> bool:
        """Initialize the NeoPixel PIO hardware."""
        import time

        # Clean up any previous instance first (important after crashes)
        if self._pixels is not None:
            self.logger.warning("Previous NeoPixel instance exists, cleaning up first...")
            self.cleanup()
            time.sleep(0.2)  # Give PIO time to release

        if not self._check_pio_available():
            return False

        try:
            self.logger.info(f"Initializing Pi5 PIO driver for {self.led_count} LEDs on GPIO {self._pin_num}...")

            import board
            import neopixel

            # Get board pin
            self._board_pin = self._get_board_pin(self._pin_num)
            self.logger.debug(f"Board pin resolved: {self._board_pin}")

            # Get pixel order constant
            if self._pixel_order_str == "RGB":
                order = neopixel.RGB
            elif self._pixel_order_str == "RGBW":
                order = neopixel.RGBW
            elif self._pixel_order_str == "GRBW":
                order = neopixel.GRBW
            else:
                order = neopixel.GRB  # Default for WS2812

            self.logger.debug(f"Creating NeoPixel object with brightness={self._brightness}/255...")

            # Create NeoPixel object
            self._pixels = neopixel.NeoPixel(
                self._board_pin,
                self.led_count,
                brightness=self._brightness / 255.0,
                auto_write=self._auto_write,
                pixel_order=order,
            )

            # Brief pause after creation
            time.sleep(0.05)

            # Test with a quick black frame to verify communication
            self.logger.debug("Testing LED communication with black frame...")
            self._pixels.fill((0, 0, 0))
            self._pixels.show()

            self._initialized = True
            self.logger.info(
                f"Pi5 PIO RGB driver initialized: {self.led_count} LEDs on GPIO {self._pin_num}"
            )
            return True

        except ImportError as e:
            self.logger.error(
                f"NeoPixel library not installed: {e}. "
                "Install with: pip install adafruit-circuitpython-neopixel adafruit-blinka-raspberry-pi5-neopixel"
            )
            return False
        except PermissionError as e:
            self.logger.error(
                f"Permission denied accessing PIO: {e}. "
                "Check /dev/pio0 permissions or run with sudo."
            )
            return False
        except OSError as e:
            self.logger.error(
                f"OS error during initialization (PIO/GPIO conflict?): {e}. "
                "Try rebooting the Pi to reset GPIO state."
            )
            self._cleanup_on_error()
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Pi5 PIO driver: {e}")
            self._cleanup_on_error()
            return False

    def _cleanup_on_error(self):
        """Minimal cleanup after initialization failure."""
        if self._pixels is not None:
            try:
                self._pixels.deinit()
            except Exception:
                pass
            self._pixels = None
        self._initialized = False

    def render(self, frame: List[Tuple[int, int, int]]) -> None:
        """Write frame to LED strip via PIO."""
        if not self._initialized or self._pixels is None:
            return

        try:
            # Set all pixels
            for i, (r, g, b) in enumerate(frame):
                if i < self.led_count:
                    self._pixels[i] = (r, g, b)

            # Push to hardware
            self._pixels.show()

        except OSError as e:
            # PIO/GPIO errors - these can crash the Pi if we keep hammering
            self.logger.error(f"PIO/GPIO error rendering frame: {e}")
            # Brief pause to prevent rapid error loops
            import time
            time.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Error rendering frame: {e}")

    def set_brightness(self, brightness: int) -> None:
        """Set hardware brightness (0-255, capped at MAX_BRIGHTNESS)."""
        # Enforce max brightness from base class to prevent overcurrent
        self._brightness = max(0, min(self.MAX_BRIGHTNESS, brightness))

        if self._pixels is not None:
            self._pixels.brightness = self._brightness / 255.0
            self.logger.debug(f"Brightness set to {self._brightness} (max={self.MAX_BRIGHTNESS})")

    def cleanup(self) -> None:
        """Turn off LEDs and release resources."""
        if self._pixels is not None:
            # Turn off all LEDs
            try:
                self._pixels.fill((0, 0, 0))
                self._pixels.show()
            except Exception as e:
                self.logger.warning(f"Error turning off LEDs during cleanup: {e}")

            # Deinit neopixel - this properly releases PIO resources
            try:
                self._pixels.deinit()
            except Exception as e:
                self.logger.warning(f"Error deinit neopixel: {e}")

            self._pixels = None

        # NOTE: Do NOT try to manually release GPIO via lgpio!
        # The neopixel library manages PIO resources internally.
        # Manually calling lgpio to release pins causes conflicts and crashes.

        import time
        time.sleep(0.05)  # Brief pause to let PIO resources release

        self._initialized = False
        self.logger.info("Pi5 PIO RGB driver cleaned up")
