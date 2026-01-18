"""Flower - Beautiful rose blooming animation"""

import time
import math
import random
from typing import Optional, Tuple
from . import register_animation, get_frame_interval


@register_animation(
    name="flower",
    description="Beautiful rose blooming animation - stem grows from outer ring, then flower blooms from center. Use for growth, beauty, or romantic moments."
)
def flower(controller, color: Optional[Tuple[int, int, int]] = None, duration: float = 12.0):
    """
    Rose blooming animation:
    1. Green stem grows from outer ring toward center
    2. Rose bud forms at center
    3. Rose blooms outward in beautiful red/pink petals
    4. Gentle breathing glow
    5. Petals gently fall (fade)
    """
    if duration is None:
        duration = 12.0

    start_time = time.time()
    led_count = controller.led_count

    # Ring structure (outer to inner)
    # Use configured rings, or fallback to treating all LEDs as one ring
    if controller.has_rings():
        rings = controller._rings
    else:
        rings = [{"start": 0, "end": led_count - 1, "count": led_count}]

    num_rings = len(rings)

    # Colors
    stem_green = (20, 120, 20)
    stem_dark = (10, 60, 10)
    leaf_green = (40, 180, 40)

    rose_colors = [
        (255, 20, 80),    # Deep rose
        (255, 50, 100),   # Rose pink
        (255, 80, 120),   # Light rose
        (255, 100, 140),  # Pale rose
        (200, 20, 60),    # Dark rose
    ]

    bud_color = (180, 30, 60)
    center_color = (255, 200, 50)  # Yellow center

    # Phase timings
    phase1_end = 3.0    # Stem grows
    phase2_end = 4.5    # Bud forms
    phase3_end = 8.0    # Bloom
    phase4_end = 10.0   # Breathing glow
    phase5_end = duration  # Petals fall

    # State for stem (which LEDs in outer rings show stem)
    # Stem is a vertical line through one segment of each ring
    stem_segment = random.randint(0, 7)  # Random position around the ring

    while not controller._stop_animation.is_set():
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break

        frame = [(0, 0, 0)] * led_count
        t = elapsed

        # === PHASE 1: Stem Growing ===
        if elapsed < phase1_end:
            progress = elapsed / phase1_end

            # Stem grows from outer ring (index 0) toward center
            rings_to_show = int(progress * (num_rings - 1)) + 1

            for ring_idx in range(rings_to_show):
                ring = rings[ring_idx]
                ring_size = ring['count']

                # Find stem LEDs (2-3 LEDs per ring forming a line)
                stem_width = max(1, ring_size // 12)
                stem_start = int((stem_segment / 8) * ring_size) % ring_size

                for offset in range(stem_width):
                    led_idx = ring['start'] + ((stem_start + offset) % ring_size)
                    if led_idx <= ring['end'] and led_idx < led_count:
                        # Darker green for older (outer) parts
                        age_factor = 1.0 - (ring_idx / num_rings) * 0.3
                        stem_color = (
                            int(stem_green[0] * age_factor),
                            int(stem_green[1] * age_factor),
                            int(stem_green[2] * age_factor)
                        )
                        frame[led_idx] = stem_color

                # Add leaves to outer rings (small extensions)
                if ring_idx < num_rings // 2 and ring_size > 8:
                    # Left leaf
                    leaf_pos = (stem_start - stem_width - 1) % ring_size
                    led_idx = ring['start'] + leaf_pos
                    if led_idx <= ring['end'] and led_idx < led_count:
                        leaf_intensity = 0.7 - (ring_idx / num_rings) * 0.3
                        frame[led_idx] = (
                            int(leaf_green[0] * leaf_intensity),
                            int(leaf_green[1] * leaf_intensity),
                            int(leaf_green[2] * leaf_intensity)
                        )
                    # Right leaf
                    leaf_pos = (stem_start + stem_width + 1) % ring_size
                    led_idx = ring['start'] + leaf_pos
                    if led_idx <= ring['end'] and led_idx < led_count:
                        frame[led_idx] = (
                            int(leaf_green[0] * leaf_intensity),
                            int(leaf_green[1] * leaf_intensity),
                            int(leaf_green[2] * leaf_intensity)
                        )

        # === PHASE 2: Bud Forms ===
        elif elapsed < phase2_end:
            phase_progress = (elapsed - phase1_end) / (phase2_end - phase1_end)

            # Keep stem visible
            for ring_idx in range(num_rings - 1):
                ring = rings[ring_idx]
                ring_size = ring['count']
                stem_width = max(1, ring_size // 12)
                stem_start = int((stem_segment / 8) * ring_size) % ring_size

                for offset in range(stem_width):
                    led_idx = ring['start'] + ((stem_start + offset) % ring_size)
                    if led_idx <= ring['end'] and led_idx < led_count:
                        age_factor = 1.0 - (ring_idx / num_rings) * 0.3
                        frame[led_idx] = (
                            int(stem_green[0] * age_factor),
                            int(stem_green[1] * age_factor),
                            int(stem_green[2] * age_factor)
                        )

            # Bud forms at center and inner ring
            bud_intensity = phase_progress
            pulse = 0.8 + 0.2 * math.sin(t * 4)
            bud_intensity *= pulse

            # Center LED (if exists)
            center_ring = rings[-1]
            for i in range(center_ring['start'], center_ring['end'] + 1):
                if i < led_count:
                    frame[i] = (
                        int(bud_color[0] * bud_intensity),
                        int(bud_color[1] * bud_intensity),
                        int(bud_color[2] * bud_intensity)
                    )

            # Inner ring starts showing
            if phase_progress > 0.5:
                inner_ring = rings[-2]
                inner_intensity = (phase_progress - 0.5) * 2 * pulse
                for i in range(inner_ring['start'], inner_ring['end'] + 1):
                    if i < led_count:
                        frame[i] = (
                            int(bud_color[0] * inner_intensity),
                            int(bud_color[1] * inner_intensity),
                            int(bud_color[2] * inner_intensity)
                        )

        # === PHASE 3: Bloom ===
        elif elapsed < phase3_end:
            phase_elapsed = elapsed - phase2_end
            phase_duration = phase3_end - phase2_end
            phase_progress = phase_elapsed / phase_duration

            # Stem stays but fades slightly
            for ring_idx in range(num_rings - 1):
                ring = rings[ring_idx]
                ring_size = ring['count']
                stem_width = max(1, ring_size // 12)
                stem_start = int((stem_segment / 8) * ring_size) % ring_size

                for offset in range(stem_width):
                    led_idx = ring['start'] + ((stem_start + offset) % ring_size)
                    if led_idx <= ring['end'] and led_idx < led_count:
                        age_factor = 0.5 - (ring_idx / num_rings) * 0.2
                        frame[led_idx] = (
                            int(stem_green[0] * age_factor),
                            int(stem_green[1] * age_factor),
                            int(stem_green[2] * age_factor)
                        )

            # Bloom expands from center outward
            bloom_rings = int(phase_progress * num_rings) + 1
            bloom_rings = min(bloom_rings, num_rings)

            for ring_idx in range(num_rings - bloom_rings, num_rings):
                ring = rings[ring_idx]
                ring_size = ring['count']

                # How long this ring has been blooming
                ring_bloom_order = (num_rings - 1 - ring_idx)
                ring_appear_progress = ring_bloom_order / num_rings
                ring_age = max(0, phase_progress - ring_appear_progress)

                # Color varies by ring (darker at center, lighter outside)
                color_idx = min(len(rose_colors) - 1, ring_idx % len(rose_colors))
                rose_color = rose_colors[color_idx]

                # Petals spread around the ring
                for led_offset in range(ring_size):
                    led_idx = ring['start'] + led_offset
                    if led_idx > ring['end'] or led_idx >= led_count:
                        continue

                    # Petal pattern - varies intensity around ring
                    angle = (led_offset / ring_size) * math.pi * 2
                    petal_pattern = (math.sin(angle * 5 + t * 2) + 1) / 2
                    petal_pattern = 0.6 + petal_pattern * 0.4

                    intensity = min(1.0, ring_age * 3) * petal_pattern

                    frame[led_idx] = (
                        int(rose_color[0] * intensity),
                        int(rose_color[1] * intensity),
                        int(rose_color[2] * intensity)
                    )

            # Yellow center
            center_ring = rings[-1]
            for i in range(center_ring['start'], center_ring['end'] + 1):
                if i < led_count:
                    pulse = 0.8 + 0.2 * math.sin(t * 3)
                    frame[i] = (
                        int(center_color[0] * pulse),
                        int(center_color[1] * pulse),
                        int(center_color[2] * pulse)
                    )

        # === PHASE 4: Breathing Glow ===
        elif elapsed < phase4_end:
            phase_elapsed = elapsed - phase3_end

            # Full bloom with gentle breathing
            breath = 0.7 + 0.3 * math.sin(phase_elapsed * 2)

            for ring_idx, ring in enumerate(rings):
                ring_size = ring['count']
                color_idx = min(len(rose_colors) - 1, ring_idx % len(rose_colors))
                rose_color = rose_colors[color_idx]

                for led_offset in range(ring_size):
                    led_idx = ring['start'] + led_offset
                    if led_idx > ring['end'] or led_idx >= led_count:
                        continue

                    # Subtle petal shimmer
                    angle = (led_offset / ring_size) * math.pi * 2
                    shimmer = 0.9 + 0.1 * math.sin(angle * 5 + phase_elapsed * 1.5)

                    intensity = breath * shimmer

                    frame[led_idx] = (
                        int(rose_color[0] * intensity),
                        int(rose_color[1] * intensity),
                        int(rose_color[2] * intensity)
                    )

            # Center glows
            center_ring = rings[-1]
            for i in range(center_ring['start'], center_ring['end'] + 1):
                if i < led_count:
                    frame[i] = (
                        int(center_color[0] * breath),
                        int(center_color[1] * breath),
                        int(center_color[2] * breath)
                    )

        # === PHASE 5: Petals Fall ===
        else:
            phase_elapsed = elapsed - phase4_end
            phase_duration = phase5_end - phase4_end

            if phase_duration > 0:
                fall_progress = phase_elapsed / phase_duration

                # Petals fade from outer to inner
                for ring_idx, ring in enumerate(rings):
                    ring_size = ring['count']
                    color_idx = min(len(rose_colors) - 1, ring_idx % len(rose_colors))
                    rose_color = rose_colors[color_idx]

                    # Outer rings fade first
                    ring_fade_start = ring_idx / num_rings * 0.5
                    ring_fade = max(0, 1.0 - (fall_progress - ring_fade_start) / 0.5)

                    if ring_fade <= 0:
                        continue

                    for led_offset in range(ring_size):
                        led_idx = ring['start'] + led_offset
                        if led_idx > ring['end'] or led_idx >= led_count:
                            continue

                        # Random flutter as petals fall
                        flutter = random.uniform(0.8, 1.0) if ring_fade > 0.3 else ring_fade

                        intensity = ring_fade * flutter

                        frame[led_idx] = (
                            int(rose_color[0] * intensity),
                            int(rose_color[1] * intensity),
                            int(rose_color[2] * intensity)
                        )

        controller._update_frame(frame)
        time.sleep(0.03)  # ~33 FPS

    # Final off
    controller._update_frame([(0, 0, 0)] * led_count)
