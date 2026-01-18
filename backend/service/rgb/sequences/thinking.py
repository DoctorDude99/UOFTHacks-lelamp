"""Thinking - Gentle wave pattern suggesting processing and contemplation"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="thinking",
    description="Gentle wave pattern - use when processing, contemplating, or analyzing. Suggests active thought and consideration."
)
def thinking(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Thinking animation - gentle wave pattern suggesting processing"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()

        t = time.time() * 2  # Medium speed wave
        frame = [(0, 0, 0)] * controller.led_count

        # Create a traveling wave across active LEDs
        for i in range(controller._active_led_start, controller._active_led_end + 1):
            # Position in the active range (0 to 1)
            position = (i - controller._active_led_start) / max(1, controller._active_led_count)

            # Multiple wave frequencies for complexity
            wave1 = math.sin(t + position * math.pi * 4)
            wave2 = math.sin(t * 1.3 + position * math.pi * 2)

            # Combine waves and normalize
            intensity = (wave1 + wave2) / 2
            intensity = (intensity + 1) / 2  # 0 to 1
            intensity = 0.3 + (intensity * 0.5)  # 30-80% range

            frame[i] = (int(base_color[0] * intensity),
                       int(base_color[1] * intensity),
                       int(base_color[2] * intensity))

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
