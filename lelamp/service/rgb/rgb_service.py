from typing import Any, List, Union, Optional, Tuple
from ..base import ServiceBase
from .rgb_controller import RGBController
from .sequences import get_animation, list_animations
from .drivers import get_driver
from .drivers.base import RGBDriver


class RGBService(ServiceBase):
    """
    RGB LED service with automatic driver selection.

    Supports:
        - Raspberry Pi 4 (PWM/DMA via rpi_ws281x)
        - Raspberry Pi 5 (kernel module via rpi_ws281x 6.0+)
        - Simulator mode for development
    """

    def __init__(self,
                 led_count: int = 93,
                 led_pin: int = 10,
                 led_freq_hz: int = 800000,
                 led_dma: int = 10,
                 led_brightness: int = 25,
                 led_invert: bool = False,
                 led_channel: int = 0,
                 rings: Optional[List[dict]] = None,
                 default_animation: str = "aura_glow",
                 default_color: Tuple[int, int, int] = (0, 0, 0),
                 force_driver: Optional[str] = None):
        super().__init__("rgb")

        self.led_count = led_count
        # Brightness comes from config (0-100 percentage)
        self._brightness_percent = max(0, min(100, led_brightness))
        # Convert brightness from 0-100 percentage to 0-255 for hardware
        brightness_255 = int((self._brightness_percent / 100) * 255)

        # Get appropriate driver for this platform
        # Note: get_driver() now tests initialization and falls back to working drivers
        self.driver: RGBDriver = get_driver(
            led_count=led_count,
            led_pin=led_pin,
            led_freq_hz=led_freq_hz,
            led_dma=led_dma,
            led_brightness=brightness_255,
            led_invert=led_invert,
            led_channel=led_channel,
            force_driver=force_driver,
        )

        # Initialize the driver if not already initialized (for non-spi drivers)
        if not self.driver._initialized:
            if not self.driver.initialize():
                self.logger.error("Failed to initialize RGB driver")
                # Continue anyway - service can still receive events
                # (useful for debugging or when RGB is optional)

        # Initialize RGB controller
        self.controller = RGBController(led_count=led_count)

        # Sync brightness to controller (software-level dimming)
        self.controller.set_brightness(led_brightness / 100.0)

        # Set up ring structure if provided
        if rings:
            start_idx = rings[0]['start']
            end_idx = rings[-1]['end']
            self.controller.set_led_range(start_idx, end_idx, rings)

        # Set default color
        self.controller.set_color(default_color, transition=False)

        # Store default animation
        self.default_animation = default_animation

        # Track current animation name
        self._current_animation = default_animation

        # Set up callback for controller to render via driver
        self.controller.set_render_callback(self._render_frame_to_strip)

        # Lock to prevent simultaneous renders
        import threading
        self._render_lock = threading.Lock()

        # Sleep mode - blocks all RGB changes when enabled
        self._sleep_mode = False

        # Ensure LEDs start OFF (prevents random white on power-up)
        self.clear()

    def _render_frame_to_strip(self, frame: List[Tuple[int, int, int]]):
        """Callback to render a frame via the hardware driver"""
        # Use lock to ensure only one render happens at a time
        with self._render_lock:
            try:
                # Render via driver
                self.driver.render(frame)
                # No delay needed - the driver handles timing internally
                # WS2812B @ 800KHz: ~30µs per LED = ~3ms for 93 LEDs
                # Driver's render() is blocking until data is sent
            except Exception as e:
                self.logger.error(f"Error rendering frame: {e}")

    def set_sleep_mode(self, enabled: bool):
        """Enable or disable sleep mode - blocks all RGB changes when enabled"""
        self._sleep_mode = enabled
        if enabled:
            # Stop any running animations and turn off LEDs
            self.controller.stop_animation()
            self.clear()
        print(f"🔒 RGB SERVICE: Sleep mode set to {enabled}")

    def set_brightness(self, brightness_percent: int):
        """Set LED brightness (0-100 percent)"""
        brightness_percent = max(0, min(100, brightness_percent))
        self._brightness_percent = brightness_percent
        brightness_255 = int((brightness_percent / 100) * 255)

        # Set hardware brightness via driver
        self.driver.set_brightness(brightness_255)

        # Also sync to controller for software-level brightness
        self.controller.set_brightness(brightness_percent / 100.0)

        self.logger.info(f"Set RGB brightness to {brightness_percent}% (hw={brightness_255}/255)")

    def get_brightness(self) -> int:
        """Get current brightness (0-100 percent)"""
        return self._brightness_percent

    def handle_event(self, event_type: str, payload: Any):
        # Block all events in sleep mode EXCEPT turning off LEDs (solid black)
        if self._sleep_mode:
            # Allow turning off LEDs (solid black) even in sleep mode
            is_turn_off = (event_type == "solid" and
                          isinstance(payload, tuple) and
                          payload == (0, 0, 0))
            if not is_turn_off:
                self.logger.info(f"🚫 RGB SERVICE: Blocked event '{event_type}' - in sleep mode")
                return

        if event_type == "solid":
            self._handle_solid(payload)
        elif event_type == "paint":
            self._handle_paint(payload)
        elif event_type == "animation":
            self._handle_animation(payload)
        elif event_type == "set_color":
            self._handle_set_color(payload)
        elif event_type == "stop_animation":
            self._handle_stop_animation()
        elif event_type == "brightness":
            self.set_brightness(int(payload))
        else:
            self.logger.warning(f"Unknown event type: {event_type}")
    
    def _handle_solid(self, color_code: Union[int, tuple]):
        """Fill entire strip with single color (legacy compatibility)"""
        if isinstance(color_code, tuple) and len(color_code) == 3:
            color_tuple = color_code
        elif isinstance(color_code, int):
            # Convert int to RGB tuple
            r = (color_code >> 16) & 0xFF
            g = (color_code >> 8) & 0xFF
            b = color_code & 0xFF
            color_tuple = (r, g, b)
        else:
            self.logger.error(f"Invalid color format: {color_code}")
            return

        # Stop any running animation and set solid color
        self.controller.stop_animation()
        self.controller.set_color(color_tuple, transition=False)
        frame = [(0, 0, 0)] * self.led_count
        for i in range(self.controller._active_led_start, self.controller._active_led_end + 1):
            frame[i] = color_tuple
        self.controller._update_frame(frame)
        self._current_animation = "solid"
        self.logger.debug(f"Applied solid color: {color_code}")
    
    def _handle_paint(self, colors: List[Union[int, tuple]]):
        """Set individual pixel colors from array (legacy compatibility)"""
        if not isinstance(colors, list):
            self.logger.error(f"Paint payload must be a list, got: {type(colors)}")
            return

        # Stop any running animation
        self.controller.stop_animation()

        max_pixels = min(len(colors), self.led_count)
        frame = [(0, 0, 0)] * self.led_count

        for i in range(max_pixels):
            color_code = colors[i]
            if isinstance(color_code, tuple) and len(color_code) == 3:
                frame[i] = color_code
            elif isinstance(color_code, int):
                # Convert int to RGB
                r = (color_code >> 16) & 0xFF
                g = (color_code >> 8) & 0xFF
                b = color_code & 0xFF
                frame[i] = (r, g, b)
            else:
                self.logger.warning(f"Invalid color at index {i}: {color_code}")
                continue

        self.controller._update_frame(frame)
        self.logger.debug(f"Applied paint pattern with {max_pixels} colors")

    def _handle_animation(self, payload: dict):
        """Start an RGB animation"""
        animation_name = payload.get("name")
        color = payload.get("color")
        duration = payload.get("duration")

        animation_func = get_animation(animation_name)
        if not animation_func:
            self.logger.error(f"Unknown animation: {animation_name}")
            return

        # Set color if provided
        if color:
            self.controller.set_color(color, transition=True)

        # Track current animation
        self._current_animation = animation_name

        # Run animation
        self.controller._run_animation(animation_func, self.controller, color, duration)
        self.logger.info(f"Started animation: {animation_name}")

    def _handle_set_color(self, color: Tuple[int, int, int]):
        """Set the current color with smooth transition"""
        self.controller.set_color(color, transition=True)
        self.logger.debug(f"Set color to: {color}")

    def _handle_stop_animation(self):
        """Stop any running animation"""
        self.controller.stop_animation()
        self.logger.debug("Stopped animation")

    def get_available_animations(self) -> dict:
        """Get all available animations with descriptions"""
        return list_animations()
    
    def clear(self):
        """Turn off all LEDs"""
        self.controller.stop_animation()
        frame = [(0, 0, 0)] * self.led_count
        self.controller._update_frame(frame)

    def stop(self, timeout: float = 5.0):
        """Override stop to clear LEDs and cleanup driver before stopping"""
        self.clear()
        self.driver.cleanup()
        super().stop(timeout)