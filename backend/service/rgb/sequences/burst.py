"""Burst - Quick flash burst for emphasis or surprise"""

import time
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="burst",
    description="Quick bright flash and fade - use for surprise, sudden realization, emphasis, or 'aha!' moments. Short duration impact."
)
def burst(controller, color: Optional[Tuple[int, int, int]] = None, duration: float = 0.5):
    """Spectacular burst: dark -> bright flash -> fade back"""
    # Handle None duration
    if duration is None:
        duration = 0.5

    start_time = time.time()
    base_color = color if color else controller.get_current_color()
    original_color = controller.get_current_color()

    # Timing phases
    burst_up_time = 0.08      # Quick ramp up (80ms)
    hold_time = 0.05          # Hold at peak (50ms)
    fade_time = duration - burst_up_time - hold_time  # Rest of duration

    while not controller._stop_animation.is_set():
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break

        frame = [(0, 0, 0)] * controller.led_count

        if elapsed < burst_up_time:
            # Phase 1: Quick ramp from black to bright
            progress = elapsed / burst_up_time
            # Ease-out curve for dramatic acceleration
            intensity = 1.0 - (1.0 - progress) ** 3

        elif elapsed < burst_up_time + hold_time:
            # Phase 2: Hold at full brightness
            intensity = 1.0

        else:
            # Phase 3: Fade back down
            fade_elapsed = elapsed - burst_up_time - hold_time
            progress = fade_elapsed / fade_time
            # Exponential fade for smooth decay
            intensity = (1.0 - progress) ** 2

        active_color = (int(base_color[0] * intensity),
                       int(base_color[1] * intensity),
                       int(base_color[2] * intensity))

        for i in range(controller._active_led_start, controller._active_led_end + 1):
            frame[i] = active_color

        controller._update_frame(frame)
        time.sleep(get_frame_interval())

    # Return to original color
    frame = [(0, 0, 0)] * controller.led_count
    for i in range(controller._active_led_start, controller._active_led_end + 1):
        frame[i] = original_color
    controller._update_frame(frame)
