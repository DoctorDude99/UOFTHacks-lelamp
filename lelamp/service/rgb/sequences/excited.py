"""Excited - Quick joyful flashes expressing happiness and energy"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="excited",
    description="Quick joyful flashes - use when happy, excited, celebrating, or laughing. Bright and energetic."
)
def excited(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Excited/laughing animation - quick joyful flashes"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()

        t = time.time() * 8  # Fast flickering
        intensity = (math.sin(t) + 1) / 2
        intensity = intensity ** 2  # Sharp peaks

        frame = [(0, 0, 0)] * controller.led_count
        active_color = (int(base_color[0] * intensity),
                       int(base_color[1] * intensity),
                       int(base_color[2] * intensity))

        for i in range(controller._active_led_start, controller._active_led_end + 1):
            frame[i] = active_color

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
