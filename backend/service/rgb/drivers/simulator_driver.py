"""
Simulator RGB LED driver for development and testing.

This driver doesn't require any hardware - useful for:
- Development on non-Pi machines
- Unit testing
- CI/CD pipelines
- Debugging animation logic
"""

from typing import List, Tuple, Optional, Callable
from .base import RGBDriver


class SimulatorDriver(RGBDriver):
    """
    Simulated RGB driver for development without hardware.

    This driver logs LED state changes and optionally calls a
    callback function with frame data for visualization.

    Useful for:
        - Development on laptops/desktops
        - Unit testing
        - Debugging animations without hardware
        - CI/CD pipelines
    """

    def __init__(
        self,
        led_count: int,
        verbose: bool = False,
        frame_callback: Optional[Callable[[List[Tuple[int, int, int]]], None]] = None,
    ):
        """
        Initialize simulator driver.

        Args:
            led_count: Number of simulated LEDs
            verbose: If True, log frame updates
            frame_callback: Optional callback called with each frame
        """
        super().__init__(led_count)

        self.verbose = verbose
        self.frame_callback = frame_callback
        self._current_frame: List[Tuple[int, int, int]] = [(0, 0, 0)] * led_count
        self._frame_count = 0

    def initialize(self) -> bool:
        """Initialize the simulator."""
        self._initialized = True
        self.logger.info(
            f"Simulator RGB driver initialized: {self.led_count} virtual LEDs"
        )
        return True

    def render(self, frame: List[Tuple[int, int, int]]) -> None:
        """Simulate rendering a frame."""
        if not self._initialized:
            return

        # Store frame
        self._current_frame = frame.copy()
        self._frame_count += 1

        # Log if verbose
        if self.verbose:
            # Count non-black pixels
            lit_count = sum(1 for r, g, b in frame if r > 0 or g > 0 or b > 0)

            # Get dominant color
            if lit_count > 0:
                avg_r = sum(r for r, g, b in frame) // len(frame)
                avg_g = sum(g for r, g, b in frame) // len(frame)
                avg_b = sum(b for r, g, b in frame) // len(frame)
                self.logger.debug(
                    f"Frame {self._frame_count}: {lit_count}/{len(frame)} LEDs lit, "
                    f"avg color: ({avg_r}, {avg_g}, {avg_b})"
                )
            else:
                self.logger.debug(f"Frame {self._frame_count}: all LEDs off")

        # Call callback if set
        if self.frame_callback:
            try:
                self.frame_callback(frame)
            except Exception as e:
                self.logger.error(f"Frame callback error: {e}")

    def set_brightness(self, brightness: int) -> None:
        """Simulate setting brightness (capped at MAX_BRIGHTNESS)."""
        # Enforce max brightness from base class to prevent overcurrent
        self._brightness = max(0, min(self.MAX_BRIGHTNESS, brightness))

        if self.verbose:
            self.logger.debug(f"Simulator brightness set to {self._brightness} (max={self.MAX_BRIGHTNESS})")

    def cleanup(self) -> None:
        """Clean up simulator."""
        self._current_frame = [(0, 0, 0)] * self.led_count
        self._initialized = False
        self.logger.info(
            f"Simulator RGB driver cleaned up (rendered {self._frame_count} frames)"
        )

    # Simulator-specific methods

    def get_current_frame(self) -> List[Tuple[int, int, int]]:
        """Get the current frame (for testing/visualization)."""
        return self._current_frame.copy()

    def get_frame_count(self) -> int:
        """Get total frames rendered (for testing)."""
        return self._frame_count

    def get_pixel(self, index: int) -> Tuple[int, int, int]:
        """Get color of specific pixel (for testing)."""
        if 0 <= index < len(self._current_frame):
            return self._current_frame[index]
        return (0, 0, 0)

    def print_strip_ascii(self) -> str:
        """
        Generate ASCII visualization of the LED strip.

        Returns:
            String representation of LED colors
        """
        def color_char(r: int, g: int, b: int) -> str:
            if r == 0 and g == 0 and b == 0:
                return "."
            if r > g and r > b:
                return "R"
            if g > r and g > b:
                return "G"
            if b > r and b > g:
                return "B"
            if r > 0 and g > 0 and b == 0:
                return "Y"
            if r > 0 and b > 0 and g == 0:
                return "M"
            if g > 0 and b > 0 and r == 0:
                return "C"
            return "W"

        chars = [color_char(r, g, b) for r, g, b in self._current_frame]
        return "".join(chars)
