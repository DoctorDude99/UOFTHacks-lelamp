"""Angry - Intense aggressive pulsing for frustration or anger"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="angry",
    description="Intense aggressive pulsing - use when frustrated, angry, or upset. Fast and intense, typically pairs well with red colors."
)
def angry(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Angry pulsing glow - intense and aggressive"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()

        t = time.time() * 4  # Fast pulse
        intensity = (math.sin(t) + 1) / 2
        intensity = 0.6 + (intensity * 0.4)  # 60-100% intensity

        frame = [(0, 0, 0)] * controller.led_count
        active_color = (int(base_color[0] * intensity),
                       int(base_color[1] * intensity),
                       int(base_color[2] * intensity))

        for i in range(controller._active_led_start, controller._active_led_end + 1):
            frame[i] = active_color

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
