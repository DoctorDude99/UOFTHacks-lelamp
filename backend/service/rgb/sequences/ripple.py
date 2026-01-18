"""Ripple - Smooth waves emanate from center outward through rings"""

import time
import math
from typing import Optional, Tuple
from . import register_animation


@register_animation(
    name="ripple",
    description="Smooth waves emanate from center outward - calming, meditative effect. Pass color to customize."
)
def ripple(controller, color: Optional[Tuple[int, int, int]] = None, duration: Optional[float] = None):
    """
    Ripple effect with smooth per-pixel interpolation.
    Waves emanate from center outward through ring structure.

    Args:
        color: Base color for the ripple (default: controller's current color)
        duration: How long to run (None = indefinite)
    """
    start_time = time.time()
    led_count = controller.led_count

    # If no rings, fall back to simple pulse
    if not controller.has_rings():
        from .aura_glow import aura_glow
        aura_glow(controller, color, duration)
        return

    rings = controller._rings
    num_rings = len(rings)

    # Current state for smooth interpolation
    current_r = [0.0] * led_count
    current_g = [0.0] * led_count
    current_b = [0.0] * led_count

    # Animation parameters
    fps = 60
    frame_time = 1.0 / fps
    lerp_speed = 10.0

    def lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    last_time = time.time()

    while not controller._stop_animation.is_set():
        current_time = time.time()
        elapsed = current_time - start_time
        dt = current_time - last_time
        last_time = current_time

        if duration and elapsed >= duration:
            break

        lerp_factor = min(1.0, lerp_speed * dt)

        # Get base color
        base_color = color if color else controller.get_current_color()
        base_r, base_g, base_b = base_color

        # Target colors
        target_r = [0.0] * led_count
        target_g = [0.0] * led_count
        target_b = [0.0] * led_count

        t = elapsed * 1.8  # Ripple speed

        # Animate each ring with phase delay (innermost first)
        for ring_idx, ring in enumerate(reversed(rings)):
            ring_size = ring['count']

            # Phase offset based on ring distance from center
            # Creates outward-moving wave
            phase = ring_idx * (math.pi / 2.5)

            # Main wave
            wave = (math.sin(t + phase) + 1) / 2

            # Add secondary harmonics for organic feel
            wave2 = (math.sin(t * 1.7 + phase * 1.3) + 1) / 2
            wave = wave * 0.7 + wave2 * 0.3

            # Base intensity (never fully off)
            base_intensity = 0.25
            wave_intensity = 0.75

            for led_offset in range(ring_size):
                led_idx = ring['start'] + led_offset
                if led_idx > ring['end'] or led_idx >= led_count:
                    continue

                # Add subtle per-LED variation for organic look
                led_angle = (led_offset / ring_size) * math.pi * 2
                led_var = 1.0 + 0.08 * math.sin(led_angle * 3 + t * 0.5)

                # Final intensity
                intensity = (base_intensity + wave * wave_intensity) * led_var

                target_r[led_idx] = base_r * intensity
                target_g[led_idx] = base_g * intensity
                target_b[led_idx] = base_b * intensity

        # Smooth interpolation
        for i in range(led_count):
            current_r[i] = lerp(current_r[i], target_r[i], lerp_factor)
            current_g[i] = lerp(current_g[i], target_g[i], lerp_factor)
            current_b[i] = lerp(current_b[i], target_b[i], lerp_factor)

        # Build frame
        frame = [
            (
                max(0, min(255, int(current_r[i]))),
                max(0, min(255, int(current_g[i]))),
                max(0, min(255, int(current_b[i])))
            )
            for i in range(led_count)
        ]

        controller._update_frame(frame)

        # FPS timing
        frame_end = time.time()
        sleep_time = frame_time - (frame_end - current_time)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Smooth fade out if duration ended
    if duration:
        fade_duration = 0.5
        fade_start = time.time()
        while not controller._stop_animation.is_set():
            fade_elapsed = time.time() - fade_start
            if fade_elapsed >= fade_duration:
                break

            fade = 1.0 - (fade_elapsed / fade_duration)
            frame = [
                (
                    max(0, min(255, int(current_r[i] * fade))),
                    max(0, min(255, int(current_g[i] * fade))),
                    max(0, min(255, int(current_b[i] * fade)))
                )
                for i in range(led_count)
            ]
            controller._update_frame(frame)
            time.sleep(frame_time)

        controller._update_frame([(0, 0, 0)] * led_count)
