"""Welcome - Beautiful welcome animation for setup and greetings"""

import time
import math
import random
from typing import Optional, Tuple, List
from . import register_animation


@register_animation(
    name="welcome",
    description="Beautiful welcome sequence with ripples, rainbow chase, and celebration. Use for greetings, setup completion, or special moments."
)
def welcome(controller, color: Optional[Tuple[int, int, int]] = None, duration: float = 10.0):
    """
    Spectacular welcome animation with smooth per-pixel interpolation.

    Each LED smoothly flows between colors creating organic, fluid motion.
    Runs at high FPS with real-time color lerping.
    """
    if duration is None:
        duration = 10.0

    start_time = time.time()
    led_count = controller.led_count

    # Ring structure
    # Use configured rings, or fallback to treating all LEDs as one ring
    if controller.has_rings():
        rings = controller._rings
    else:
        rings = [{"start": 0, "end": led_count - 1, "count": led_count}]
    rings_center_first = list(reversed(rings))
    num_rings = len(rings)

    # Current state - floats for smooth interpolation
    current_r = [0.0] * led_count
    current_g = [0.0] * led_count
    current_b = [0.0] * led_count

    # Rainbow colors (HSV-like spread)
    def hsv_to_rgb(h: float, s: float = 1.0, v: float = 1.0) -> Tuple[float, float, float]:
        """Convert HSV to RGB. h is 0-1, returns 0-255 floats."""
        if s == 0:
            return (v * 255, v * 255, v * 255)

        h = h % 1.0
        i = int(h * 6)
        f = (h * 6) - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))

        if i == 0:
            r, g, b = v, t, p
        elif i == 1:
            r, g, b = q, v, p
        elif i == 2:
            r, g, b = p, v, t
        elif i == 3:
            r, g, b = p, q, v
        elif i == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q

        return (r * 255, g * 255, b * 255)

    def lerp(a: float, b: float, t: float) -> float:
        """Linear interpolation."""
        return a + (b - a) * t

    def ease_in_out(t: float) -> float:
        """Smooth ease in/out curve."""
        return t * t * (3 - 2 * t)

    # Phase timings
    phase1_end = 3.0    # Rainbow ripple pulse
    phase2_end = 6.0    # Flowing chase
    phase3_end = 8.5    # Sparkle celebration
    phase4_end = duration  # Warm fade

    # Animation parameters
    fps = 60
    frame_time = 1.0 / fps

    # Interpolation speed (how fast pixels lerp to target) - higher = snappier
    lerp_speed = 8.0  # Per second

    # Sparkle state
    sparkle_timers = [0.0] * led_count
    sparkle_colors = [(0.0, 0.0, 0.0)] * led_count

    last_time = time.time()

    while not controller._stop_animation.is_set():
        current_time = time.time()
        elapsed = current_time - start_time
        dt = current_time - last_time
        last_time = current_time

        if elapsed >= duration:
            break

        # Calculate lerp factor for this frame
        lerp_factor = min(1.0, lerp_speed * dt)

        # Target colors for this frame
        target_r = [0.0] * led_count
        target_g = [0.0] * led_count
        target_b = [0.0] * led_count

        # Global time-based modulation
        t = elapsed

        # === PHASE 1: Rainbow Ripple Pulse from Center ===
        if elapsed < phase1_end:
            phase_progress = elapsed / phase1_end
            fade_in = min(1.0, elapsed / 0.5)

            for ring_idx, ring in enumerate(rings_center_first):
                ring_size = ring['count']

                # Ripple wave - multiple waves expanding outward
                wave_speed = 3.0
                wave_count = 2

                for wave in range(wave_count):
                    wave_phase = (t * wave_speed - ring_idx * 0.4 - wave * 2.0)
                    wave_intensity = math.sin(wave_phase) * 0.5 + 0.5
                    wave_intensity = wave_intensity ** 1.5  # Sharpen peaks

                    # Fade waves as they expand
                    distance_fade = 1.0 - (ring_idx / num_rings) * 0.3
                    wave_intensity *= distance_fade * fade_in

                    if wave_intensity > 0.05:
                        # Color shifts with time and ring
                        hue = (t * 0.15 + ring_idx * 0.08 + wave * 0.1) % 1.0
                        r, g, b = hsv_to_rgb(hue, 0.9, wave_intensity)

                        # Add breathing pulse
                        breath = 0.85 + 0.15 * math.sin(t * 4 + ring_idx * 0.5)
                        r *= breath
                        g *= breath
                        b *= breath

                        for led_offset in range(ring_size):
                            led_idx = ring['start'] + led_offset
                            if led_idx <= ring['end'] and led_idx < led_count:
                                # Per-LED variation
                                led_phase = led_offset / ring_size * math.pi * 2
                                led_var = 0.9 + 0.1 * math.sin(led_phase * 3 + t * 5)

                                target_r[led_idx] = max(target_r[led_idx], r * led_var)
                                target_g[led_idx] = max(target_g[led_idx], g * led_var)
                                target_b[led_idx] = max(target_b[led_idx], b * led_var)

            # Transition blend to next phase
            if elapsed > phase1_end - 0.8:
                blend = (elapsed - (phase1_end - 0.8)) / 0.8
                lerp_factor = min(1.0, lerp_speed * dt * (1 + blend * 2))

        # === PHASE 2: Flowing Color Chase ===
        elif elapsed < phase2_end:
            phase_elapsed = elapsed - phase1_end
            phase_progress = phase_elapsed / (phase2_end - phase1_end)

            for ring_idx, ring in enumerate(rings):
                ring_size = ring['count']
                if ring_size == 0:
                    continue

                # Direction alternates by ring
                direction = 1.0 if ring_idx % 2 == 0 else -1.0

                # Speed varies by ring (inner rings faster)
                speed = 2.0 + (num_rings - ring_idx) * 0.5

                # Chase position (continuous float)
                chase_pos = (phase_elapsed * speed * direction) % ring_size

                # Ring base hue shifts over time
                ring_hue_base = (phase_elapsed * 0.1 + ring_idx * 0.12) % 1.0

                for led_offset in range(ring_size):
                    led_idx = ring['start'] + led_offset
                    if led_idx > ring['end'] or led_idx >= led_count:
                        continue

                    # Distance from chase head (wrapping)
                    dist = led_offset - chase_pos
                    if dist < 0:
                        dist += ring_size
                    if dist > ring_size / 2:
                        dist = ring_size - dist

                    # Tail with smooth falloff
                    tail_length = ring_size * 0.4

                    if dist < tail_length:
                        # Smooth intensity falloff
                        intensity = 1.0 - (dist / tail_length)
                        intensity = intensity ** 0.7  # Softer tail

                        # Hue shifts along tail
                        hue = (ring_hue_base + dist / tail_length * 0.15) % 1.0

                        # Saturation varies
                        sat = 0.8 + 0.2 * math.sin(t * 3 + led_offset)

                        r, g, b = hsv_to_rgb(hue, sat, intensity)

                        # Add shimmer
                        shimmer = 0.9 + 0.1 * math.sin(t * 12 + led_idx * 0.7)

                        target_r[led_idx] = r * shimmer
                        target_g[led_idx] = g * shimmer
                        target_b[led_idx] = b * shimmer

                    # Ambient glow on all LEDs
                    ambient = 0.08 + 0.04 * math.sin(t * 2 + led_idx * 0.3)
                    amb_hue = (ring_hue_base + 0.5) % 1.0
                    ar, ag, ab = hsv_to_rgb(amb_hue, 0.5, ambient)
                    target_r[led_idx] = max(target_r[led_idx], ar)
                    target_g[led_idx] = max(target_g[led_idx], ag)
                    target_b[led_idx] = max(target_b[led_idx], ab)

        # === PHASE 3: Sparkle Burst Celebration ===
        elif elapsed < phase3_end:
            phase_elapsed = elapsed - phase2_end
            phase_progress = phase_elapsed / (phase3_end - phase2_end)

            # Pulsing base glow
            glow_pulse = 0.15 + 0.1 * math.sin(t * 6)
            glow_hue = (t * 0.08) % 1.0

            for i in range(led_count):
                # Base warm glow with color shift
                hue_var = (glow_hue + i * 0.003) % 1.0
                gr, gg, gb = hsv_to_rgb(hue_var, 0.4, glow_pulse)
                target_r[i] = gr
                target_g[i] = gg
                target_b[i] = gb

                # Update sparkle timers
                sparkle_timers[i] -= dt

                if sparkle_timers[i] > 0:
                    # Active sparkle - fade out
                    sparkle_intensity = sparkle_timers[i] / 0.3  # 0.3s sparkle duration
                    sparkle_intensity = sparkle_intensity ** 0.5  # Quick attack, slow decay

                    sr, sg, sb = sparkle_colors[i]
                    target_r[i] = max(target_r[i], sr * sparkle_intensity)
                    target_g[i] = max(target_g[i], sg * sparkle_intensity)
                    target_b[i] = max(target_b[i], sb * sparkle_intensity)

            # Spawn new sparkles
            sparkle_rate = 25 + 15 * math.sin(t * 3)  # Sparkles per second
            num_new_sparkles = int(sparkle_rate * dt) + (1 if random.random() < (sparkle_rate * dt) % 1 else 0)

            for _ in range(num_new_sparkles):
                idx = random.randint(0, led_count - 1)
                if sparkle_timers[idx] <= 0:
                    sparkle_timers[idx] = 0.3 + random.random() * 0.2

                    # Sparkle color - mostly white with occasional color
                    if random.random() < 0.7:
                        sparkle_colors[idx] = (255.0, 255.0, 255.0)
                    else:
                        spark_hue = random.random()
                        sparkle_colors[idx] = hsv_to_rgb(spark_hue, 0.5, 1.0)

        # === PHASE 4: Warm Fade Out ===
        else:
            phase_elapsed = elapsed - phase3_end
            phase_duration = phase4_end - phase3_end

            if phase_duration > 0:
                fade_progress = phase_elapsed / phase_duration
                # Smooth ease out
                fade = 1.0 - ease_in_out(fade_progress)

                # Warm golden color with gentle pulse
                pulse = 0.95 + 0.05 * math.sin(t * 2)
                intensity = fade * pulse

                # Warm gradient from center
                for ring_idx, ring in enumerate(rings_center_first):
                    # Center is brighter
                    ring_intensity = intensity * (0.7 + 0.3 * (1 - ring_idx / num_rings))

                    # Warm color (amber/gold)
                    r = 255 * ring_intensity
                    g = 160 * ring_intensity
                    b = 40 * ring_intensity

                    for i in range(ring['start'], ring['end'] + 1):
                        if i < led_count:
                            # Subtle per-LED variation
                            var = 0.95 + 0.05 * math.sin(i * 0.5 + t)
                            target_r[i] = r * var
                            target_g[i] = g * var
                            target_b[i] = b * var

                # Slower lerp during fade for smoother exit
                lerp_factor = min(1.0, lerp_speed * 0.5 * dt)

        # === Apply smooth interpolation to all LEDs ===
        for i in range(led_count):
            current_r[i] = lerp(current_r[i], target_r[i], lerp_factor)
            current_g[i] = lerp(current_g[i], target_g[i], lerp_factor)
            current_b[i] = lerp(current_b[i], target_b[i], lerp_factor)

        # Build output frame
        frame = [
            (
                max(0, min(255, int(current_r[i]))),
                max(0, min(255, int(current_g[i]))),
                max(0, min(255, int(current_b[i])))
            )
            for i in range(led_count)
        ]

        controller._update_frame(frame)

        # High FPS timing
        frame_end = time.time()
        sleep_time = frame_time - (frame_end - current_time)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Smooth fade to off
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

    # Final off
    controller._update_frame([(0, 0, 0)] * led_count)
