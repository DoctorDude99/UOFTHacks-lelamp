import os
import logging
import threading
import queue
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess
import numpy as np


class AudioService:
    """
    Unified audio service for LeLamp.

    Features:
    - Sound effect playback (via aplay/mpg123 to lelamp_playback dmix)
    - Real-time microphone level monitoring (via lelamp_capture dsnoop)
    - Auto-discovery of audio files in assets/AudioFX/
    - Non-blocking playback with queueing
    - Agent tools for AI to play appropriate sounds
    """

    # Audio monitoring settings
    SAMPLE_RATE = 24000  # Standardized to match OpenAI Realtime API
    BLOCK_SIZE = 1024
    NUM_BARS = 16  # Frequency bands for visualization

    def __init__(self, assets_dir: str = "assets/AudioFX", silence_threshold: float = 0.01, volume: int = 50):
        """
        Initialize the audio service.

        Args:
            assets_dir: Root directory containing audio files
            silence_threshold: RMS threshold for silence detection (default 0.01)
            volume: Initial system volume 0-100 (default 50)
        """
        self.assets_dir = assets_dir
        self.logger = logging.getLogger(__name__)
        self._configured_volume = volume

        # Audio catalog
        self.sounds: Dict[str, Dict[str, str]] = {}

        # Playback queue
        self.play_queue = queue.Queue()
        self.playback_thread = None
        self._running = False

        # Audio level monitoring
        self._monitor_thread = None
        self._monitor_running = False
        self._audio_level: float = 0.0  # Boosted for visualization (0-1)
        self._audio_bars: List[float] = [0.0] * self.NUM_BARS
        self._level_lock = threading.Lock()

        # Raw RMS tracking for silence detection / VAD tuning
        self._raw_rms: float = 0.0  # Actual RMS value (typically 0.0-0.1)
        self._rms_history: List[float] = []  # Rolling history for averaging
        self._rms_history_size = 10  # Number of samples to average
        self._silence_threshold: float = silence_threshold

        # Reference signal buffer for AEC (Acoustic Echo Cancellation)
        # Stores recent playback audio that microphone_service can use for echo removal
        self._ref_buffer_duration_ms = 500  # 500ms of audio reference
        self._ref_buffer_samples = int(self.SAMPLE_RATE * self._ref_buffer_duration_ms / 1000)
        self._reference_buffer: deque = deque(maxlen=self._ref_buffer_samples)
        self._ref_buffer_lock = threading.Lock()
        self._is_playing = False  # Flag to indicate active playback
        self._playback_rms: float = 0.0  # RMS of recent playback for ducking

        # Discover all audio files
        self._discover_sounds()

        self.logger.info(f"AudioService initialized with {len(self.sounds)} sounds")

    def _discover_sounds(self):
        """Scan assets directory and catalog all audio files"""
        if not os.path.exists(self.assets_dir):
            self.logger.warning(f"Assets directory not found: {self.assets_dir}")
            return

        # Walk through all subdirectories
        for root, dirs, files in os.walk(self.assets_dir):
            for file in files:
                # Check if it's an audio file
                if file.lower().endswith(('.mp3', '.wav', '.ogg', '.flac')):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, self.assets_dir)

                    # Categorize by directory structure
                    category = os.path.dirname(relative_path) or "Uncategorized"

                    # Create a friendly name (remove extension and path)
                    name = os.path.splitext(file)[0]

                    # Store in catalog
                    sound_id = f"{category}/{name}".replace(" ", "_").lower()

                    self.sounds[sound_id] = {
                        "name": name,
                        "category": category,
                        "path": full_path,
                        "format": os.path.splitext(file)[1][1:],  # .mp3 -> mp3
                        "filename": file
                    }

        self.logger.info(f"Discovered {len(self.sounds)} audio files")

        # Log categories
        categories = set(sound['category'] for sound in self.sounds.values())
        self.logger.info(f"Categories: {sorted(categories)}")

    def set_system_volume(self, volume_percent: int):
        """
        Set system volume using amixer.

        Args:
            volume_percent: Volume level 0-100
        """
        # Try common mixer control names in order of preference
        mixer_controls = ["Speaker", "Master", "PCM", "Headphone"]

        try:
            # Clamp volume to valid range
            volume = max(0, min(100, volume_percent))

            for control in mixer_controls:
                result = subprocess.run(
                    ["amixer", "sset", control, f"{volume}%"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self.logger.info(f"System volume set to {volume}% (control: {control})")
                    return

            # If none worked, log warning
            self.logger.warning(f"No mixer control found. Tried: {mixer_controls}")
        except FileNotFoundError:
            self.logger.warning("amixer not found - cannot set system volume")
        except Exception as e:
            self.logger.error(f"Error setting system volume: {e}")

    def start(self):
        """Start the audio playback service"""
        if self._running:
            return

        # Set volume to 0 first, then ramp up to prevent speaker pop
        self.set_system_volume(0)
        time.sleep(0.1)  # Brief delay to let audio settle

        self._running = True
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()

        # Now set to configured volume
        self.set_system_volume(self._configured_volume)
        self.logger.info(f"AudioService started (volume: {self._configured_volume}%)")

    def stop(self):
        """Stop the audio playback service"""
        # Set volume to 0% on shutdown to prevent audio bleed
        self.set_system_volume(0)

        self._running = False
        if self.playback_thread:
            self.playback_thread.join(timeout=2)
        self.logger.info("AudioService stopped (volume muted)")

    def clear_queue(self):
        """Clear all pending sounds from the playback queue"""
        # Empty the queue
        while not self.play_queue.empty():
            try:
                self.play_queue.get_nowait()
                self.play_queue.task_done()
            except queue.Empty:
                break
        self.logger.info("Audio playback queue cleared")

    def _playback_worker(self):
        """Background worker that processes the playback queue"""
        while self._running:
            try:
                # Get next sound to play (block with timeout)
                sound_path, volume = self.play_queue.get(timeout=0.5)

                if sound_path:
                    self._play_sound_blocking(sound_path, volume)

                self.play_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error in playback worker: {e}")

    def _play_sound_blocking(self, file_path: str, volume: int = 100):
        """
        Play a sound file using subprocess (blocking).
        Uses lelamp_playback abstract device for hardware independence.

        Args:
            file_path: Path to audio file
            volume: Volume percentage (0-100)
        """
        print("sound path:", file_path)
        import sounddevice as sd
        import soundfile as sf
        # import librosa
        # target_fs = sd.query_devices(kind='output')['default_samplerate']
        try:
            # data, fs = librosa.load(file_path, sr=target_fs)
            data, fs = sf.read(file_path, always_2d=True)
            sd.play(data, fs, latency="high")
            sd.wait()
            self.logger.debug(f"Played sound: {file_path}")

        except FileNotFoundError as e:
            self.logger.error(f"Audio player not found: {e}")
        except Exception as e:
            self.logger.error(f"Error playing sound {file_path}: {e}")

    def play(self, sound_id: str, volume: int = 100, blocking: bool = False) -> bool:
        """
        Play a sound by its ID.

        Args:
            sound_id: Sound identifier (e.g., "effects/scifi-success")
            volume: Volume percentage (0-100)
            blocking: If True, wait for sound to finish

        Returns:
            True if sound was queued/played successfully
        """
        # Normalize sound_id
        sound_id = sound_id.lower().replace(" ", "_")

        # Find the sound
        if sound_id not in self.sounds:
            # Try fuzzy matching
            for sid, sound in self.sounds.items():
                if sound_id in sid or sound_id in sound['name'].lower():
                    sound_id = sid
                    break
            else:
                self.logger.warning(f"Sound not found: {sound_id}")
                return False

        sound_path = self.sounds[sound_id]['path']

        if blocking:
            self._play_sound_blocking(sound_path, volume)
        else:
            self.play_queue.put((sound_path, volume))

        return True

    def play_by_path(self, file_path: str, volume: int = 100, blocking: bool = False) -> bool:
        """
        Play a sound by its file path.

        Args:
            file_path: Full or relative path to audio file
            volume: Volume percentage (0-100)
            blocking: If True, wait for sound to finish

        Returns:
            True if sound was queued/played successfully
        """
        if not os.path.exists(file_path):
            self.logger.warning(f"Sound file not found: {file_path}")
            return False

        if blocking:
            self._play_sound_blocking(file_path, volume)
        else:
            self.play_queue.put((file_path, volume))

        return True

    def get_all_sounds(self) -> Dict[str, Dict[str, str]]:
        """Get catalog of all available sounds"""
        return self.sounds.copy()

    def get_sounds_by_category(self, category: str) -> List[str]:
        """
        Get all sound IDs in a category.

        Args:
            category: Category name (e.g., "Effects", "Emotions")

        Returns:
            List of sound IDs in that category
        """
        return [
            sid for sid, sound in self.sounds.items()
            if sound['category'].lower() == category.lower()
        ]

    def get_categories(self) -> List[str]:
        """Get list of all sound categories"""
        return sorted(set(sound['category'] for sound in self.sounds.values()))

    def search_sounds(self, query: str) -> List[str]:
        """
        Search for sounds by name or category.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching sound IDs
        """
        query = query.lower()
        matches = []

        for sid, sound in self.sounds.items():
            if (query in sid.lower() or
                query in sound['name'].lower() or
                query in sound['category'].lower()):
                matches.append(sid)

        return matches

    def get_sound_info(self, sound_id: str) -> Optional[Dict[str, str]]:
        """Get detailed info about a specific sound"""
        sound_id = sound_id.lower().replace(" ", "_")
        return self.sounds.get(sound_id)

    # =========================================================================
    # Audio Level Monitoring (for dashboard visualization)
    # =========================================================================

    def start_monitoring(self):
        """Start the audio level monitoring thread."""
        if self._monitor_running:
            return

        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._audio_monitor_worker, daemon=True)
        self._monitor_thread.start()
        self.logger.info("AudioService monitoring thread started")

    def stop_monitoring(self):
        """Stop the audio level monitoring thread."""
        self._monitor_running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None
        self.logger.info("AudioService monitoring stopped")

    def _audio_monitor_worker(self):
        """
        Background worker that captures audio from lelamp_capture dsnoop
        and calculates RMS level and frequency bars for visualization.
        """
        return
        BYTES_PER_SAMPLE = 2  # 16-bit audio
        bytes_to_read = self.BLOCK_SIZE * BYTES_PER_SAMPLE

        process = None
        retry_count = 0
        max_retries = 5

        while self._monitor_running and retry_count < max_retries:
            try:
                # Use arecord with lelamp_capture (dsnoop device) - allows sharing with VAD
                cmd = [
                    'arecord',
                    '-D', 'lelamp_capture',
                    '-f', 'S16_LE',
                    '-r', str(self.SAMPLE_RATE),
                    '-c', '1',
                    '-t', 'raw',
                    '--buffer-size', '4096',
                    '-'
                ]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=bytes_to_read
                )

                self.logger.info("Audio monitor started with lelamp_capture (dsnoop)")
                retry_count = 0  # Reset on successful start

                while self._monitor_running:
                    # Check if process is still running
                    if process.poll() is not None:
                        stderr = process.stderr.read().decode() if process.stderr else ""
                        self.logger.warning(f"arecord process exited: {stderr}")
                        break

                    # Read audio data
                    raw_data = process.stdout.read(bytes_to_read)

                    if not raw_data:
                        time.sleep(0.01)
                        continue

                    if len(raw_data) < bytes_to_read:
                        continue

                    # Convert bytes to numpy array
                    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
                    samples = samples / 32768.0  # Normalize to -1 to 1

                    # Calculate RMS level
                    rms = np.sqrt(np.mean(samples ** 2))

                    # Boost for visualization (mic input is quiet)
                    level = min(1.0, rms * 25)  # Increased gain for better visibility

                    # Simple FFT for frequency bands
                    fft = np.abs(np.fft.rfft(samples))
                    bins_per_bar = max(1, len(fft) // self.NUM_BARS)
                    bars = []
                    for i in range(self.NUM_BARS):
                        start = i * bins_per_bar
                        end = min(start + bins_per_bar, len(fft))
                        if start < len(fft):
                            bar_value = float(np.mean(fft[start:end]))
                            # Normalize and boost lower frequencies (increased multiplier)
                            bar_value = min(1.0, bar_value * (0.3 + 0.7 * (1 - i / self.NUM_BARS)) * 0.015)
                            bars.append(round(bar_value, 3))
                        else:
                            bars.append(0.0)

                    # Update shared state with lock
                    with self._level_lock:
                        self._audio_level = round(level, 3)
                        self._audio_bars = bars

                        # Track raw RMS for silence detection
                        self._raw_rms = round(rms, 6)
                        self._rms_history.append(rms)
                        if len(self._rms_history) > self._rms_history_size:
                            self._rms_history.pop(0)

            except FileNotFoundError:
                self.logger.error("arecord not found - audio monitoring unavailable")
                break
            except Exception as e:
                self.logger.error(f"Audio monitor error: {e}")
                retry_count += 1
                time.sleep(1.0)  # Wait before retry
            finally:
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    process = None

        if retry_count >= max_retries:
            self.logger.error("Audio monitor gave up after max retries")

        self._monitor_running = False

    def get_audio_levels(self) -> Tuple[float, List[float]]:
        """
        Get current audio level and frequency bars.

        Returns:
            Tuple of (level: 0.0-1.0, bars: list of 16 floats 0.0-1.0)
        """
        with self._level_lock:
            return self._audio_level, self._audio_bars.copy()

    def is_monitoring(self) -> bool:
        """Check if audio monitoring is active."""
        return self._monitor_running

    # =========================================================================
    # Raw RMS / Silence Detection (for VAD tuning)
    # =========================================================================

    def get_raw_rms(self) -> float:
        """
        Get the current raw RMS value (not boosted).

        Returns:
            Raw RMS value, typically 0.0-0.1 for normal speech
        """
        with self._level_lock:
            return self._raw_rms

    def get_average_rms(self) -> float:
        """
        Get the average RMS over recent samples.

        Returns:
            Average RMS value over the history window
        """
        with self._level_lock:
            if not self._rms_history:
                return 0.0
            return sum(self._rms_history) / len(self._rms_history)

    def is_silent(self, threshold: Optional[float] = None) -> bool:
        """
        Check if the current audio level indicates silence.

        Args:
            threshold: Custom silence threshold (uses default if None)

        Returns:
            True if current RMS is below threshold
        """
        thresh = threshold if threshold is not None else self._silence_threshold
        return self.get_raw_rms() < thresh

    def set_silence_threshold(self, threshold: float):
        """
        Set the silence detection threshold.

        Args:
            threshold: RMS value below which audio is considered silent
        """
        self._silence_threshold = threshold
        self.logger.info(f"Silence threshold set to: {threshold}")

    def get_silence_threshold(self) -> float:
        """Get the current silence detection threshold."""
        return self._silence_threshold

    def get_rms_stats(self) -> dict:
        """
        Get comprehensive RMS statistics for tuning.

        Returns:
            Dict with current, average, min, max RMS and silence status
        """
        with self._level_lock:
            history = self._rms_history.copy()

        if not history:
            return {
                "current_rms": 0.0,
                "average_rms": 0.0,
                "min_rms": 0.0,
                "max_rms": 0.0,
                "is_silent": True,
                "silence_threshold": self._silence_threshold,
            }

        return {
            "current_rms": self._raw_rms,
            "average_rms": sum(history) / len(history),
            "min_rms": min(history),
            "max_rms": max(history),
            "is_silent": self._raw_rms < self._silence_threshold,
            "silence_threshold": self._silence_threshold,
        }

    # =========================================================================
    # Reference Signal Buffer (for AEC in MicrophoneService)
    # =========================================================================

    def write_reference_audio(self, samples: np.ndarray):
        """
        Write playback audio samples to the reference buffer.
        Called by TTS/playback components to provide echo reference.

        Args:
            samples: Numpy array of float32 samples (-1.0 to 1.0)
        """
        with self._ref_buffer_lock:
            # Add samples to ring buffer
            for sample in samples:
                self._reference_buffer.append(sample)

            # Calculate RMS of this chunk for playback detection
            if len(samples) > 0:
                self._playback_rms = float(np.sqrt(np.mean(samples ** 2)))
                self._is_playing = self._playback_rms > 0.01

    def get_reference_audio(self, num_samples: int) -> np.ndarray:
        """
        Get recent reference audio for AEC processing.

        Args:
            num_samples: Number of samples to retrieve

        Returns:
            Numpy array of recent playback samples
        """
        with self._ref_buffer_lock:
            # Get the most recent samples
            available = len(self._reference_buffer)
            if available == 0:
                return np.zeros(num_samples, dtype=np.float32)

            # Get samples from buffer
            samples_to_get = min(num_samples, available)
            samples = list(self._reference_buffer)[-samples_to_get:]

            # Pad with zeros if we don't have enough
            if len(samples) < num_samples:
                samples = [0.0] * (num_samples - len(samples)) + samples

            return np.array(samples, dtype=np.float32)

    def clear_reference_buffer(self):
        """Clear the reference audio buffer."""
        with self._ref_buffer_lock:
            self._reference_buffer.clear()
            self._is_playing = False
            self._playback_rms = 0.0

    def is_playing_audio(self) -> bool:
        """
        Check if audio is currently being played.

        Returns:
            True if playback is active (reference signal present)
        """
        with self._ref_buffer_lock:
            return self._is_playing

    def get_playback_rms(self) -> float:
        """
        Get the RMS level of current playback audio.

        Returns:
            RMS level of recent playback (0.0 if not playing)
        """
        with self._ref_buffer_lock:
            return self._playback_rms

    def set_playing_state(self, is_playing: bool):
        """
        Manually set the playback state.
        Used by realtime pipelines to indicate TTS playback.

        Args:
            is_playing: True if TTS/audio is playing
        """
        with self._ref_buffer_lock:
            self._is_playing = is_playing
            if not is_playing:
                self._playback_rms = 0.0
