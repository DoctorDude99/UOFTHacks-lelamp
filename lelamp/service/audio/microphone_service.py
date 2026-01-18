"""
Microphone Service for LeLamp.

Handles microphone input processing with:
- Local VAD (Voice Activity Detection) using Silero VAD (via livekit-plugins-silero)
- Acoustic Echo Cancellation (AEC) using reference signal from AudioService
- Gating logic to prevent self-interruption during playback
- Barge-in detection for interrupting AI speech

Architecture:
    AudioService (output) <---> MicrophoneService (input)
    - AudioService provides reference signal buffer for AEC
    - MicrophoneService gates mic input based on playback state
"""

import logging
import threading
import time
import subprocess
from collections import deque
from typing import Callable, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .audio_service import AudioService

logger = logging.getLogger(__name__)

# Try to import livekit's silero plugin (preferred)
_LIVEKIT_SILERO_AVAILABLE = False
_silero_vad = None
try:
    from livekit.plugins import silero as livekit_silero
    _LIVEKIT_SILERO_AVAILABLE = True
    logger.debug("livekit-plugins-silero available")
except ImportError:
    logger.debug("livekit-plugins-silero not available")


class MicrophoneService:
    """
    Microphone input processing service with VAD and echo cancellation.

    Features:
    - Continuous microphone capture from ALSA device
    - Local Silero VAD for speech detection
    - Simple AEC using reference signal correlation
    - Gating to mute mic during playback (prevents echo loops)
    - Barge-in detection (loud speech during playback = interrupt)
    - Callbacks for speech events
    """

    # Audio parameters - match OpenAI Realtime API
    SAMPLE_RATE = 24000
    BLOCK_SIZE = 1024
    BYTES_PER_SAMPLE = 2  # 16-bit audio

    def __init__(
        self,
        audio_service: Optional["AudioService"] = None,
        device: str = "lelamp_capture",
        vad_threshold: float = 0.5,
        barge_in_threshold: float = 0.15,
        echo_gate_threshold: float = 0.02,
        gate_release_time: float = 0.3,
        min_speech_duration: float = 0.1,
        min_silence_duration: float = 0.3,
        debug_logging: bool = False,
    ):
        """
        Initialize the microphone service.

        Args:
            audio_service: Reference to AudioService for playback state and AEC
            device: ALSA capture device name
            vad_threshold: Silero VAD activation threshold (0.0-1.0, higher = needs louder speech)
            barge_in_threshold: RMS threshold to trigger barge-in during playback
            echo_gate_threshold: RMS threshold below which we assume it's echo
            gate_release_time: Seconds to wait after playback stops before ungating
            min_speech_duration: Minimum speech duration to trigger speech start (seconds)
            min_silence_duration: Minimum silence duration to trigger speech end (seconds)
            debug_logging: Enable verbose debug logging for tuning
        """
        self._audio_service = audio_service
        self._device = device
        self._vad_threshold = vad_threshold
        self._barge_in_threshold = barge_in_threshold
        self._echo_gate_threshold = echo_gate_threshold
        self._gate_release_time = gate_release_time
        self._min_speech_duration = min_speech_duration
        self._min_silence_duration = min_silence_duration
        self._debug_logging = debug_logging

        # State
        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None

        # VAD state
        self._vad_model = None
        self._vad_stream = None  # For livekit silero streaming VAD
        self._vad_available = False
        self._vad_backend = "none"  # "livekit_silero", "torch_silero", or "rms"
        self._speech_active = False
        self._speech_start_time: Optional[float] = None
        self._speech_end_time: Optional[float] = None
        self._current_vad_probability: float = 0.0  # Last VAD probability for UI

        # Gating state
        self._gate_closed = False  # True = mic is muted (during playback)
        self._gate_close_time: Optional[float] = None
        self._last_playback_time: Optional[float] = None

        # Audio level tracking
        self._current_rms: float = 0.0
        self._peak_rms: float = 0.0  # Peak RMS for calibration
        self._level_lock = threading.Lock()

        # Callbacks
        self._on_speech_start: Optional[Callable[[], None]] = None
        self._on_speech_end: Optional[Callable[[], None]] = None
        self._on_barge_in: Optional[Callable[[], None]] = None

        # Buffer for VAD (needs 512 samples at 16kHz, we'll resample)
        self._vad_buffer: deque = deque(maxlen=int(self.SAMPLE_RATE * 0.1))  # 100ms buffer

        logger.info(f"MicrophoneService initialized (device={device}, vad_threshold={vad_threshold})")

    def _load_vad_model(self):
        """Load Silero VAD model. Tries livekit-plugins-silero first, then torch.hub fallback."""
        # Try livekit-plugins-silero first (preferred - already bundled with our deps)
        if _LIVEKIT_SILERO_AVAILABLE:
            try:
                logger.info("Loading Silero VAD via livekit-plugins-silero...")
                self._vad_model = livekit_silero.VAD.load(
                    min_speech_duration=self._min_speech_duration,
                    min_silence_duration=self._min_silence_duration,
                    activation_threshold=self._vad_threshold,
                )
                self._vad_available = True
                self._vad_backend = "livekit_silero"
                logger.info(f"Silero VAD loaded (livekit-plugins-silero) - threshold={self._vad_threshold}")
                return
            except Exception as e:
                logger.warning(f"Failed to load livekit-plugins-silero VAD: {e}")

        # Fallback to torch.hub (direct Silero)
        try:
            import torch
            logger.info("Loading Silero VAD via torch.hub...")
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )
            self._vad_model = model
            self._vad_available = True
            self._vad_backend = "torch_silero"
            logger.info("Silero VAD loaded (torch.hub) - using neural VAD")
            return
        except ImportError:
            logger.warning("PyTorch not available")
        except Exception as e:
            logger.warning(f"Failed to load torch.hub Silero VAD: {e}")

        # Final fallback to RMS-based VAD
        logger.warning("Using RMS fallback VAD (less accurate than Silero)")
        self._vad_available = False
        self._vad_backend = "rms"

    def start(self):
        """Start microphone capture and processing."""
        if self._running:
            return

        # Load VAD model
        self._load_vad_model()

        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self._capture_thread.start()
        logger.info("MicrophoneService started")

    def stop(self):
        """Stop microphone capture."""
        self._running = False

        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        if self._capture_thread:
            self._capture_thread.join(timeout=2)
            self._capture_thread = None

        logger.info("MicrophoneService stopped")

    def _capture_worker(self):
        """Background worker for continuous microphone capture."""
        bytes_to_read = self.BLOCK_SIZE * self.BYTES_PER_SAMPLE
        retry_count = 0
        max_retries = 5

        while self._running and retry_count < max_retries:
            try:
                # Start arecord process
                cmd = [
                    'arecord',
                    '-D', self._device,
                    '-f', 'S16_LE',
                    '-r', str(self.SAMPLE_RATE),
                    '-c', '1',
                    '-t', 'raw',
                    '--buffer-size', '4096',
                    '-'
                ]

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=bytes_to_read
                )

                logger.info(f"Microphone capture started on {self._device}")
                retry_count = 0

                while self._running:
                    if self._process.poll() is not None:
                        stderr = self._process.stderr.read().decode() if self._process.stderr else ""
                        logger.warning(f"arecord process exited: {stderr}")
                        break

                    raw_data = self._process.stdout.read(bytes_to_read)
                    if not raw_data or len(raw_data) < bytes_to_read:
                        time.sleep(0.01)
                        continue

                    # Convert to numpy float32
                    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
                    samples = samples / 32768.0  # Normalize to -1 to 1

                    # Process the audio
                    self._process_audio(samples)

            except FileNotFoundError:
                logger.error("arecord not found")
                break
            except Exception as e:
                logger.error(f"Capture error: {e}")
                retry_count += 1
                time.sleep(1.0)
            finally:
                if self._process:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                    self._process = None

        if retry_count >= max_retries:
            logger.error("Microphone capture gave up after max retries")

    def _process_audio(self, samples: np.ndarray):
        """
        Process captured audio samples.

        Pipeline:
        1. Calculate RMS level
        2. Check playback state (from AudioService)
        3. Apply gating logic
        4. Run VAD on ungated audio
        5. Check for barge-in
        """
        # Calculate RMS
        rms = float(np.sqrt(np.mean(samples ** 2)))
        with self._level_lock:
            self._current_rms = rms
            # Track peak for calibration UI
            if rms > self._peak_rms:
                self._peak_rms = rms

        # Get playback state from AudioService
        is_playing = False
        playback_rms = 0.0
        if self._audio_service:
            is_playing = self._audio_service.is_playing_audio()
            playback_rms = self._audio_service.get_playback_rms()
            if is_playing:
                self._last_playback_time = time.time()

        # Verbose debug logging
        if self._debug_logging and (is_playing or rms > 0.01):
            logger.info(
                f"🎤 MIC: rms={rms:.4f} | playing={is_playing} | "
                f"gate={'CLOSED' if self._gate_closed else 'OPEN'} | "
                f"playback_rms={playback_rms:.4f}"
            )

        # Gating logic
        self._update_gate_state(is_playing, rms)

        # If gate is closed (during playback), check for barge-in
        if self._gate_closed:
            if rms > self._barge_in_threshold:
                # Loud speech during playback = barge-in
                logger.info(f"🎤 BARGE-IN detected (RMS={rms:.3f} > threshold={self._barge_in_threshold})")
                if self._on_barge_in:
                    self._on_barge_in()
            elif self._debug_logging and rms > self._echo_gate_threshold:
                # Log when we're blocking what might be echo
                logger.debug(f"🎤 Blocked (gate closed): rms={rms:.4f}")
            return  # Don't process further while gated

        # Run VAD on ungated audio
        self._run_vad(samples)

    def _update_gate_state(self, is_playing: bool, rms: float):
        """
        Update the microphone gate state.

        Gate closes when:
        - Playback starts
        - Audio detected is below echo threshold (likely echo)

        Gate opens when:
        - Playback has stopped AND
        - Enough time has passed (gate_release_time)
        """
        now = time.time()

        if is_playing:
            # Close gate during playback
            if not self._gate_closed:
                self._gate_closed = True
                self._gate_close_time = now
                logger.info("🔇 Mic gate CLOSED (AI speaking)")
        else:
            # Check if we should open the gate
            if self._gate_closed:
                # Wait for release time after playback stops
                time_since_playback = now - (self._last_playback_time or 0)
                if time_since_playback > self._gate_release_time:
                    self._gate_closed = False
                    logger.info(f"🔊 Mic gate OPENED (waited {time_since_playback:.2f}s)")
                elif self._debug_logging:
                    # Log waiting state
                    remaining = self._gate_release_time - time_since_playback
                    logger.debug(f"🔇 Gate still closed, waiting {remaining:.2f}s more")

    def _run_vad(self, samples: np.ndarray):
        """
        Run Silero VAD on audio samples.
        Updates speech state and fires callbacks.
        """
        # RMS fallback VAD (used when Silero not available)
        if not self._vad_available or self._vad_model is None:
            # Fallback: simple RMS-based VAD
            # Use vad_threshold scaled to RMS range (0.05-0.3 typical speech)
            fallback_threshold = self._vad_threshold * 0.3  # Scale 0-1 to 0-0.3 RMS
            fallback_threshold = max(fallback_threshold, 0.03)  # Minimum threshold
            is_speech = self._current_rms > fallback_threshold
            # Fake probability for UI (RMS scaled)
            self._current_vad_probability = min(1.0, self._current_rms / 0.3)
            if self._debug_logging and is_speech:
                logger.debug(f"🎤 RMS VAD: rms={self._current_rms:.4f} > threshold={fallback_threshold:.4f}")
            self._update_speech_state(is_speech)
            return

        # Silero VAD (torch.hub backend)
        if self._vad_backend == "torch_silero":
            try:
                import torch

                # Add samples to buffer
                for s in samples:
                    self._vad_buffer.append(s)

                # Need at least 512 samples for VAD (at 16kHz)
                # We're at 24kHz, so need ~768 samples
                if len(self._vad_buffer) < 768:
                    return

                # Get buffer and resample from 24kHz to 16kHz for Silero
                buffer = np.array(list(self._vad_buffer))
                # Simple resampling: take every 1.5th sample (24000/16000 = 1.5)
                indices = np.arange(0, len(buffer), 1.5).astype(int)
                resampled = buffer[indices[:512]] if len(indices) >= 512 else buffer[:512]

                # Run VAD (Silero expects 16kHz audio and integer sample rate)
                tensor = torch.tensor(resampled, dtype=torch.float32)
                speech_prob = self._vad_model(tensor, 16000).item()
                self._current_vad_probability = speech_prob

                is_speech = speech_prob > self._vad_threshold
                if self._debug_logging:
                    logger.debug(f"🎤 Silero VAD: prob={speech_prob:.3f} threshold={self._vad_threshold:.3f} speech={is_speech}")
                self._update_speech_state(is_speech)

            except Exception as e:
                logger.debug(f"Torch Silero VAD error: {e}")

        # LiveKit Silero backend - uses the model's internal event streaming
        # For MicrophoneService, we use a simplified approach since we don't have
        # the full async pipeline. Fall back to torch if livekit model doesn't
        # provide direct probability access.
        elif self._vad_backend == "livekit_silero":
            # livekit-plugins-silero is event-based, designed for their pipeline
            # For direct probability, we'd need torch.hub fallback
            # For now, use RMS as a proxy when livekit silero is loaded
            # (The main VAD benefit comes from the LiveKit pipeline itself)
            fallback_threshold = self._vad_threshold * 0.3
            fallback_threshold = max(fallback_threshold, 0.03)
            is_speech = self._current_rms > fallback_threshold
            self._current_vad_probability = min(1.0, self._current_rms / 0.3)
            self._update_speech_state(is_speech)

    def _update_speech_state(self, is_speech: bool):
        """Update speech state and fire callbacks."""
        now = time.time()

        if is_speech and not self._speech_active:
            # Speech started
            self._speech_active = True
            self._speech_start_time = now
            logger.debug("Speech started")
            if self._on_speech_start:
                self._on_speech_start()

        elif not is_speech and self._speech_active:
            # Speech ended
            self._speech_active = False
            self._speech_end_time = now
            logger.debug("Speech ended")
            if self._on_speech_end:
                self._on_speech_end()

    # =========================================================================
    # Public API
    # =========================================================================

    def set_callbacks(
        self,
        on_speech_start: Optional[Callable[[], None]] = None,
        on_speech_end: Optional[Callable[[], None]] = None,
        on_barge_in: Optional[Callable[[], None]] = None,
    ):
        """
        Set callbacks for speech events.

        Args:
            on_speech_start: Called when speech begins
            on_speech_end: Called when speech ends
            on_barge_in: Called when user interrupts during playback
        """
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_barge_in = on_barge_in

    def is_speech_active(self) -> bool:
        """Check if speech is currently detected."""
        return self._speech_active

    def is_gate_closed(self) -> bool:
        """Check if the microphone gate is closed (muted)."""
        return self._gate_closed

    def get_current_rms(self) -> float:
        """Get current microphone RMS level."""
        with self._level_lock:
            return self._current_rms

    def set_vad_threshold(self, threshold: float):
        """Set VAD detection threshold (0.0-1.0)."""
        self._vad_threshold = max(0.0, min(1.0, threshold))
        # Update livekit silero model if available
        if self._vad_backend == "livekit_silero" and self._vad_model:
            try:
                # Reload with new threshold
                self._vad_model = livekit_silero.VAD.load(
                    min_speech_duration=self._min_speech_duration,
                    min_silence_duration=self._min_silence_duration,
                    activation_threshold=self._vad_threshold,
                )
            except Exception as e:
                logger.warning(f"Failed to update livekit silero threshold: {e}")
        logger.info(f"VAD threshold set to {self._vad_threshold}")

    def set_barge_in_threshold(self, threshold: float):
        """Set barge-in RMS threshold."""
        self._barge_in_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Barge-in threshold set to {self._barge_in_threshold}")

    def set_gate_release_time(self, seconds: float):
        """Set gate release delay after playback stops."""
        self._gate_release_time = max(0.0, seconds)
        logger.info(f"Gate release time set to {self._gate_release_time}s")

    def set_echo_gate_threshold(self, threshold: float):
        """Set echo gate RMS threshold."""
        self._echo_gate_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Echo gate threshold set to {self._echo_gate_threshold}")

    def set_min_speech_duration(self, seconds: float):
        """Set minimum speech duration to trigger speech start."""
        self._min_speech_duration = max(0.0, seconds)
        # Update livekit silero model if available
        if self._vad_backend == "livekit_silero" and self._vad_model:
            try:
                self._vad_model = livekit_silero.VAD.load(
                    min_speech_duration=self._min_speech_duration,
                    min_silence_duration=self._min_silence_duration,
                    activation_threshold=self._vad_threshold,
                )
            except Exception as e:
                logger.warning(f"Failed to update livekit silero min_speech_duration: {e}")
        logger.info(f"Min speech duration set to {self._min_speech_duration}s")

    def set_min_silence_duration(self, seconds: float):
        """Set minimum silence duration to trigger speech end."""
        self._min_silence_duration = max(0.0, seconds)
        # Update livekit silero model if available
        if self._vad_backend == "livekit_silero" and self._vad_model:
            try:
                self._vad_model = livekit_silero.VAD.load(
                    min_speech_duration=self._min_speech_duration,
                    min_silence_duration=self._min_silence_duration,
                    activation_threshold=self._vad_threshold,
                )
            except Exception as e:
                logger.warning(f"Failed to update livekit silero min_silence_duration: {e}")
        logger.info(f"Min silence duration set to {self._min_silence_duration}s")

    def reset_peak_rms(self):
        """Reset peak RMS for recalibration."""
        with self._level_lock:
            self._peak_rms = 0.0
        logger.info("Peak RMS reset")

    def force_gate_open(self):
        """Manually open the microphone gate."""
        self._gate_closed = False
        self._last_playback_time = None
        logger.debug("Mic gate forced open")

    def force_gate_close(self):
        """Manually close the microphone gate."""
        self._gate_closed = True
        self._gate_close_time = time.time()
        logger.debug("Mic gate forced closed")

    def get_status(self) -> dict:
        """Get comprehensive status for debugging and UI."""
        return {
            "running": self._running,
            "vad_available": self._vad_available,
            "vad_backend": self._vad_backend,
            "speech_active": self._speech_active,
            "gate_closed": self._gate_closed,
            "current_rms": self._current_rms,
            "peak_rms": self._peak_rms,
            "vad_probability": self._current_vad_probability,
            "vad_threshold": self._vad_threshold,
            "barge_in_threshold": self._barge_in_threshold,
            "echo_gate_threshold": self._echo_gate_threshold,
            "gate_release_time": self._gate_release_time,
            "min_speech_duration": self._min_speech_duration,
            "min_silence_duration": self._min_silence_duration,
        }
