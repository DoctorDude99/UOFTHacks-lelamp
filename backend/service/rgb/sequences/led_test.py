"""LED Test - Safe diagnostic LED test cycling R, G, B, White"""

import time
from typing import Optional, Tuple
from . import register_animation


@register_animation(
    name="led_test",
    description="Safe diagnostic: one LED at a time, cycling R->G->B->White. For hardware testing."
)
def led_test(controller, color: Optional[Tuple[int, int, int]] = None, duration: float = None):
    """
    Safe diagnostic LED test.

    Lights ONE LED at a time, cycling through:
    - Red (tests red channel)
    - Green (tests green channel)
    - Blue (tests blue channel)
    - White (tests all channels)

    Uses moderate brightness (128) to minimize current draw.
    Only 1 LED powered at any time for maximum safety.
    """
    led_count = controller.led_count
    delay = 0.1  # 100ms per LED per color - slow enough to observe

    # Test colors at moderate brightness (128 instead of 255)
    # This reduces current draw significantly
    test_colors = [
        (128, 0, 0),    # Red
        (0, 128, 0),    # Green
        (0, 0, 128),    # Blue
        (128, 128, 128) # White (all channels)
    ]

    color_names = ["RED", "GREEN", "BLUE", "WHITE"]

    while not controller._stop_animation.is_set():
        for color_idx, test_color in enumerate(test_colors):
            if controller._stop_animation.is_set():
                break

            # Chase through all LEDs with this color
            for i in range(led_count):
                if controller._stop_animation.is_set():
                    break

                # All off except current LED
                frame = [(0, 0, 0)] * led_count
                frame[i] = test_color
                controller._update_frame(frame)
                time.sleep(delay)

        # Brief pause between cycles
        if not controller._stop_animation.is_set():
            controller._update_frame([(0, 0, 0)] * led_count)
            time.sleep(0.5)

    # Turn off
    controller._update_frame([(0, 0, 0)] * led_count)
