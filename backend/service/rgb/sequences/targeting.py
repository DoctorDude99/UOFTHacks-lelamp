"""Targeting - Crosshair targeting effect with inward/outward sequence"""

import time
import math
from typing import Optional, Tuple
from . import register_animation, get_frame_interval

@register_animation(
    name="targeting",
    description="Crosshair targeting effect - use when focusing on something specific, aiming, or zeroing in on a target. Creates a locked-on feel."
)
def targeting(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """
    Crosshair targeting animation.

    Creates a crosshair pattern (vertical + horizontal lines) that sequences
    inward from outer ring to center, then back outward.

    LED 0 of each ring is at the TOP position. Crosshair markers are placed at:
    - Top (0% of ring = LED 0)
    - Right (25% of ring)
    - Bottom (50% of ring)
    - Left (75% of ring)
    """
    start_time = time.time()
    led_count = controller.led_count

    if not controller.has_rings():
        # Fallback for no ring structure - simple pulse
        while not controller._stop_animation.is_set():
            if duration and (time.time() - start_time) >= duration:
                break
            base_color = color if color else controller.get_current_color()
            t = time.time() * 2.5
            intensity = 0.5 + 0.5 * ((math.sin(t) + 1) / 2)
            frame = [(0, 0, 0)] * led_count
            for i in range(controller._active_led_start, controller._active_led_end + 1):
                frame[i] = (int(base_color[0] * intensity),
                           int(base_color[1] * intensity),
                           int(base_color[2] * intensity))
            controller._update_frame(frame)
            time.sleep(get_frame_interval())
        return

    rings = controller._rings
    num_rings = len(rings)

    # Animation parameters
    cycle_duration = 2.0  # Time for one complete in-out cycle

    while not controller._stop_animation.is_set():
        if duration and (time.time() - start_time) >= duration:
            break

        base_color = color if color else controller.get_current_color()
        elapsed = time.time() - start_time

        # Calculate cycle position (0 to 1, where 0.5 is center)
        # Triangle wave: 0->1 (inward), 1->0 (outward)
        cycle_pos = (elapsed % cycle_duration) / cycle_duration
        if cycle_pos < 0.5:
            # Inward phase: 0->1 maps to outer->inner (ring index 0 to num_rings-1)
            focus_progress = cycle_pos * 2  # 0 to 1
        else:
            # Outward phase: 0.5->1 maps to inner->outer
            focus_progress = 1.0 - (cycle_pos - 0.5) * 2  # 1 to 0

        frame = [(0, 0, 0)] * led_count

        for ring_idx, ring in enumerate(rings):
            ring_size = ring['count']
            if ring_size == 0:
                continue

            # Ring's normalized position (0 = outer/first ring, 1 = inner/last ring)
            ring_norm = ring_idx / max(1, num_rings - 1)

            # How active is this ring based on the focus sweep?
            # Ring is brightest when focus_progress matches its position
            distance_from_focus = abs(ring_norm - focus_progress)

            # Sharp activation with trail
            if distance_from_focus < 0.3:
                ring_intensity = 1.0 - (distance_from_focus / 0.3)
                ring_intensity = ring_intensity ** 0.5  # Softer falloff
            else:
                ring_intensity = 0.0

            if ring_intensity < 0.05:
                continue

            # Crosshair marker positions (as fractions of ring)
            # LED 0 = top, so positions are: 0.0 (top), 0.25 (right), 0.5 (bottom), 0.75 (left)
            marker_positions = [0.0, 0.25, 0.5, 0.75]

            # Marker width scales with ring size (larger rings get wider markers)
            marker_width = max(1, ring_size // 8)

            for marker_pos in marker_positions:
                # Center LED for this marker
                center_offset = int(marker_pos * ring_size)

                for offset in range(-marker_width, marker_width + 1):
                    led_offset = (center_offset + offset) % ring_size
                    led_idx = ring['start'] + led_offset

                    if led_idx > ring['end'] or led_idx >= led_count:
                        continue

                    # Intensity falls off from center of marker
                    distance_from_center = abs(offset)
                    marker_intensity = 1.0 - (distance_from_center / (marker_width + 1))

                    # Combine ring activation with marker intensity
                    final_intensity = ring_intensity * marker_intensity

                    # Apply color
                    r = int(base_color[0] * final_intensity)
                    g = int(base_color[1] * final_intensity)
                    b = int(base_color[2] * final_intensity)

                    # Max blend (in case markers overlap at center ring)
                    if frame[led_idx][0] < r or frame[led_idx][1] < g or frame[led_idx][2] < b:
                        frame[led_idx] = (max(frame[led_idx][0], r),
                                         max(frame[led_idx][1], g),
                                         max(frame[led_idx][2], b))

        controller._update_frame(frame)
        time.sleep(get_frame_interval())
