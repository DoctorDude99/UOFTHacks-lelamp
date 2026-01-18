"""Beacon - Rotating bright spot for attention or alert"""

import time
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="beacon",
    description="Rotating bright spot - use for attracting attention, alert mode, or beacon-like signaling. Constantly moving focus."
)
def beacon(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Beacon mode - rotating bright spot"""
    start_time = time.time()
    spot_width = max(2, controller._active_led_count // 20)

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()

        t = time.time() * 2
        position = controller._active_led_start + int((t % 1.0) * controller._active_led_count)

        frame = [(0, 0, 0)] * controller.led_count

        # Bright spot with falloff within active range
        for i in range(-spot_width, spot_width + 1):
            idx = position + i
            # Wrap within active range
            if idx < controller._active_led_start:
                idx = controller._active_led_end - (controller._active_led_start - idx - 1)
            elif idx > controller._active_led_end:
                idx = controller._active_led_start + (idx - controller._active_led_end - 1)

            intensity = 1.0 - (abs(i) / spot_width) * 0.8
            frame[idx] = (int(base_color[0] * intensity),
                         int(base_color[1] * intensity),
                         int(base_color[2] * intensity))

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
