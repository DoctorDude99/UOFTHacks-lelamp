"""Speaking - Subtle brightness variation indicating active speech"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="speaking",
    description="Subtle pulsing brightness - use when LeLamp is speaking or vocalizing. Creates a lively, conversational feel."
)
def speaking(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Speaking animation - subtle brightness variation"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()

        # Randomized subtle pulses
        t = time.time()
        intensity = 0.7 + (math.sin(t * 10) * 0.15) + (math.sin(t * 7.3) * 0.1)

        frame = [(0, 0, 0)] * controller.led_count
        active_color = (int(base_color[0] * intensity),
                       int(base_color[1] * intensity),
                       int(base_color[2] * intensity))

        for i in range(controller._active_led_start, controller._active_led_end + 1):
            frame[i] = active_color

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
