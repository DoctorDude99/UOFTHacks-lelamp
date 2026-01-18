"""Aura Glow - Gentle pulsing idle glow, mysterious and calming"""

import time
import math
from typing import Optional, Tuple, List
from . import register_animation, get_frame_interval

@register_animation(
    name="aura_glow",
    description="Gentle pulsing idle glow - use for calm, mysterious, or idle states. Creates depth with inner rings slightly brighter."
)
def aura_glow(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """Pulsing idle glow - ominous and dark, uses ring structure for depth"""
    start_time = time.time()

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        # Get current color (with transition)
        base_color = color if color else controller.get_current_color()

        # Slow sine wave pulse
        t = time.time() * 1.5  # Slow pulse speed
        base_intensity = (math.sin(t) + 1) / 2  # 0 to 1
        base_intensity = 0.2 + (base_intensity * 0.4)  # Scale to 20-60% intensity

        frame = [(0, 0, 0)] * controller.led_count

        if controller.has_rings():
            # Ring-aware: inner rings slightly brighter creating depth
            for ring_idx, ring in enumerate(controller._rings):
                # Inner rings get a slight boost
                ring_boost = 1.0 + (ring_idx * 0.1)
                intensity = min(1.0, base_intensity * ring_boost)

                active_color = (int(base_color[0] * intensity),
                               int(base_color[1] * intensity),
                               int(base_color[2] * intensity))

                for i in range(ring['start'], ring['end'] + 1):
                    frame[i] = active_color
        else:
            # Fallback for no ring structure
            active_color = (int(base_color[0] * base_intensity),
                           int(base_color[1] * base_intensity),
                           int(base_color[2] * base_intensity))
            for i in range(controller._active_led_start, controller._active_led_end + 1):
                frame[i] = active_color

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
