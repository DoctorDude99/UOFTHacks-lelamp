import os
import csv
import time
import random
import threading
from typing import Any, List, Dict, Optional, Tuple, Callable
from lelamp.follower import LeLampFollowerConfig, LeLampFollower
from lelamp.service.motors.modifiers import (
    ModifierStack,
    MusicModifier, MusicConfig,
    BreathingModifier, BreathingConfig,
    TwitchModifier, TwitchConfig,
    SwayModifier, SwayConfig,
)
from lelamp.user_data import (
    get_recording_path,
    save_recording_path,
    list_all_recordings,
    get_recordings_paths,
    USER_RECORDINGS_DIR,
)

LAMP_ID = "lelamp"


class AnimationService:
    def __init__(self, port: str, fps: int = 30, duration: float = 5.0, idle_recording: str = "idle", config: Dict = None):
        self.port = port
        self.fps = fps
        self.duration = duration
        self.idle_recording = idle_recording
        self.robot_config = LeLampFollowerConfig(port=port, id=LAMP_ID)
        self.robot: LeLampFollower = None
        self.recordings_dir = os.path.join(os.path.dirname(__file__), "..", "..", "recordings")

        # State management
        self._recording_cache: Dict[str, List[Dict[str, float]]] = {}
        self._current_state: Optional[Dict[str, float]] = None
        self._current_recording: Optional[str] = None
        self._current_frame_index: int = 0
        self._current_actions: List[Dict[str, float]] = []
        self._interpolation_frames: int = 0
        self._interpolation_target: Optional[Dict[str, float]] = None

        # Custom event handling
        self._running = threading.Event()
        self._event_queue = []
        self._event_lock = threading.Lock()
        self._bus_lock = threading.Lock()  # Lock for servo bus access
        self._event_thread: Optional[threading.Thread] = None
        self._pushable_mode = False  # When True, animations are paused
        self._sleep_mode = False  # When True, block all animations except sleep

        # Face tracking mode
        self._face_tracking_mode = False
        self._face_tracking_lock = threading.Lock()
        # Target angles (where face is)
        self._face_target_yaw = 0.0
        self._face_target_pitch = 0.0
        # Current smoothed angles (what motors are doing)
        self._face_current_yaw = 0.0
        self._face_current_pitch = 0.0
        # Tracking parameters
        self._face_tracking_speed = 0.15  # Interpolation factor (0-1, higher = faster)
        self._face_yaw_scale = 45.0  # Max degrees of yaw movement
        self._face_pitch_scale = 25.0  # Max degrees of pitch movement
        self._face_deadzone = 0.05  # Ignore tiny movements
        # Base position (center point to offset from)
        self._face_base_yaw = 0.0
        self._face_base_pitch = 0.0
        self._face_last_detected = False

        # Animation modifiers (music bob, breathing, etc.)
        self._modifiers = ModifierStack()
        modifiers_config = config.get("modifiers", {}) if config else {}
        self._init_modifiers(modifiers_config)

        # Energy-based dance mode - load thresholds from config
        music_cfg = modifiers_config.get("music", {})
        self._dance_mode = False
        self._dance_energy_callback: Optional[Callable[[], float]] = None
        self._dance_threshold = music_cfg.get("dance_threshold", 0.25)  # Energy above this triggers dancing animations
        self._excited_threshold = music_cfg.get("excited_threshold", 0.6)  # Energy above this triggers excited dancing
        self._dance_animations = ["dancing1", "dancing2", "dancing3"]
        self._excited_animations = ["dancing-excited1", "dancing-excited2", "dancing-excited3", "dancing-excited4", "dancing-excited5"]
        self._last_dance_animation: Optional[str] = None  # Track last played to avoid repeats
        print(f"💃 ANIMATION SERVICE: Dance thresholds loaded - dance={self._dance_threshold}, excited={self._excited_threshold}")

    def _init_modifiers(self, modifiers_config: Dict):
        """Initialize modifiers from config."""
        # Music modifier
        music_cfg = modifiers_config.get("music", {})

        # Support both 'joint' (singular, legacy) and 'joints' (list, new format)
        default_joint = music_cfg.get("joint", "wrist_pitch.pos")
        joints_list = music_cfg.get("joints", [default_joint])
        if isinstance(joints_list, str):
            joints_list = [joints_list]

        music_modifier = MusicModifier(
            target_joints=set(joints_list) if joints_list else {default_joint},
            config=MusicConfig(
                amplitude=music_cfg.get("amplitude", 12.0),
                beat_divisor=music_cfg.get("beat_divisor", 1.0),
                groove=music_cfg.get("groove", 0.3),
                wave_spread=music_cfg.get("wave_spread", 0.08),
                energy_threshold=music_cfg.get("energy_threshold", 0.25),
                joint=default_joint,
            )
        )
        self._modifiers.add(music_modifier)

        # Auto-enable if config says so
        if music_cfg.get("enabled", False):
            self._modifiers.enable("music")
            print(f"🎵 ANIMATION SERVICE: Music modifier auto-enabled from config")

        # Breathing modifier
        breathing_cfg = modifiers_config.get("breathing", {})
        breathing_modifier = BreathingModifier(
            config=BreathingConfig(
                amplitude=breathing_cfg.get("amplitude", 2.0),
                frequency=breathing_cfg.get("frequency", 0.2),
            )
        )
        self._modifiers.add(breathing_modifier)
        if breathing_cfg.get("enabled", False):
            breathing_modifier.enable()

        # Twitch modifier
        twitch_cfg = modifiers_config.get("twitch", {})
        twitch_modifier = TwitchModifier(
            config=TwitchConfig(
                amplitude=twitch_cfg.get("amplitude", 3.0),
                min_interval=twitch_cfg.get("min_interval", 3.0),
                max_interval=twitch_cfg.get("max_interval", 10.0),
            )
        )
        self._modifiers.add(twitch_modifier)
        if twitch_cfg.get("enabled", False):
            twitch_modifier.enable()

        # Sway modifier
        sway_cfg = modifiers_config.get("sway", {})
        sway_modifier = SwayModifier(
            config=SwayConfig(
                amplitude=sway_cfg.get("amplitude", 8.0),
                frequency=sway_cfg.get("frequency", 0.15),
            )
        )
        self._modifiers.add(sway_modifier)
        if sway_cfg.get("enabled", False):
            sway_modifier.enable()

    def connect_spotify_service(self, spotify_service):
        """
        Connect to SpotifyService for BPM and energy-synced music modifier.

        Args:
            spotify_service: SpotifyService instance
        """
        music_mod = self._modifiers.get("music")
        if music_mod and hasattr(spotify_service, 'get_current_bpm'):
            music_mod.set_bpm_callback(spotify_service.get_current_bpm)
            music_mod.set_is_playing_callback(spotify_service.is_playing)
            # Connect energy callback for dynamic intensity
            if hasattr(spotify_service, 'get_energy'):
                music_mod.set_energy_callback(spotify_service.get_energy)
                # Also store for dance animation selection
                self._dance_energy_callback = spotify_service.get_energy
                print("🎵 ANIMATION SERVICE: Connected music modifier to Spotify (BPM + energy)")
            else:
                print("🎵 ANIMATION SERVICE: Connected music modifier to Spotify (BPM only)")

    # ==================== Energy-Based Dance Mode ====================

    def set_dance_thresholds(self, dance_threshold: float = 0.25, excited_threshold: float = 0.6):
        """Set energy thresholds for dance animation selection."""
        self._dance_threshold = dance_threshold
        self._excited_threshold = excited_threshold
        print(f"💃 ANIMATION SERVICE: Dance thresholds set - dance={dance_threshold}, excited={excited_threshold}")

    def start_dance_mode(self):
        """
        Start energy-based dance mode.
        When energy > threshold, plays dancing animations; otherwise just uses modifier.
        """
        if self._dance_mode:
            return

        self._dance_mode = True
        self._last_dance_animation = None

        # Check energy and start appropriate animation
        energy = self._get_current_energy()
        print(f"💃 ANIMATION SERVICE: Starting dance mode (energy={energy:.2f})")

        if energy >= self._dance_threshold:
            self._play_dance_animation(energy)
        else:
            print(f"💃 ANIMATION SERVICE: Energy {energy:.2f} below threshold {self._dance_threshold}, waiting for energy increase")

    def stop_dance_mode(self):
        """Stop dance mode and return to idle."""
        if not self._dance_mode:
            return

        self._dance_mode = False
        self._last_dance_animation = None
        print("💃 ANIMATION SERVICE: Stopping dance mode, returning to idle")

        # Return to idle
        self.dispatch("play", self.idle_recording)

    def is_dance_mode(self) -> bool:
        """Check if dance mode is currently active."""
        return self._dance_mode

    def _get_current_energy(self) -> float:
        """Get current energy level from Spotify callback."""
        if self._dance_energy_callback:
            try:
                return self._dance_energy_callback()
            except Exception:
                return 0.0
        return 0.0

    def _play_dance_animation(self, energy: float):
        """Select and play appropriate dance animation based on energy level."""
        if energy >= self._excited_threshold:
            # High energy - play excited dance animation
            animations = self._excited_animations
            animation_type = "excited"
        else:
            # Normal energy - play regular dance animation
            animations = self._dance_animations
            animation_type = "normal"

        # Filter to only animations that exist
        available = [a for a in animations if self._load_recording(a) is not None]

        if not available:
            print(f"💃 ANIMATION SERVICE: No {animation_type} dance animations available!")
            return

        # Pick random animation, avoiding repeat of last one
        if len(available) > 1 and self._last_dance_animation in available:
            available = [a for a in available if a != self._last_dance_animation]

        selected = random.choice(available)
        self._last_dance_animation = selected
        print(f"💃 ANIMATION SERVICE: Playing {animation_type} dance animation '{selected}' (energy={energy:.2f})")
        self.dispatch("play", selected)

    def enable_modifier(self, name: str) -> bool:
        """Enable a modifier by name."""
        result = self._modifiers.enable(name)
        print(f"\033[95m🎛️ ANIMATION SERVICE: enable_modifier('{name}') called, result={result}\033[0m")
        print(f"\033[95m🎛️ ANIMATION SERVICE: current_recording={self._current_recording}, "
              f"frame={self._current_frame_index}/{len(self._current_actions) if self._current_actions else 0}, "
              f"running={self._running.is_set()}\033[0m")
        return result

    def disable_modifier(self, name: str) -> bool:
        """Disable a modifier by name."""
        result = self._modifiers.disable(name)
        if result:
            print(f"🎛️ ANIMATION SERVICE: Disabled modifier '{name}'")
        return result

    def is_modifier_enabled(self, name: str) -> bool:
        """Check if a modifier is enabled."""
        return self._modifiers.is_enabled(name)

    def list_modifiers(self) -> Dict[str, bool]:
        """List all modifiers and their enabled state."""
        return self._modifiers.list_modifiers()

    def get_modifier(self, name: str):
        """Get a modifier by name for direct configuration."""
        return self._modifiers.get(name)

    def set_music_beat_divisor(self, divisor: float):
        """
        Set the beat divisor for the music modifier.

        Args:
            divisor: 1=every beat, 2=half beat, 4=quarter beat, 0.5=every 2 beats
        """
        music_mod = self._modifiers.get("music")
        if music_mod:
            music_mod.set_beat_divisor(divisor)
            print(f"🎵 ANIMATION SERVICE: Beat divisor set to {divisor}")

    def set_music_amplitude(self, amplitude: float):
        """Set the amplitude (degrees) for the music modifier."""
        music_mod = self._modifiers.get("music")
        if music_mod:
            music_mod.set_amplitude(amplitude)
            print(f"🎵 ANIMATION SERVICE: Amplitude set to {amplitude}")

    def start(self):
        # Check if motors are enabled in config
        import lelamp.globals as g
        motors_config = g.CONFIG.get("motors", {})
        if not motors_config.get("enabled", True):
            print("ℹ️ Motors disabled in config - animation service not started")
            return

        self.robot = LeLampFollower(self.robot_config)

        # Check if calibration file exists before connecting
        if not os.path.exists(self.robot.calibration_fpath):
            # Set global flag for post-assembly setup
            g.calibration_required = True
            g.calibration_path = self.robot.calibration_fpath
            print(f"⚠️ Calibration required: {self.robot.calibration_fpath}")
            print(f"ℹ️ Animation service will remain disabled until calibration is complete")
            print(f"   Complete setup wizard at WebUI or run: uv run -m lelamp.calibrate --port {self.port}")
            # Don't raise error - just return without connecting
            return

        self.robot.connect(calibrate=True)
        print(f"Animation service connected to {self.port}")
        
        # Start event processing thread
        self._running.set()
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()
        
        # Initialize with idle recording via self dispatch
        # self.dispatch("play", self.idle_recording)

    def stop(self, timeout: float = 5.0):
        # Stop event processing
        self._running.clear()
        if self._event_thread and self._event_thread.is_alive():
            self._event_thread.join(timeout=timeout)
        
        if self.robot:
            self.robot.disconnect()
            self.robot = None
    
    def dispatch(self, event_type: str, payload: Any):
        """Dispatch an event - same interface as ServiceBase"""
        if not self._running.is_set():
            print(f"Animation service is not running, ignoring event {event_type}")
            return

        with self._event_lock:
            self._event_queue.append((event_type, payload))

    def set_sleep_mode(self, enabled: bool, release_motors: bool = False):
        """Enable or disable sleep mode - blocks all animations except 'sleep' when enabled

        Args:
            enabled: Whether to enable sleep mode
            release_motors: If True AND enabled=True, also release motor torque.
                           Set to False when starting sleep animation, True when animation completes.
        """
        self._sleep_mode = enabled
        print(f"🔒 ANIMATION SERVICE: Sleep mode set to {enabled}")

        # Only release motors if explicitly requested (after animation completes)
        if enabled and release_motors and self.robot and self.robot.bus:
            try:
                self.robot.bus.disable_torque()
                print("💤 ANIMATION SERVICE: Released motors (torque disabled) for sleep mode")
            except Exception as e:
                print(f"⚠️ ANIMATION SERVICE: Error disabling motor torque: {e}")

    def set_face_tracking_mode(self, enabled: bool):
        """Enable or disable face tracking mode"""
        was_enabled = self._face_tracking_mode
        self._face_tracking_mode = enabled

        if enabled and not was_enabled:
            # Starting face tracking - capture current position as base
            if self.robot and self.robot.bus:
                try:
                    current_pos = self.robot.bus.sync_read("Present_Position")
                    self._face_base_yaw = current_pos.get('base_yaw', 0.0)
                    self._face_base_pitch = current_pos.get('base_pitch', 0.0)
                    self._face_current_yaw = self._face_base_yaw
                    self._face_current_pitch = self._face_base_pitch
                    self._face_target_yaw = self._face_base_yaw
                    self._face_target_pitch = self._face_base_pitch
                except Exception as e:
                    print(f"👁️ FACE TRACKING: Could not read base position: {e}")

        if not enabled:
            with self._face_tracking_lock:
                self._face_target_yaw = self._face_base_yaw
                self._face_target_pitch = self._face_base_pitch
                self._face_last_detected = False

        print(f"👁️ ANIMATION SERVICE: Face tracking motor mode set to {enabled}")

    def update_face_position(self, x: float, y: float, detected: bool):
        """
        Update face tracking with normalized face position.

        Args:
            x: Face X position, -1.0 (left) to 1.0 (right)
            y: Face Y position, -1.0 (top) to 1.0 (bottom)
            detected: Whether a face is currently detected
        """
        if not self._face_tracking_mode:
            return

        with self._face_tracking_lock:
            if detected:
                # Apply deadzone
                if abs(x) < self._face_deadzone:
                    x = 0.0
                if abs(y) < self._face_deadzone:
                    y = 0.0

                # Convert face position to target motor angles
                # Face on right (x > 0) -> lamp should yaw right (positive)
                # Face above center (y < 0) -> lamp should pitch up (negative pitch)
                self._face_target_yaw = self._face_base_yaw + (x * self._face_yaw_scale)
                self._face_target_pitch = self._face_base_pitch + (y * self._face_pitch_scale)

                # Clamp to safe limits
                self._face_target_yaw = max(-60, min(60, self._face_target_yaw))
                self._face_target_pitch = max(-30, min(30, self._face_target_pitch))

                self._face_last_detected = True
            else:
                # No face - gradually return to base position
                if self._face_last_detected:
                    self._face_target_yaw = self._face_base_yaw
                    self._face_target_pitch = self._face_base_pitch
                    self._face_last_detected = False

    def update_face_tracking_target(self, yaw_adj: float, pitch_adj: float):
        """Legacy method - use update_face_position instead"""
        # Keep for backwards compatibility
        pass
    
    def _event_loop(self):
        """Custom event loop that supports interruption"""
        while self._running.is_set():
            # Check for events
            with self._event_lock:
                if self._event_queue:
                    event_type, payload = self._event_queue.pop(0)
                else:
                    event_type, payload = None, None
            
            if event_type:
                try:
                    self.handle_event(event_type, payload)
                except Exception as e:
                    print(f"Error handling event {event_type}: {e}")
            
            # Continue current playback
            self._continue_playback()
            
            time.sleep(1.0 / self.fps)  # Frame rate timing
    
    def handle_event(self, event_type: str, payload: Any):
        if event_type == "play":
            self._handle_play(payload)
        else:
            print(f"Unknown event type: {event_type}")
    
    def _handle_play(self, recording_name: str):
        """Start playing a recording with interpolation from current state"""
        if not self.robot:
            print("Robot not connected")
            return

        # Block animations in sleep mode (except sleep/wake_up animations)
        if self._sleep_mode and recording_name not in ["sleep", "wake_up", "timer_up", "alarm"]:
            print(f"🚫 ANIMATION SERVICE: Blocked animation '{recording_name}' - in sleep mode (_sleep_mode=True)")
            return

        # Load the recording
        actions = self._load_recording(recording_name)
        if actions is None:
            return

        print(f"Starting {recording_name} with interpolation")

        # Set up new playback
        self._current_recording = recording_name
        self._current_actions = actions
        self._current_frame_index = 0

        # If we don't have a current state, read it from motors first
        # This ensures smooth interpolation even after sleep/wake or service restart
        if self._current_state is None and self.robot and self.robot.bus:
            try:
                current_pos = self.robot.bus.sync_read("Present_Position")
                # Convert to action format (add .pos suffix)
                self._current_state = {f"{k}.pos": v for k, v in current_pos.items()}
                print(f"📍 ANIMATION SERVICE: Read current motor positions for interpolation: {self._current_state}")
            except Exception as e:
                print(f"⚠️ ANIMATION SERVICE: Could not read motor positions: {e}")

        # Set up interpolation to the first frame
        if self._current_state is not None:
            self._interpolation_frames = int(self.duration * self.fps)
            self._interpolation_target = actions[0]
        else:
            self._interpolation_frames = 0
            self._interpolation_target = None
    
    def _continue_playback(self):
        """Continue current playback - called every frame"""
        # In manual control override (dashboard sliders), skip animation processing
        # Motors hold position - no goal updates, just wait for slider commands
        if getattr(self, 'manual_control_override', False):
            return

        # In pushable mode (physical hand movement), continuously update goal to current position
        # This makes motors compliant - they follow where you push them
        if self._pushable_mode:
            if self._bus_lock.acquire(blocking=False):
                try:
                    if self.robot:
                        self.robot.update_goal_to_current_position()
                finally:
                    self._bus_lock.release()
            return

        # Stop any ongoing animation if entering sleep mode (except allowed animations)
        if self._sleep_mode and self._current_recording not in ["sleep", "wake_up", "timer_up", "alarm", None]:
            print(f"🚫 ANIMATION SERVICE: Stopping animation '{self._current_recording}' - entered sleep mode")
            self._current_recording = None
            self._current_actions = []
            self._current_frame_index = 0

            # Release motors when stopping animation due to sleep mode
            if self.robot and self.robot.bus:
                try:
                    self.robot.bus.disable_torque()
                    print("💤 ANIMATION SERVICE: Released motors (torque disabled) for sleep mode")
                except Exception as e:
                    print(f"⚠️ ANIMATION SERVICE: Error disabling motor torque: {e}")

            return

        # Face tracking mode - adjust yaw/pitch based on face position
        if self._face_tracking_mode and not self._current_recording:
            self._process_face_tracking()
            return

        # Apply modifiers even when no animation is playing (for music bob, etc.)
        if not self._current_recording or not self._current_actions:
            # If any modifiers are enabled, apply them to current position
            enabled_mods = {k: v for k, v in self._modifiers.list_modifiers().items() if v}
            if enabled_mods:
                if self._bus_lock.acquire(blocking=False):
                    try:
                        # Initialize current state from motors if not set
                        if self._current_state is None:
                            current_pos = self.robot.bus.sync_read("Present_Position")
                            # Convert to action format (add .pos suffix)
                            self._current_state = {f"{k}.pos": v for k, v in current_pos.items()}
                            print(f"\033[93m🎵 ANIM SVC: Initialized state from motors: {list(self._current_state.keys())}\033[0m")

                        original_pitch = self._current_state.get("head_pitch.pos", 0)
                        modified_action = self._modifiers.apply(self._current_state)
                        modified_pitch = modified_action.get("head_pitch.pos", 0)

                        # Debug: show difference every 30 frames
                        if not hasattr(self, '_mod_debug_counter'):
                            self._mod_debug_counter = 0
                        self._mod_debug_counter += 1
                        if self._mod_debug_counter % 30 == 0:
                            diff = modified_pitch - original_pitch
                            print(f"\033[93m🎵 ANIM SVC: Applying modifiers {list(enabled_mods.keys())}, head_pitch diff={diff:.2f}°\033[0m")

                        self.robot.send_action(modified_action)
                    except Exception as e:
                        print(f"Error applying modifiers: {e}")
                    finally:
                        self._bus_lock.release()
            return

        # Try to acquire lock, skip frame if bus is busy
        if not self._bus_lock.acquire(blocking=False):
            return

        try:
            # Handle interpolation to first frame
            if self._interpolation_frames > 0 and self._interpolation_target is not None:
                # Calculate interpolation progress
                progress = 1.0 - (self._interpolation_frames / (self.duration * self.fps))
                progress = max(0.0, min(1.0, progress))

                # Interpolate between current state and target
                interpolated_action = {}
                for joint in self._interpolation_target.keys():
                    current_val = self._current_state.get(joint, 0)
                    target_val = self._interpolation_target[joint]
                    interpolated_action[joint] = current_val + (target_val - current_val) * progress

                # Apply modifiers (music bob, breathing, etc.)
                modified_action = self._modifiers.apply(interpolated_action)
                self.robot.send_action(modified_action)
                self._current_state = interpolated_action.copy()  # Store unmodified for smooth transitions
                self._interpolation_frames -= 1
                return

            # Play current frame
            if self._current_frame_index < len(self._current_actions):
                action = self._current_actions[self._current_frame_index]
                # Apply modifiers (music bob, breathing, etc.)
                original_pitch = action.get("wrist_pitch.pos", 0)
                modified_action = self._modifiers.apply(action)
                modified_pitch = modified_action.get("wrist_pitch.pos", 0)

                # Debug: show modifier effect during animation playback
                if not hasattr(self, '_anim_debug_counter'):
                    self._anim_debug_counter = 0
                self._anim_debug_counter += 1
                enabled_mods = {k: v for k, v in self._modifiers.list_modifiers().items() if v}
                if self._anim_debug_counter % 30 == 0 and enabled_mods:
                    diff = modified_pitch - original_pitch
                    print(f"\033[96m🎵 ANIM PLAYBACK: recording={self._current_recording}, frame={self._current_frame_index}, "
                          f"mods={list(enabled_mods.keys())}, wrist_pitch_diff={diff:.2f}°\033[0m")

                self.robot.send_action(modified_action)
                self._current_state = action.copy()  # Store unmodified for smooth transitions
                self._current_frame_index += 1
            else:
                # Recording finished
                if self._current_recording != self.idle_recording:
                    # Check if we're in dance mode - if so, play next dance animation
                    if self._dance_mode:
                        energy = self._get_current_energy()
                        if energy >= self._dance_threshold:
                            # Clear current recording and play next dance
                            self._current_recording = None
                            self._current_actions = []
                            self._current_frame_index = 0
                            self._play_dance_animation(energy)
                            return
                        else:
                            print(f"💃 ANIMATION SERVICE: Energy dropped to {energy:.2f}, returning to idle with modifier")
                    # Interpolate back to idle
                    idle_actions = self._load_recording(self.idle_recording)
                    if idle_actions is not None and len(idle_actions) > 0:
                        self._current_recording = self.idle_recording
                        self._current_actions = idle_actions
                        self._current_frame_index = 0
                        # Set up interpolation back to idle
                        if self._current_state is not None:
                            self._interpolation_frames = int(self.duration * self.fps)
                            self._interpolation_target = idle_actions[0]
                else:
                    # Loop idle recording (or dance mode without high energy)
                    if self._dance_mode:
                        # In dance mode but at idle - check if energy increased
                        energy = self._get_current_energy()
                        if energy >= self._dance_threshold:
                            self._play_dance_animation(energy)
                            return
                    # Otherwise just loop idle
                    self._current_frame_index = 0

        except Exception as e:
            print(f"Error in playback: {e}")
            # Reset to safe state
            self._current_recording = None
            self._current_actions = []
            self._current_frame_index = 0
        finally:
            self._bus_lock.release()
    
    def get_available_recordings(self) -> List[str]:
        """Get list of recording names available (from both user and builtin directories)"""
        # Use user_data helper to get all recordings from both locations
        all_recordings = list_all_recordings()
        return sorted([r['name'] for r in all_recordings])
    
    def apply_preset(self, preset_name: str = None) -> bool:
        """Apply a motor preset at runtime."""
        if self.robot:
            with self._bus_lock:
                return self.robot.apply_preset(preset_name)
        return False

    def get_available_presets(self) -> List[str]:
        """Get list of available motor presets."""
        if self.robot:
            return self.robot.get_available_presets()
        return []

    def enable_pushable_mode(self) -> bool:
        """
        Enable pushable mode - pauses animations and makes lamp compliant.
        User can physically move the lamp and it will hold position.
        """
        if self.robot:
            with self._bus_lock:
                success = self.robot.enable_pushable_mode()
                if success:
                    self._pushable_mode = True
                    # Clear current animation
                    self._current_recording = None
                    self._current_actions = []
                    self._current_frame_index = 0
                    print("Pushable mode enabled - animations paused")
                return success
        return False

    def disable_pushable_mode(self, return_to_idle: bool = None) -> bool:
        """
        Disable pushable mode - resumes normal operation and animations.

        Args:
            return_to_idle: If True, triggers return to idle animation.
        """
        if self.robot:
            with self._bus_lock:
                success = self.robot.disable_pushable_mode(return_to_idle)
                if success:
                    self._pushable_mode = False
                    print("Pushable mode disabled - animations resumed")
                    # Trigger return to idle if configured
                    if return_to_idle:
                        self.dispatch("play", self.idle_recording)
                return success
        return False

    def is_pushable_mode(self) -> bool:
        """Check if pushable mode is currently enabled."""
        return self._pushable_mode

    def is_face_tracking_mode(self) -> bool:
        """Check if face tracking mode is currently enabled."""
        return self._face_tracking_mode

    def _process_face_tracking(self):
        """Process face tracking with smooth interpolation - called from event loop"""
        if not self.robot or not self._face_tracking_mode:
            return

        # Don't interfere with animations or manual control
        if self._current_recording or self.manual_control_override or self._pushable_mode:
            return

        # Get target positions
        with self._face_tracking_lock:
            target_yaw = self._face_target_yaw
            target_pitch = self._face_target_pitch

        # Smooth interpolation (lerp toward target)
        speed = self._face_tracking_speed
        self._face_current_yaw += (target_yaw - self._face_current_yaw) * speed
        self._face_current_pitch += (target_pitch - self._face_current_pitch) * speed

        # Check if we've moved enough to bother sending a command
        # (avoid spamming tiny adjustments)
        yaw_diff = abs(target_yaw - self._face_current_yaw)
        pitch_diff = abs(target_pitch - self._face_current_pitch)
        if yaw_diff < 0.1 and pitch_diff < 0.1:
            return

        # Try to acquire bus lock (non-blocking)
        if not self._bus_lock.acquire(blocking=False):
            return

        try:
            # Send smoothed position
            action = {
                'base_yaw.pos': self._face_current_yaw,
                'base_pitch.pos': self._face_current_pitch
            }
            self.robot.send_action(action)

        except Exception as e:
            print(f"Face tracking error: {e}")
        finally:
            self._bus_lock.release()

    def _load_recording(self, recording_name: str) -> Optional[List[Dict[str, float]]]:
        """Load a recording from cache or file (checks user dir first, then builtin)"""
        # Check cache first
        if recording_name in self._recording_cache:
            return self._recording_cache[recording_name]

        # Use user_data helper to find recording (prefers user dir)
        csv_path = get_recording_path(recording_name)

        if csv_path is None:
            print(f"Recording not found: {recording_name}")
            return None

        try:
            with open(csv_path, 'r') as csvfile:
                csv_reader = csv.DictReader(csvfile)
                actions = []
                for row in csv_reader:
                    # Extract action data (exclude timestamp column)
                    action = {key: float(value) for key, value in row.items() if key != 'timestamp'}
                    actions.append(action)

            # Cache the recording
            self._recording_cache[recording_name] = actions
            return actions
            
        except Exception as e:
            print(f"Error loading recording {recording_name}: {e}")
            return None

    def hand_control_callback(self, hand_data):
        """
        MediaPipe hand tracking callback function.
        Controls Robot to follow hand movement when "pinching" gesture is detected.

        Args:
            hand_data: MediaPipeHandData object
        """
        # Reference external animation_service instance
        # In actual use, you may need to make it a class member method, or use closure/global variable

        # 1. Basic check: Is hand detected
        if not hand_data.detected:
            return

        # 2. Core logic: Control motors only in "pinching" state
        if hand_data.is_pinching:
            # Get normalized coordinates (-1.0 ~ 1.0)
            x, y = hand_data.position

            # 3. Calculate target angles
            target_yaw, target_pitch = self.calculate_hand_target_angles(x, y)

            # 4. Construct command packet
            # Note: Assuming control of base (base_yaw) and head (base_pitch/head_pitch)
            # Specific joint names need to refer to your robots_config or calibration
            action = {
                'base_yaw.pos': target_yaw,
                'base_pitch.pos': target_pitch  # Or 'head_pitch.pos', depending on your config
            }

            # 5. Send command
            # Check if robot is connected to avoid errors
            if self.robot:
                try:
                    # Try to acquire lock non-blocking, prevent freezing in this high-frequency callback
                    if self._bus_lock.acquire(blocking=False):
                        self.robot.send_action(action)
                        self._bus_lock.release()

                        # Optional: Print debug info
                        # print(f"👆 Pinching! Moving to Yaw: {target_yaw:.1f}, Pitch: {target_pitch:.1f}")
                except Exception as e:
                    print(f"Error sending hand action: {e}")

        else:
            # Optional: Do nothing when not pinching, or let it slowly return to origin
            pass

    def calculate_hand_target_angles(self, x: float, y: float) -> tuple[float, float]:
        """
        Calculate target motor angles based on hand position.

        Args:
            x: Hand horizontal position (-1.0 Left to 1.0 Right)
            y: Hand vertical position (-1.0 Up to 1.0 Down)

        Returns:
            (target_yaw, target_pitch): Target yaw and pitch angles
        """
        # Define maximum motor movement range (degrees)
        # You can adjust these values according to actual needs
        MAX_YAW_ANGLE = 60.0    # Max 60 degrees left/right
        MAX_PITCH_ANGLE = 30.0  # Max 30 degrees up/down

        # Define Deadzone, ignore tiny jitters
        DEADZONE = 0.05

        if abs(x) < DEADZONE: x = 0.0
        if abs(y) < DEADZONE: y = 0.0

        # Calculate Yaw (Left/Right rotation)
        # x > 0 (Right side) -> Yaw positive (Turn right)
        target_yaw = x * MAX_YAW_ANGLE

        # Calculate Pitch (Up/Down pitch)
        # MediaPipe y: -1.0 (Top) to 1.0 (Bottom)
        # Servo usually: Negative value tilts up, positive value bows down
        # So map directly
        target_pitch = y * MAX_PITCH_ANGLE

        # Clamp angles within safe range
        target_yaw = max(-MAX_YAW_ANGLE, min(MAX_YAW_ANGLE, target_yaw))
        target_pitch = max(-MAX_PITCH_ANGLE, min(MAX_PITCH_ANGLE, target_pitch))

        return target_yaw, target_pitch
    