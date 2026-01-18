"""Scan - Active scanning animation sweeping across rings"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="scan",
    description="Active scanning sweep - use when searching, analyzing, or actively looking for something. Suggests alertness and focus."
)
def scan(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Active scanning animation - sweeps across each ring simultaneously"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()
        t = time.time() * 3  # Scan speed
        frame = [(0, 0, 0)] * controller.led_count

        if controller.has_rings():
            # Sweep across each ring simultaneously
            for ring in controller._rings:
                ring_size = ring['count']
                scan_pos = (t % 1.0) * ring_size
                center_led = int(scan_pos)

                beam_width = max(3, ring_size // 8)
                for offset in range(-beam_width, beam_width + 1):
                    led_idx = ring['start'] + ((center_led + offset) % ring_size)
                    if led_idx <= ring['end']:
                        distance = abs(offset)
                        intensity = max(0, 1.0 - (distance / beam_width))
                        intensity = intensity ** 0.5  # Softer falloff

                        frame[led_idx] = (int(base_color[0] * intensity),
                                         int(base_color[1] * intensity),
                                         int(base_color[2] * intensity))
        else:
            # Fallback
            scan_width = max(3, controller._active_led_count // 10)
            position = controller._active_led_start + int((math.sin(t) + 1) / 2 * controller._active_led_count)
            for i in range(controller._active_led_start, controller._active_led_end + 1):
                distance = abs(i - position)
                if distance < scan_width:
                    intensity = 1.0 - (distance / scan_width)
                    frame[i] = (int(base_color[0] * intensity),
                               int(base_color[1] * intensity),
                               int(base_color[2] * intensity))

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
