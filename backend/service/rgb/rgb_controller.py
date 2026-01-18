import time
import threading
from typing import Tuple, Optional, Callable, List
import logging


class RGBController:
    """Animation controller for multi-ring LED setup"""

    # Frame rate limits
    # WS2812B @ 800KHz needs ~30µs per LED + 50µs reset
    # For 93 LEDs: ~2.8ms data time + 0.05ms reset = ~3ms minimum
    # Target 60 FPS for smooth animations (~16.7ms per frame)
    MIN_FRAME_INTERVAL = 0.008  # ~120 FPS max (8ms minimum between frames)
    DEFAULT_ANIMATION_FPS = 60  # Default target FPS for animations

    # Maximum brightness multiplier (1.0 = full brightness)
    # Actual brightness is controlled via config's led_brightness setting
    MAX_BRIGHTNESS_MULTIPLIER = 1.0

    def __init__(self, led_count: int = 93):
        self.led_count = led_count
        self.logger = logging.getLogger("rgb_controller")
        self._animation_thread: Optional[threading.Thread] = None
        self._stop_animation = threading.Event()
        self._current_frame: List[Tuple[int, int, int]] = [(0, 0, 0)] * led_count
        self._frame_lock = threading.Lock()
        self._brightness_multiplier = 1.0
        self._render_callback: Optional[Callable] = None

        # Initialize frame buffer to all black
        self._current_frame = [(0, 0, 0)] * led_count

        # Active LED range (start_index, end_index) - None means all LEDs
        self._led_range: Optional[Tuple[int, int]] = None
        self._active_led_start = 0
        self._active_led_end = led_count - 1
        self._active_led_count = led_count

        # Ring structure (if available)
        self._rings: Optional[List[dict]] = None

        # Color state and transitions
        self._current_color: Tuple[int, int, int] = (0, 0, 0)  # Start with black
        self._target_color: Optional[Tuple[int, int, int]] = None
        self._color_transition_start: Optional[float] = None
        self._color_transition_duration = 0.8  # seconds

        # Frame rate control
        self._last_frame_time: float = 0.0

    def set_led_range(self, start: int, end: int, rings: Optional[List[dict]] = None):
        """Set the active LED range for animations"""
        self._led_range = (start, end)
        self._active_led_start = start
        self._active_led_end = end
        self._active_led_count = end - start + 1
        self._rings = rings
        self.logger.info(f"Active LED range set to {start}-{end} ({self._active_led_count} LEDs)")
        if rings:
            self.logger.info(f"Ring structure loaded: {len(rings)} rings")

    def get_led_range(self) -> Tuple[int, int]:
        """Get the active LED range"""
        return (self._active_led_start, self._active_led_end)

    def get_rings(self) -> Optional[List[dict]]:
        """Get the ring structure if available"""
        return self._rings

    def has_rings(self) -> bool:
        """Check if ring structure is available"""
        return self._rings is not None and len(self._rings) > 0

    def set_render_callback(self, callback: Callable):
        """Set callback function to render frames to hardware"""
        self._render_callback = callback
        self.logger.info("Render callback registered")

    def set_color(self, color: Tuple[int, int, int], transition: bool = True):
        """Set the current color for animations"""
        if transition and self._current_color != color:
            self._target_color = color
            self._color_transition_start = time.time()
            self.logger.info(f"Transitioning color from {self._current_color} to {color}")
        else:
            self._current_color = color
            self._target_color = None

    def get_current_color(self) -> Tuple[int, int, int]:
        """Get the current color (with transition if active)"""
        if self._target_color is None:
            return self._current_color

        # Calculate transition progress
        elapsed = time.time() - self._color_transition_start
        progress = min(1.0, elapsed / self._color_transition_duration)

        if progress >= 1.0:
            # Transition complete
            self._current_color = self._target_color
            self._target_color = None
            return self._current_color

        # Linear interpolation between colors
        r = int(self._current_color[0] + (self._target_color[0] - self._current_color[0]) * progress)
        g = int(self._current_color[1] + (self._target_color[1] - self._current_color[1]) * progress)
        b = int(self._current_color[2] + (self._target_color[2] - self._current_color[2]) * progress)

        # Clamp values to valid range
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))

        return (r, g, b)

    def stop_animation(self):
        """Stop any currently running animation"""
        if self._animation_thread and self._animation_thread.is_alive():
            self._stop_animation.set()
            self._animation_thread.join(timeout=2.0)
        self._stop_animation.clear()

    def get_current_frame(self) -> List[Tuple[int, int, int]]:
        """Get the current LED frame data"""
        with self._frame_lock:
            return self._current_frame.copy()

    def set_brightness(self, multiplier: float):
        """Set global brightness multiplier (0.0 to MAX_BRIGHTNESS_MULTIPLIER)"""
        # Enforce max brightness to prevent overcurrent
        self._brightness_multiplier = max(0.0, min(self.MAX_BRIGHTNESS_MULTIPLIER, multiplier))

    def get_brightness(self) -> float:
        """Get current brightness multiplier"""
        return self._brightness_multiplier

    def _apply_brightness(self, color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Apply brightness multiplier to a color"""
        r, g, b = color
        r = max(0, min(255, int(r * self._brightness_multiplier)))
        g = max(0, min(255, int(g * self._brightness_multiplier)))
        b = max(0, min(255, int(b * self._brightness_multiplier)))
        return (r, g, b)

    def _update_frame(self, frame: List[Tuple[int, int, int]]):
        """Thread-safe frame update - renders directly to hardware if callback set

        Enforces minimum frame interval to prevent flickering from too-fast updates.
        """
        current_time = time.time()

        # Enforce minimum frame interval to prevent flickering
        time_since_last = current_time - self._last_frame_time
        if time_since_last < self.MIN_FRAME_INTERVAL:
            # Skip this frame - too soon after last one
            return

        with self._frame_lock:
            # Apply brightness
            new_frame = [self._apply_brightness(c) for c in frame]

            # Always update frame for smooth animations
            # The MIN_FRAME_INTERVAL already rate-limits us
            self._current_frame = new_frame
            self._last_frame_time = current_time

            # Render directly to hardware if callback is set
            if self._render_callback:
                self._render_callback(new_frame)

    def _map_to_range(self, position: float) -> int:
        """Map a 0-1 position to actual LED index within active range"""
        return self._active_led_start + int(position * self._active_led_count)

    def _run_animation(self, animation_func: Callable, *args, **kwargs):
        """Run animation function in a thread"""
        self.stop_animation()
        self._animation_thread = threading.Thread(
            target=animation_func,
            args=args,
            kwargs=kwargs,
            daemon=True
        )
        self._animation_thread.start()
