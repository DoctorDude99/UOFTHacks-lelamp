"""
Audio Router Service for LeLamp.

Captures audio from the real microphone, processes it (gating, AEC),
and writes to the ALSA loopback device for LiveKit to consume.

Architecture:
    Real Mic (lelamp_capture_raw) → AudioRouter → Loopback (loopback_sink) → LiveKit

This allows us to:
- Gate audio during AI playback (prevent echo triggering server VAD)
- Apply local VAD to only send speech
- Monitor audio levels for UI
"""

import logging
import threading
import time
import subprocess
from collections import deque
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .audio_service import AudioService

logger = logging.getLogger(__name__)


class AudioRouter:
    """
    Routes and processes audio from real mic to loopback device.

    The loopback device is what LiveKit captures from, so we can
    control what audio reaches the AI by gating/processing here.
    """

    SAMPLE_RATE = 24000
    CHANNELS = 1
    BLOCK_SIZE = 1024  # ~42ms at 24kHz
    BYTES_PER_SAMPLE = 2  # 16-bit

    def __init__(
        self,
        audio_service: Optional["AudioService"] = None,
        input_device: str = "lelamp_capture_raw",
        output_device: str = "loopback_sink",
        gate_during_playback: bool = True,
        gate_release_delay: float = 0.3,
        pass_through_threshold: float = 0.02,
    ):
        """
        Initialize the audio router.

        Args:
            audio_service: Reference to AudioService for playback state
            input_device: ALSA device to capture from (raw mic)
            output_device: ALSA device to write to (loopback)
            gate_during_playback: If True, mute mic during AI playback
            gate_release_delay: Seconds to wait after playback before unmuting
            pass_through_threshold: RMS below this is considered silence (zero it)
        """
        self._audio_service = audio_service
        self._input_device = input_device
        self._output_device = output_device
        self._gate_during_playback = gate_during_playback
        self._gate_release_delay = gate_release_delay
        self._pass_through_threshold = pass_through_threshold

        # State
        self._running = False
        self._router_thread: Optional[threading.Thread] = None
        self._capture_process: Optional[subprocess.Popen] = None
        self._playback_process: Optional[subprocess.Popen] = None

        # Gating state
        self._gate_closed = False
        self._last_playback_time: Optional[float] = None

        # Monitoring
        self._current_rms: float = 0.0
        self._samples_processed: int = 0
        self._samples_gated: int = 0

        logger.info(f"AudioRouter initialized: {input_device} → {output_device}")

    def start(self):
        """Start the audio routing pipeline."""
        if self._running:
            return

        self._running = True
        self._router_thread = threading.Thread(target=self._router_worker, daemon=True)
        self._router_thread.start()
        logger.info("AudioRouter started")

    def stop(self):
        """Stop the audio routing pipeline."""
        self._running = False

        # Terminate processes
        for proc in [self._capture_process, self._playback_process]:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

        self._capture_process = None
        self._playback_process = None

        if self._router_thread:
            self._router_thread.join(timeout=2)
            self._router_thread = None

        logger.info("AudioRouter stopped")

    def _router_worker(self):
        """Main routing worker - captures, processes, and forwards audio."""
        bytes_per_block = self.BLOCK_SIZE * self.BYTES_PER_SAMPLE * self.CHANNELS

        while self._running:
            try:
                # Start capture process (arecord from raw mic)
                capture_cmd = [
                    'arecord',
                    '-D', self._input_device,
                    '-f', 'S16_LE',
                    '-r', str(self.SAMPLE_RATE),
                    '-c', str(self.CHANNELS),
                    '-t', 'raw',
                    '--buffer-size', '4096',
                    '-'
                ]

                # Start playback process (aplay to loopback)
                playback_cmd = [
                    'aplay',
                    '-D', self._output_device,
                    '-f', 'S16_LE',
                    '-r', str(self.SAMPLE_RATE),
                    '-c', str(self.CHANNELS),
                    '-t', 'raw',
                    '--buffer-size', '4096',
                    '-'
                ]

                self._capture_process = subprocess.Popen(
                    capture_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=bytes_per_block
                )

                self._playback_process = subprocess.Popen(
                    playback_cmd,
                    stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=bytes_per_block
                )

                logger.info(f"Audio routing active: {self._input_device} → processing → {self._output_device}")

                # Main routing loop
                while self._running:
                    # Check if processes are still alive
                    if self._capture_process.poll() is not None:
                        stderr = self._capture_process.stderr.read().decode() if self._capture_process.stderr else ""
                        logger.warning(f"Capture process exited (code={self._capture_process.returncode}): {stderr[:200]}")
                        break
                    if self._playback_process.poll() is not None:
                        stderr = self._playback_process.stderr.read().decode() if self._playback_process.stderr else ""
                        logger.warning(f"Playback process exited (code={self._playback_process.returncode}): {stderr[:200]}")
                        break

                    # Read audio from capture
                    raw_data = self._capture_process.stdout.read(bytes_per_block)
                    if not raw_data or len(raw_data) < bytes_per_block:
                        time.sleep(0.01)
                        continue

                    # Convert to numpy for processing
                    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
                    samples = samples / 32768.0  # Normalize to -1 to 1

                    # Process audio
                    processed = self._process_audio(samples)

                    # Convert back to bytes
                    output_samples = (processed * 32768.0).astype(np.int16)
                    output_data = output_samples.tobytes()

                    # Write to loopback
                    try:
                        self._playback_process.stdin.write(output_data)
                        self._playback_process.stdin.flush()
                    except BrokenPipeError:
                        logger.warning("Playback pipe broken, restarting...")
                        break

            except Exception as e:
                logger.error(f"Router error: {e}")
                time.sleep(1.0)
            finally:
                # Clean up processes for restart
                for proc in [self._capture_process, self._playback_process]:
                    if proc:
                        proc.terminate()
                        try:
                            proc.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                self._capture_process = None
                self._playback_process = None

    def _process_audio(self, samples: np.ndarray) -> np.ndarray:
        """
        Process audio samples - apply gating and monitoring.

        Args:
            samples: Input audio samples (float32, -1 to 1)

        Returns:
            Processed audio samples (may be zeroed if gated)
        """
        # Calculate RMS
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self._current_rms = rms
        self._samples_processed += len(samples)

        # Update gate state
        self._update_gate_state()

        # If gate is closed, output silence
        if self._gate_closed:
            self._samples_gated += len(samples)
            return np.zeros_like(samples)

        # If below pass-through threshold, output silence (reduce noise)
        if rms < self._pass_through_threshold:
            return np.zeros_like(samples)

        # Pass through audio
        return samples

    def _update_gate_state(self):
        """Update the audio gate state based on playback."""
        if not self._gate_during_playback:
            self._gate_closed = False
            return

        now = time.time()

        # Check if audio is playing
        is_playing = False
        if self._audio_service:
            is_playing = self._audio_service.is_playing_audio()
            if is_playing:
                self._last_playback_time = now

        if is_playing:
            # Close gate during playback
            if not self._gate_closed:
                self._gate_closed = True
                logger.debug("Audio gate CLOSED (playback active)")
        else:
            # Open gate after delay
            if self._gate_closed and self._last_playback_time:
                time_since_playback = now - self._last_playback_time
                if time_since_playback > self._gate_release_delay:
                    self._gate_closed = False
                    logger.debug(f"Audio gate OPENED (waited {time_since_playback:.2f}s)")

    # =========================================================================
    # Public API
    # =========================================================================

    def is_gate_closed(self) -> bool:
        """Check if audio gate is currently closed."""
        return self._gate_closed

    def get_current_rms(self) -> float:
        """Get current input RMS level."""
        return self._current_rms

    def set_gate_release_delay(self, seconds: float):
        """Set gate release delay."""
        self._gate_release_delay = max(0.0, seconds)

    def set_gate_enabled(self, enabled: bool):
        """Enable/disable gating during playback."""
        self._gate_during_playback = enabled
        if not enabled:
            self._gate_closed = False

    def get_stats(self) -> dict:
        """Get routing statistics."""
        return {
            "running": self._running,
            "gate_closed": self._gate_closed,
            "current_rms": self._current_rms,
            "samples_processed": self._samples_processed,
            "samples_gated": self._samples_gated,
            "gate_ratio": self._samples_gated / max(1, self._samples_processed),
            "input_device": self._input_device,
            "output_device": self._output_device,
        }
