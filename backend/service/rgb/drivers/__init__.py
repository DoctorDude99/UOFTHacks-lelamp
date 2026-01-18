"""
RGB LED Driver Factory

Provides automatic driver selection based on Raspberry Pi version.

Supported drivers:
- pio: PIO-based driver for Pi 5 (uses adafruit neopixel with PIO, GPIO 10)
- rpi4: PWM-based driver for Pi 3/4 (uses rpi_ws281x)
- simulator: No-op driver for development/testing
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import RGBDriver

logger = logging.getLogger(__name__)


def get_driver(
    led_count: int,
    led_pin: int = 10,
    led_freq_hz: int = 800000,
    led_dma: int = 10,
    led_brightness: int = 255,
    led_invert: bool = False,
    led_channel: int = 0,
    force_driver: Optional[str] = None,
    pixel_order: str = "GRB",
) -> "RGBDriver":
    """
    Factory function to get the appropriate RGB driver for this Pi.

    Args:
        led_count: Number of LEDs in the strip
        led_pin: GPIO pin (default 10 for Pi5 PIO/SPI)
        led_freq_hz: LED signal frequency (800kHz for WS2812)
        led_dma: DMA channel (10 for Pi4, may differ for Pi5)
        led_brightness: Hardware brightness (0-255)
        led_invert: Invert signal (for level shifters)
        led_channel: PWM channel
        force_driver: Override auto-detection ("pio", "rpi4", "simulator")
        pixel_order: Color order for LEDs (GRB, RGB, RGBW, GRBW)

    Returns:
        Appropriate RGBDriver instance for the platform
    """
    from lelamp.user_data import get_pi_version, get_memory_mb

    # Allow forcing a specific driver
    if force_driver:
        driver_name = force_driver.lower()
    else:
        pi_version = get_pi_version()
        memory_mb = get_memory_mb()

        logger.info(f"Detected Pi version: {pi_version}, Memory: {memory_mb}MB")

        if pi_version == 5:
            # Pi 5 uses PIO driver (works on any GPIO, default GPIO 10)
            driver_name = "pio"
        elif pi_version in (3, 4):
            driver_name = "rpi4"
        else:
            # Non-Pi or unknown - use simulator
            logger.warning("Unknown platform, using simulator driver")
            driver_name = "simulator"

    # Import and instantiate the appropriate driver
    if driver_name == "pio":
        # Pi 5 PIO driver - hardware-accurate timing via RP1 PIO
        try:
            from .pi5_pio_driver import Pi5PioDriver
            driver = Pi5PioDriver(
                led_count=led_count,
                led_pin=led_pin,
                led_brightness=led_brightness,
                pixel_order=pixel_order,
                auto_write=False,
            )
            if driver.initialize():
                logger.info(f"Using Pi5 PIO RGB driver (GPIO {led_pin})")
                return driver
            else:
                logger.error("Pi5 PIO driver failed to initialize")
                driver.cleanup()
        except Exception as e:
            logger.error(f"Pi5 PIO driver error: {e}")
        # Fall back to simulator
        driver_name = "simulator"

    if driver_name == "rpi4":
        try:
            from .rpi4_driver import Rpi4Driver
            logger.info("Using RPi4 RGB driver (PWM/DMA)")
            return Rpi4Driver(
                led_count=led_count,
                led_pin=led_pin,
                led_freq_hz=led_freq_hz,
                led_dma=led_dma,
                led_brightness=led_brightness,
                led_invert=led_invert,
                led_channel=led_channel,
            )
        except ImportError as e:
            logger.error(f"Failed to import RPi4 driver: {e}")
            logger.warning("Falling back to simulator driver")
            driver_name = "simulator"

    # Fallback to simulator
    from .simulator_driver import SimulatorDriver
    logger.info("Using simulator RGB driver (no hardware)")
    return SimulatorDriver(led_count=led_count)


__all__ = ["get_driver"]
