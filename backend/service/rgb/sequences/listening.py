"""Listening - Calm steady glow indicating passive listening state"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="listening",
    description="Calm steady glow with subtle breathing - use when LeLamp is passively listening and ready for input."
)
def listening(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Listening animation - calm steady glow with very subtle breathing"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()

        # Very slow, subtle breathing effect - barely noticeable
        t = time.time() * 0.5  # Very slow
        intensity = 0.6 + (math.sin(t) * 0.1)  # 50-70% range, subtle variation

        frame = [(0, 0, 0)] * controller.led_count

        active_color = (int(base_color[0] * intensity),
                       int(base_color[1] * intensity),
                       int(base_color[2] * intensity))

        for i in range(controller._active_led_start, controller._active_led_end + 1):
            frame[i] = active_color

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
