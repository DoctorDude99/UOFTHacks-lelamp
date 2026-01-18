"""Count - Sequential LED lighting from 0 to 93"""

import time
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="count",
    description="Sequential LED count - lights up each LED one by one with 0.5s delay. Good for demos and testing."
)
def count(controller, color: Optional[Tuple[int, int, int]] = None, duration: float = None):
    """Count through LEDs sequentially from first to last."""
    # Handle None duration - if not specified, run through all LEDs once
    if duration is None:
        duration = controller.led_count * 0.5  # 0.5s per LED

    base_color = color if color else controller.get_current_color()
    start_time = time.time()
    delay_per_led = 0.5  # 0.5 second delay between LEDs

    led_index = 0
    last_update = start_time

    while not controller._stop_animation.is_set():
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break

        # Check if it's time to move to the next LED
        if time.time() - last_update >= delay_per_led:
            # Create frame with all LEDs off
            frame = [(0, 0, 0)] * controller.led_count

            # Light up the current LED
            if led_index < controller.led_count:
                frame[led_index] = base_color

            controller._update_frame(frame)

            # Move to next LED
            led_index += 1
            last_update = time.time()

            # Loop back to start if we've reached the end
            if led_index >= controller.led_count:
                led_index = 0

        time.sleep(get_frame_interval())

    # Turn off all LEDs at the end
    frame = [(0, 0, 0)] * controller.led_count
    controller._update_frame(frame)
