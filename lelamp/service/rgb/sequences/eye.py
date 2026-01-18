"""Eye - Realistic human eye animation with customizable iris color"""

import time
import math
import random
from typing import Optional, Tuple, List
from . import register_animation


@register_animation(
    name="eye",
    description="Realistic human eye with iris color, pupil dilation, and subtle organic movement. Specify color for iris."
)
def eye(controller, color: Optional[Tuple[int, int, int]] = None, duration: float = 30.0):
    """
    Human eye animation:
    - Colored iris with radial texture and depth
    - Dark pupil in center that dilates/contracts
    - Subtle shimmer and organic movement
    - Occasional blink effect

    Args:
        color: Iris color (default: blue-green)
        duration: How long to run
    """
    if duration is None:
        duration = 30.0

    # Default to a natural blue-green eye color
    if color is None:
        color = (70, 130, 160)

    start_time = time.time()
    led_count = controller.led_count

    # Ring structure (outer to inner)
    # Use configured rings, or fallback to treating all LEDs as one ring
    if controller.has_rings():
        rings = controller._rings
    else:
        # Fallback: treat all LEDs as a single ring
        rings = [{"start": 0, "end": led_count - 1, "count": led_count}]
    num_rings = len(rings)

    # Current state for smooth interpolation
    current_r = [0.0] * led_count
    current_g = [0.0] * led_count
    current_b = [0.0] * led_count

    # Animation parameters
    fps = 60
    frame_time = 1.0 / fps
    lerp_speed = 12.0

    # Pupil state
    base_pupil_size = 0.35  # 0-1, how much of the eye is pupil
    pupil_size = base_pupil_size

    # Blink state
    blink_progress = 0.0  # 0 = open, 1 = closed
    next_blink_time = time.time() + random.uniform(3.0, 8.0)
    is_blinking = False

    # Extract iris color components
    iris_r, iris_g, iris_b = color

    # Create darker and lighter variations of iris color
    def darken(c: Tuple[int, int, int], factor: float) -> Tuple[float, float, float]:
        return (c[0] * factor, c[1] * factor, c[2] * factor)

    def lighten(c: Tuple[int, int, int], factor: float) -> Tuple[float, float, float]:
        return (
            min(255, c[0] + (255 - c[0]) * factor),
            min(255, c[1] + (255 - c[1]) * factor),
            min(255, c[2] + (255 - c[2]) * factor),
        )

    # Iris color variations
    iris_dark = darken(color, 0.4)
    iris_mid = color
    iris_light = lighten(color, 0.3)
    iris_rim = darken(color, 0.6)  # Dark limbal ring

    # Pupil color (very dark, slight color tint)
    pupil_color = darken(color, 0.08)

    def lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    last_time = time.time()

    while not controller._stop_animation.is_set():
        current_time = time.time()
        elapsed = current_time - start_time
        dt = current_time - last_time
        last_time = current_time

        if elapsed >= duration:
            break

        t = elapsed
        lerp_factor = min(1.0, lerp_speed * dt)

        # === Pupil dilation (breathing effect) ===
        # Pupils dilate and contract slowly
        breath = math.sin(t * 0.8) * 0.5 + 0.5  # 0-1
        target_pupil = base_pupil_size + breath * 0.15  # Varies 0.35-0.5

        # Occasional faster dilation (like reacting to light)
        if random.random() < 0.002:
            target_pupil = base_pupil_size - 0.1  # Quick constriction

        pupil_size = lerp(pupil_size, target_pupil, 0.05)

        # === Blink handling ===
        if not is_blinking and current_time >= next_blink_time:
            is_blinking = True
            blink_progress = 0.0

        if is_blinking:
            # Fast close, slower open
            if blink_progress < 0.5:
                blink_progress += dt * 8  # Fast close
            else:
                blink_progress += dt * 4  # Slower open

            if blink_progress >= 1.0:
                is_blinking = False
                blink_progress = 0.0
                next_blink_time = current_time + random.uniform(2.5, 7.0)

        # Blink factor (1 = fully open, 0 = closed)
        if is_blinking:
            # Smooth blink curve
            blink_phase = blink_progress * 2 if blink_progress < 0.5 else 2 - blink_progress * 2
            blink_factor = 1.0 - (math.sin(blink_phase * math.pi / 2) ** 2)
        else:
            blink_factor = 1.0

        # === Calculate target colors for each LED ===
        target_r = [0.0] * led_count
        target_g = [0.0] * led_count
        target_b = [0.0] * led_count

        for ring_idx, ring in enumerate(rings):
            ring_size = ring['count']
            # Ring position: 0 = outermost, 1 = center
            ring_pos = ring_idx / (num_rings - 1) if num_rings > 1 else 0.5

            for led_offset in range(ring_size):
                led_idx = ring['start'] + led_offset
                if led_idx > ring['end'] or led_idx >= led_count:
                    continue

                # Angular position around ring (0-1)
                angle = led_offset / ring_size
                angle_rad = angle * math.pi * 2

                # === Determine if this LED is pupil, iris, or limbal ring ===

                if ring_pos > (1.0 - pupil_size):
                    # PUPIL - center area
                    # Very dark with subtle depth
                    depth_var = 0.8 + 0.2 * math.sin(angle_rad * 2 + t)
                    r, g, b = pupil_color
                    r *= depth_var
                    g *= depth_var
                    b *= depth_var

                elif ring_pos > 0.15:
                    # IRIS - the colored part
                    # Calculate how far into iris (0 = inner edge near pupil, 1 = outer edge)
                    iris_inner = 1.0 - pupil_size
                    iris_outer = 0.15
                    iris_progress = (ring_pos - iris_outer) / (iris_inner - iris_outer)
                    iris_progress = max(0, min(1, iris_progress))

                    # Radial fibers - iris has streaky texture radiating from pupil
                    fiber_count = 12
                    fiber = (math.sin(angle_rad * fiber_count + ring_pos * 3) + 1) / 2
                    fiber = fiber ** 2  # Sharpen

                    # Color gradient: lighter near pupil, darker at edges
                    # Plus fiber texture
                    if iris_progress > 0.7:
                        # Near pupil - lighter, more golden highlights
                        base_r = lerp(iris_mid[0], iris_light[0], (iris_progress - 0.7) / 0.3)
                        base_g = lerp(iris_mid[1], iris_light[1], (iris_progress - 0.7) / 0.3)
                        base_b = lerp(iris_mid[2], iris_light[2], (iris_progress - 0.7) / 0.3)
                    else:
                        # Outer iris - base color to darker
                        base_r = lerp(iris_dark[0], iris_mid[0], iris_progress / 0.7)
                        base_g = lerp(iris_dark[1], iris_mid[1], iris_progress / 0.7)
                        base_b = lerp(iris_dark[2], iris_mid[2], iris_progress / 0.7)

                    # Apply fiber texture
                    fiber_influence = 0.25
                    r = base_r * (1 - fiber_influence + fiber * fiber_influence)
                    g = base_g * (1 - fiber_influence + fiber * fiber_influence)
                    b = base_b * (1 - fiber_influence + fiber * fiber_influence)

                    # Subtle shimmer/sparkle in iris
                    shimmer = 0.9 + 0.1 * math.sin(t * 3 + angle_rad * 5 + ring_pos * 10)
                    r *= shimmer
                    g *= shimmer
                    b *= shimmer

                    # Occasional sparkle (light reflection)
                    sparkle_angle = (t * 0.2) % 1.0  # Slow rotation
                    angle_diff = abs(angle - sparkle_angle)
                    if angle_diff > 0.5:
                        angle_diff = 1.0 - angle_diff
                    if angle_diff < 0.08 and iris_progress > 0.4 and iris_progress < 0.8:
                        sparkle = 1.0 - (angle_diff / 0.08)
                        sparkle = sparkle ** 2
                        r = lerp(r, 255, sparkle * 0.4)
                        g = lerp(g, 255, sparkle * 0.4)
                        b = lerp(b, 255, sparkle * 0.4)

                else:
                    # LIMBAL RING - dark edge around iris
                    # Creates depth and definition
                    r, g, b = iris_rim
                    # Slight variation
                    var = 0.85 + 0.15 * math.sin(angle_rad * 8)
                    r *= var
                    g *= var
                    b *= var

                # === Apply blink (darken during blink) ===
                r *= blink_factor
                g *= blink_factor
                b *= blink_factor

                target_r[led_idx] = r
                target_g[led_idx] = g
                target_b[led_idx] = b

        # === Smooth interpolation ===
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

    # Fade out (eye closing)
    fade_duration = 0.8
    fade_start = time.time()
    while not controller._stop_animation.is_set():
        fade_elapsed = time.time() - fade_start
        if fade_elapsed >= fade_duration:
            break

        # Smooth close
        fade = 1.0 - (fade_elapsed / fade_duration)
        fade = fade * fade  # Ease out

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
