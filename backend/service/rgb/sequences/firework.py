"""Firework - Explosive celebration animation"""

import time
import math
import random
from typing import Optional, Tuple, List
from . import register_animation, get_frame_interval


@register_animation(
    name="firework",
    description="Explosive firework bursts from center - use for celebrations, achievements, or exciting moments."
)
def firework(controller, color: Optional[Tuple[int, int, int]] = None, duration: float = 10.0):
    """
    Firework animation:
    - Multiple bursts launch from center
    - Explode outward through rings
    - Trails fade with sparkle effects
    - Random vibrant colors
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

    # Reverse to get center-first order (fireworks explode outward)
    rings_center_first = list(reversed(rings))
    num_rings = len(rings_center_first)

    # Firework colors (vibrant celebration colors)
    firework_colors = [
        (255, 50, 50),    # Red
        (50, 255, 50),    # Green
        (50, 50, 255),    # Blue
        (255, 200, 50),   # Gold
        (255, 50, 200),   # Magenta
        (50, 255, 255),   # Cyan
        (255, 100, 50),   # Orange
        (200, 50, 255),   # Purple
        (255, 255, 255),  # White
    ]

    # Track active firework bursts
    # Each burst: {launch_time, color, ring_progress, particles}
    active_bursts: List[dict] = []

    # Frame buffer for fading trails
    trail_frame = [(0, 0, 0)] * led_count

    # Time between bursts
    burst_interval = 1.2
    last_burst_time = start_time - burst_interval  # Launch immediately

    while not controller._stop_animation.is_set():
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break

        current_time = time.time()
        frame = [(0, 0, 0)] * led_count

        # === Fade trail frame ===
        trail_frame = [
            (max(0, c[0] - 15), max(0, c[1] - 15), max(0, c[2] - 15))
            for c in trail_frame
        ]

        # === Launch new burst periodically ===
        if current_time - last_burst_time >= burst_interval:
            last_burst_time = current_time
            burst_color = random.choice(firework_colors)

            # Create particle positions for explosion pattern
            # Each particle has a position within its ring and a random offset
            particles = []
            for ring_idx in range(num_rings):
                ring = rings_center_first[ring_idx]
                ring_size = ring['count']
                # More particles for larger rings
                num_particles = max(1, ring_size // 4)
                for _ in range(num_particles):
                    particles.append({
                        'ring_idx': ring_idx,
                        'offset': random.uniform(0, ring_size),
                        'speed': random.uniform(0.8, 1.2),
                    })

            active_bursts.append({
                'launch_time': current_time,
                'color': burst_color,
                'particles': particles,
            })

        # === Update and render active bursts ===
        bursts_to_remove = []

        for burst_idx, burst in enumerate(active_bursts):
            burst_elapsed = current_time - burst['launch_time']
            burst_duration = 1.5  # Total burst animation time

            if burst_elapsed >= burst_duration:
                bursts_to_remove.append(burst_idx)
                continue

            progress = burst_elapsed / burst_duration
            burst_color = burst['color']

            # Explosion expands outward (ring_progress goes from 0 to num_rings)
            ring_progress = progress * (num_rings + 1)

            # Intensity fades as burst ages
            burst_intensity = 1.0 - (progress ** 0.5)

            for particle in burst['particles']:
                p_ring_idx = particle['ring_idx']
                p_offset = particle['offset']
                p_speed = particle['speed']

                # Particle appears when explosion reaches its ring
                particle_appear_time = p_ring_idx / (num_rings + 1) * burst_duration

                if burst_elapsed < particle_appear_time:
                    continue

                # Particle fades after appearing
                particle_age = burst_elapsed - particle_appear_time
                particle_fade = max(0, 1.0 - particle_age / (burst_duration * 0.6))

                if particle_fade <= 0:
                    continue

                ring = rings_center_first[p_ring_idx]
                ring_size = ring['count']

                # LED position (particles spread slightly as they age)
                spread = particle_age * p_speed * 3
                led_offset = int((p_offset + spread) % ring_size)
                led_idx = ring['start'] + led_offset

                if led_idx > ring['end'] or led_idx >= led_count:
                    continue

                intensity = burst_intensity * particle_fade
                particle_color = (
                    int(burst_color[0] * intensity),
                    int(burst_color[1] * intensity),
                    int(burst_color[2] * intensity)
                )

                # Add to trail and frame
                trail_frame[led_idx] = (
                    min(255, max(trail_frame[led_idx][0], particle_color[0])),
                    min(255, max(trail_frame[led_idx][1], particle_color[1])),
                    min(255, max(trail_frame[led_idx][2], particle_color[2]))
                )
                frame[led_idx] = (
                    min(255, max(frame[led_idx][0], particle_color[0])),
                    min(255, max(frame[led_idx][1], particle_color[1])),
                    min(255, max(frame[led_idx][2], particle_color[2]))
                )

        # Remove finished bursts (in reverse order to preserve indices)
        for idx in reversed(bursts_to_remove):
            active_bursts.pop(idx)

        # === Combine trail and active frame ===
        final_frame = []
        for i in range(led_count):
            r = max(frame[i][0], trail_frame[i][0])
            g = max(frame[i][1], trail_frame[i][1])
            b = max(frame[i][2], trail_frame[i][2])
            final_frame.append((r, g, b))

        # === Add random sparkles for extra magic ===
        if random.random() < 0.3:
            sparkle_idx = random.randint(0, led_count - 1)
            final_frame[sparkle_idx] = (255, 255, 255)

        controller._update_frame(final_frame)
        time.sleep(0.025)  # ~40 FPS

    # Fade out
    for fade_step in range(20):
        fade = 1.0 - (fade_step / 20)
        faded_frame = [
            (int(c[0] * fade), int(c[1] * fade), int(c[2] * fade))
            for c in trail_frame
        ]
        controller._update_frame(faded_frame)
        time.sleep(0.03)

    # Final off
    controller._update_frame([(0, 0, 0)] * led_count)
