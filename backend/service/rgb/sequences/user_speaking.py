"""User Speaking - Attentive pulsing indicating active engagement with user's speech"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="user_speaking",
    description="Attentive pulsing glow - use when the user is speaking and LeLamp is actively listening and engaged."
)
def user_speaking(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """User speaking animation - brighter, more responsive pulsing to show attention"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()

        # Faster, more noticeable pulse to show active engagement
        t = time.time() * 2.0  # Moderate speed
        intensity = 0.7 + (math.sin(t) * 0.25)  # 45-95% range, more dynamic

        frame = [(0, 0, 0)] * controller.led_count

        active_color = (int(base_color[0] * intensity),
                       int(base_color[1] * intensity),
                       int(base_color[2] * intensity))

        for i in range(controller._active_led_start, controller._active_led_end + 1):
            frame[i] = active_color

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
