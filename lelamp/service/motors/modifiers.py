"""
Animation Modifiers for LeLamp

Modifiers add dynamic overlays to animations - things like:
- Music bob (head nodding to BPM)
- Breathing (subtle periodic movement)
- Twitch (random small movements)
- Sway (drunk-like movement)

Modifiers are composable and stack additively on target joints.
"""

import math
import time
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Callable


class Modifier(ABC):
    """Base class for animation modifiers."""

    def __init__(self, name: str, target_joints: Set[str]):
        self.name = name
        self.target_joints = target_joints
        self.enabled = False
        self._start_time: float = 0.0

    def enable(self):
        """Enable the modifier."""
        self.enabled = True
        self._start_time = time.time()
        self.on_enable()

    def disable(self):
        """Disable the modifier."""
        self.enabled = False
        self.on_disable()

    def on_enable(self):
        """Called when modifier is enabled. Override for setup."""
        pass

    def on_disable(self):
        """Called when modifier is disabled. Override for cleanup."""
        pass

    @abstractmethod
    def get_offset(self, joint: str, current_time: float) -> float:
        """
        Calculate the offset to apply to a joint.

        Args:
            joint: Joint name (e.g., 'head_pitch.pos')
            current_time: Current time in seconds

        Returns:
            Offset in degrees to add to the joint position
        """
        pass

    def apply(self, action: Dict[str, float], current_time: float) -> Dict[str, float]:
        """
        Apply modifier offsets to an action.

        Args:
            action: Dict of joint positions
            current_time: Current time in seconds

        Returns:
            Modified action dict
        """
        if not self.enabled:
            return action

        modified = action.copy()
        for joint in self.target_joints:
            if joint in modified:
                offset = self.get_offset(joint, current_time)
                modified[joint] += offset

        return modified


@dataclass
class MusicConfig:
    """Configuration for music modifier."""
    amplitude: float = 12.0       # Degrees of movement (increased for more noticeable dance)
    beat_divisor: float = 1.0     # 1 = every beat, 2 = every 2 beats
    groove: float = 0.3           # 0-1, adds swing character
    joint: str = "wrist_pitch.pos"
    fallback_bpm: float = 110.0
    wave_spread: float = 0.08     # Phase offset between joints
    energy_threshold: float = 0.25
    energy_scale: float = 1.5


class MusicModifier(Modifier):
    """
    Lightweight music-synchronized movement overlay.

    Designed to be fast and not interfere with base animations.
    Uses cached values to minimize callback overhead.
    """

    def __init__(
        self,
        target_joints: Set[str] = None,
        config: MusicConfig = None,
        bpm_callback: Callable[[], float] = None,
        is_playing_callback: Callable[[], bool] = None,
        energy_callback: Callable[[], float] = None,
    ):
        self.config = config or MusicConfig()
        target_joints = target_joints or {self.config.joint}
        super().__init__("music", target_joints)

        self.bpm_callback = bpm_callback
        self.is_playing_callback = is_playing_callback
        self.energy_callback = energy_callback

        # Cached values (updated periodically, not every frame)
        self._cached_bpm = self.config.fallback_bpm
        self._cached_energy = 0.5
        self._cached_playing = False
        self._cache_counter = 0
        self._cache_interval = 15  # Update cache every 15 frames (~0.5s at 30fps)

        self._start_time = 0.0
        self._envelope = 0.0
        self._joint_order = list(target_joints)

    def set_bpm_callback(self, callback: Callable[[], float]):
        self.bpm_callback = callback

    def set_is_playing_callback(self, callback: Callable[[], bool]):
        self.is_playing_callback = callback

    def set_energy_callback(self, callback: Callable[[], float]):
        self.energy_callback = callback

    def set_amplitude(self, amplitude: float):
        self.config.amplitude = amplitude

    def set_beat_divisor(self, divisor: float):
        self.config.beat_divisor = max(0.25, divisor)

    def set_groove(self, groove: float):
        self.config.groove = max(0.0, min(1.0, groove))

    def update_target_joints(self, joints: Set[str]):
        self.target_joints = joints
        priority = ['wrist_pitch.pos', 'wrist_roll.pos', 'elbow_pitch.pos', 'base_pitch.pos', 'base_yaw.pos']
        self._joint_order = sorted(list(joints), key=lambda j: priority.index(j) if j in priority else 99)

    def on_enable(self):
        self._start_time = time.time()
        self._envelope = 0.0
        self._cache_counter = 0
        priority = ['wrist_pitch.pos', 'wrist_roll.pos', 'elbow_pitch.pos', 'base_pitch.pos', 'base_yaw.pos']
        self._joint_order = sorted(list(self.target_joints), key=lambda j: priority.index(j) if j in priority else 99)
        print(f"\033[95m🎵 DANCE: Enabled, joints={self._joint_order}\033[0m")

    def _update_cache(self):
        """Update cached values from callbacks (called periodically, not every frame)."""
        if self.is_playing_callback:
            try:
                self._cached_playing = self.is_playing_callback()
            except:
                pass

        if self._cached_playing:
            if self.bpm_callback:
                try:
                    bpm = self.bpm_callback()
                    if bpm > 0:
                        self._cached_bpm = bpm
                except:
                    pass

            if self.energy_callback:
                try:
                    self._cached_energy = self.energy_callback()
                except:
                    pass

    def get_offset(self, joint: str, current_time: float) -> float:
        if joint not in self.target_joints:
            return 0.0

        # Update cache periodically (not every frame)
        self._cache_counter += 1
        if self._cache_counter >= self._cache_interval:
            self._cache_counter = 0
            self._update_cache()

        # Smooth envelope
        target = 1.0 if self._cached_playing else 0.0
        self._envelope += (target - self._envelope) * 0.1

        if self._envelope < 0.02:
            return 0.0

        # Energy scaling
        energy = self._cached_energy
        if energy < self.config.energy_threshold:
            energy_mult = 0.0
        else:
            energy_mult = (energy - self.config.energy_threshold) / (1.0 - self.config.energy_threshold)

        if energy_mult < 0.02:
            return 0.0

        # Simple phase calculation
        elapsed = current_time - self._start_time
        freq = (self._cached_bpm / 60.0) / self.config.beat_divisor

        # Joint phase offset for wave effect
        try:
            idx = self._joint_order.index(joint)
        except ValueError:
            idx = 0
        phase = (elapsed * freq + idx * self.config.wave_spread) % 1.0

        # Simple sine wave with optional groove
        wave = math.sin(phase * 2 * math.pi)
        if self.config.groove > 0:
            # Add subtle bounce harmonic
            wave += math.sin(phase * 4 * math.pi) * 0.1 * self.config.groove

        return wave * self.config.amplitude * energy_mult * self._envelope


@dataclass
class BreathingConfig:
    """Configuration for breathing modifier."""
    amplitude: float = 2.0      # Degrees of movement
    frequency: float = 0.2      # Breaths per second (0.2 = 12 breaths/min)
    phase_offset: float = 0.0   # Phase offset in radians


class BreathingModifier(Modifier):
    """
    Subtle breathing motion - slow, periodic movement.

    Creates a gentle sine wave motion that simulates breathing,
    making the lamp feel more alive even when idle.
    """

    def __init__(
        self,
        target_joints: Set[str] = None,
        config: BreathingConfig = None,
    ):
        target_joints = target_joints or {"head_pitch.pos"}
        super().__init__("breathing", target_joints)
        self.config = config or BreathingConfig()

    def get_offset(self, joint: str, current_time: float) -> float:
        if joint not in self.target_joints:
            return 0.0

        elapsed = current_time - self._start_time
        phase = (elapsed * self.config.frequency * 2 * math.pi) + self.config.phase_offset

        # Smooth sine wave for natural breathing feel
        return math.sin(phase) * self.config.amplitude


@dataclass
class TwitchConfig:
    """Configuration for twitch modifier."""
    amplitude: float = 3.0          # Max degrees of twitch
    min_interval: float = 3.0       # Min seconds between twitches
    max_interval: float = 10.0      # Max seconds between twitches
    twitch_duration: float = 0.15   # Duration of twitch in seconds


class TwitchModifier(Modifier):
    """
    Random occasional twitch - small sudden movements.

    Creates occasional quick movements that add character,
    like a nervous twitch or sudden alertness.
    """

    def __init__(
        self,
        target_joints: Set[str] = None,
        config: TwitchConfig = None,
    ):
        target_joints = target_joints or {"head_pitch.pos", "head_yaw.pos"}
        super().__init__("twitch", target_joints)
        self.config = config or TwitchConfig()

        self._next_twitch_time = 0.0
        self._twitch_start_time = 0.0
        self._twitch_offsets: Dict[str, float] = {}
        self._is_twitching = False

    def on_enable(self):
        self._schedule_next_twitch()

    def _schedule_next_twitch(self):
        """Schedule the next random twitch."""
        interval = random.uniform(self.config.min_interval, self.config.max_interval)
        self._next_twitch_time = time.time() + interval
        self._is_twitching = False

    def _start_twitch(self):
        """Start a new twitch with random offsets."""
        self._is_twitching = True
        self._twitch_start_time = time.time()
        self._twitch_offsets = {
            joint: random.uniform(-self.config.amplitude, self.config.amplitude)
            for joint in self.target_joints
        }

    def get_offset(self, joint: str, current_time: float) -> float:
        if joint not in self.target_joints:
            return 0.0

        # Check if it's time to twitch
        if not self._is_twitching and current_time >= self._next_twitch_time:
            self._start_twitch()

        if not self._is_twitching:
            return 0.0

        # Calculate twitch progress
        twitch_elapsed = current_time - self._twitch_start_time
        if twitch_elapsed >= self.config.twitch_duration:
            self._schedule_next_twitch()
            return 0.0

        # Quick in, quick out using sine
        progress = twitch_elapsed / self.config.twitch_duration
        intensity = math.sin(progress * math.pi)  # 0 -> 1 -> 0

        return self._twitch_offsets.get(joint, 0.0) * intensity


@dataclass
class SwayConfig:
    """Configuration for sway modifier."""
    amplitude: float = 8.0          # Degrees of sway
    frequency: float = 0.15         # Sways per second
    secondary_frequency: float = 0.23  # Secondary wave for organic feel
    secondary_amplitude: float = 3.0


class SwayModifier(Modifier):
    """
    Drunk-like swaying motion.

    Creates a slow, wavering motion using multiple overlapping
    sine waves for an organic, unsteady feeling.
    """

    def __init__(
        self,
        target_joints: Set[str] = None,
        config: SwayConfig = None,
    ):
        target_joints = target_joints or {"base_yaw.pos", "head_roll.pos"}
        super().__init__("sway", target_joints)
        self.config = config or SwayConfig()

    def get_offset(self, joint: str, current_time: float) -> float:
        if joint not in self.target_joints:
            return 0.0

        elapsed = current_time - self._start_time

        # Primary wave
        primary = math.sin(elapsed * self.config.frequency * 2 * math.pi)
        primary *= self.config.amplitude

        # Secondary wave (different frequency for organic feel)
        secondary = math.sin(elapsed * self.config.secondary_frequency * 2 * math.pi)
        secondary *= self.config.secondary_amplitude

        return primary + secondary


class ModifierStack:
    """
    Manages a collection of modifiers and applies them to actions.

    Usage:
        stack = ModifierStack()
        stack.add(MusicBobModifier(...))
        stack.add(BreathingModifier(...))

        # In animation loop:
        action = stack.apply(action)
    """

    def __init__(self):
        self._modifiers: Dict[str, Modifier] = {}

    def add(self, modifier: Modifier):
        """Add a modifier to the stack."""
        self._modifiers[modifier.name] = modifier

    def remove(self, name: str):
        """Remove a modifier by name."""
        if name in self._modifiers:
            self._modifiers[name].disable()
            del self._modifiers[name]

    def get(self, name: str) -> Optional[Modifier]:
        """Get a modifier by name."""
        return self._modifiers.get(name)

    def enable(self, name: str) -> bool:
        """Enable a modifier by name."""
        if name in self._modifiers:
            self._modifiers[name].enable()
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a modifier by name."""
        if name in self._modifiers:
            self._modifiers[name].disable()
            return True
        return False

    def is_enabled(self, name: str) -> bool:
        """Check if a modifier is enabled."""
        mod = self._modifiers.get(name)
        return mod.enabled if mod else False

    def list_modifiers(self) -> Dict[str, bool]:
        """List all modifiers and their enabled state."""
        return {name: mod.enabled for name, mod in self._modifiers.items()}

    def apply(self, action: Dict[str, float]) -> Dict[str, float]:
        """Apply all enabled modifiers to an action."""
        current_time = time.time()
        result = action.copy()

        for modifier in self._modifiers.values():
            if modifier.enabled:
                result = modifier.apply(result, current_time)

        return result
