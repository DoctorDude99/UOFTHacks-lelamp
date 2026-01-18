"""
Direct ALSA audio I/O for local voice pipeline.

Adapted from ~/Faster-Local-Voice-AI-Whisper/client_alsa.py
"""

import asyncio
import numpy as np
import queue
import threading
import logging
from typing import Optional, Callable

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import soxr
except ImportError:
    soxr = None

logger = logging.getLogger(__name__)


class LocalAudioIO:
    """Direct ALSA audio I/O for local voice pipeline."""

    # Audio settings
    SAMPLE_RATE = 24000  # Standardized to match OpenAI Realtime API
    WHISPER_RATE = 16000  # Whisper expects 16kHz (1.5:1 conversion ratio)
    BLOCK_SIZE = 2048
    CHANNELS_OUT = 2  # Stereo output
    LATENCY = "high"  # More stable on Pi

    def __init__(self):
        if sd is None:
            raise ImportError("sounddevice not installed. Run: pip install sounddevice")
        if soxr is None:
            raise ImportError("soxr not installed. Run: pip install soxr")

        self.input_queue: queue.Queue = queue.Queue()
        self.output_queue: queue.Queue = queue.Queue()
        self.mic_enabled = True
        self._running = False

        # Playback buffer
        self._playback_buffer = np.zeros(0, dtype=np.float32)
        self._playback_lock = threading.Lock()

        # Streams
        self._input_stream: Optional[sd.InputStream] = None
        self._output_stream: Optional[sd.OutputStream] = None

        # Callbacks
        self._on_playback_complete: Optional[Callable] = None

        # Overflow warnings (log once)
        self._input_overflow_warned = False
        self._output_underflow_warned = False

    def find_device(self, name_pattern: str, kind: str = "input") -> Optional[int]:
        """Find ALSA device by name pattern."""
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if name_pattern.lower() in dev["name"].lower():
                if kind == "input" and dev["max_input_channels"] > 0:
                    return i
                elif kind == "output" and dev["max_output_channels"] > 0:
                    return i
        return None

    def _input_callback(self, indata, frames, time, status):
        """Microphone input callback."""
        if status and not self._input_overflow_warned:
            logger.warning(f"Input status: {status}")
            self._input_overflow_warned = True

        if self.mic_enabled:
            # Resample to 16kHz for Whisper
            resampled = soxr.resample(indata[:, 0], self.SAMPLE_RATE, self.WHISPER_RATE)
            self.input_queue.put(resampled.astype(np.float32))

        # Debug: log periodically
        if not hasattr(self, '_callback_count'):
            self._callback_count = 0
        self._callback_count += 1
        if self._callback_count % 500 == 0:
            logger.warning(f"[AUDIO_IO] Input callback #{self._callback_count}, mic_enabled={self.mic_enabled}, queue_size={self.input_queue.qsize()}")

    def _output_callback(self, outdata, frames, time, status):
        """Speaker output callback."""
        if status and not self._output_underflow_warned:
            logger.warning(f"Output status: {status}")
            self._output_underflow_warned = True

        # Debug: log periodically
        if not hasattr(self, '_output_callback_count'):
            self._output_callback_count = 0
        self._output_callback_count += 1
        if self._output_callback_count % 500 == 0:
            print(f"[AUDIO_IO] Output callback #{self._output_callback_count}, buffer_size={self._playback_buffer.size}, queue_size={self.output_queue.qsize()}")

        with self._playback_lock:
            # Fill buffer from queue if needed
            while self._playback_buffer.size < frames * 2 and not self.output_queue.empty():
                try:
                    chunk = self.output_queue.get_nowait()
                    if isinstance(chunk, bytes):
                        # Convert int16 bytes to float32
                        new_data = (
                            np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                            / 32768.0
                        )
                        self._playback_buffer = np.concatenate(
                            (self._playback_buffer, new_data)
                        )
                    elif chunk == "__END__":
                        # Signal playback complete
                        if self._on_playback_complete:
                            threading.Thread(
                                target=self._on_playback_complete, daemon=True
                            ).start()
                except queue.Empty:
                    break

            # Write to output (stereo interleaved)
            if self._playback_buffer.size >= frames * 2:
                outdata[:, 0] = self._playback_buffer[::2][:frames]
                outdata[:, 1] = self._playback_buffer[1::2][:frames]
                self._playback_buffer = self._playback_buffer[frames * 2 :]
            elif self._playback_buffer.size > 0 and self.output_queue.empty():
                # Queue is empty but buffer has remaining data - play what we have
                # Zero-pad to fill the output frame
                samples_available = self._playback_buffer.size // 2  # stereo pairs
                if samples_available > 0:
                    outdata[:samples_available, 0] = self._playback_buffer[::2][:samples_available]
                    outdata[:samples_available, 1] = self._playback_buffer[1::2][:samples_available]
                    outdata[samples_available:, :] = 0  # Zero-pad rest
                    self._playback_buffer = np.zeros(0, dtype=np.float32)
                else:
                    outdata.fill(0)
            else:
                outdata.fill(0)

    def _output_callback_int16(self, outdata, frames, time, status):
        """Speaker output callback for int16 format (HDMI compatibility)."""
        if status and not self._output_underflow_warned:
            logger.warning(f"Output status: {status}")
            self._output_underflow_warned = True

        with self._playback_lock:
            # Fill buffer from queue if needed
            while self._playback_buffer.size < frames * 2 and not self.output_queue.empty():
                try:
                    chunk = self.output_queue.get_nowait()
                    if isinstance(chunk, bytes):
                        # Keep as int16 (no conversion needed)
                        new_data = np.frombuffer(chunk, dtype=np.int16)
                        self._playback_buffer = np.concatenate(
                            (self._playback_buffer, new_data.astype(np.float32))
                        )
                    elif chunk == "__END__":
                        if self._on_playback_complete:
                            threading.Thread(
                                target=self._on_playback_complete, daemon=True
                            ).start()
                except queue.Empty:
                    break

            # Write to output (stereo interleaved) - convert to int16
            if self._playback_buffer.size >= frames * 2:
                outdata[:, 0] = (self._playback_buffer[::2][:frames] * 32767).astype(np.int16)
                outdata[:, 1] = (self._playback_buffer[1::2][:frames] * 32767).astype(np.int16)
                self._playback_buffer = self._playback_buffer[frames * 2 :]
            elif self._playback_buffer.size > 0 and self.output_queue.empty():
                # Queue is empty but buffer has remaining data - play what we have
                samples_available = self._playback_buffer.size // 2
                if samples_available > 0:
                    outdata[:samples_available, 0] = (self._playback_buffer[::2][:samples_available] * 32767).astype(np.int16)
                    outdata[:samples_available, 1] = (self._playback_buffer[1::2][:samples_available] * 32767).astype(np.int16)
                    outdata[samples_available:, :] = 0
                    self._playback_buffer = np.zeros(0, dtype=np.float32)
                else:
                    outdata.fill(0)
            else:
                outdata.fill(0)

    def start(self):
        """Start audio streams."""
        # Find devices
        input_device = self.find_device("lelamp_capture", "input")
        output_device = self.find_device("lelamp_playback", "output")

        # Fallback to hardware devices
        if input_device is None:
            input_device = self.find_device("USB PnP Sound Device", "input")
        if output_device is None:
            output_device = self.find_device("USB PnP Audio Device", "output")

        # Final fallback to defaults
        if input_device is None:
            input_device = sd.default.device[0]
            logger.warning("Using default input device")
        if output_device is None:
            output_device = sd.default.device[1]
            logger.warning("Using default output device")

        devices = sd.query_devices()
        logger.info(f"Input device: [{input_device}] {devices[input_device]['name']}")
        logger.info(f"Output device: [{output_device}] {devices[output_device]['name']}")

        # Create separate streams (more stable than duplex)
        self._input_stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=self.BLOCK_SIZE,
            device=input_device,
            channels=1,
            dtype=np.float32,
            latency=self.LATENCY,
            callback=self._input_callback,
        )

        # Try float32 first, fallback to int16 for HDMI compatibility
        self._output_dtype = np.float32
        try:
            self._output_stream = sd.OutputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_SIZE,
                device=output_device,
                channels=self.CHANNELS_OUT,
                dtype=np.float32,
                latency=self.LATENCY,
                callback=self._output_callback,
            )
        except sd.PortAudioError as e:
            logger.warning(f"float32 output not supported, trying int16: {e}")
            self._output_dtype = np.int16
            self._output_stream = sd.OutputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_SIZE,
                device=output_device,
                channels=self.CHANNELS_OUT,
                dtype=np.int16,
                latency=self.LATENCY,
                callback=self._output_callback_int16,
            )

        self._input_stream.start()
        self._output_stream.start()
        self._running = True
        logger.info(f"Audio streams started (output dtype: {self._output_dtype})")

    def stop(self):
        """Stop audio streams."""
        self._running = False
        if self._input_stream:
            self._input_stream.stop()
            self._input_stream.close()
        if self._output_stream:
            self._output_stream.stop()
            self._output_stream.close()
        logger.info("Audio streams stopped")

    def mute_mic(self, muted: bool = True):
        """Mute/unmute microphone during playback."""
        self.mic_enabled = not muted
        # Always log mic state changes for debugging
        print(f"[AUDIO_IO] mute_mic({muted}) -> mic_enabled={self.mic_enabled}")
        logger.debug(f"Mic muted: {muted}")

    def play_audio(self, audio_data: bytes):
        """Queue audio for playback (int16 stereo 48kHz bytes)."""
        self.output_queue.put(audio_data)

    def signal_playback_end(self):
        """Signal end of current playback sequence."""
        self.output_queue.put("__END__")

    def on_playback_complete(self, callback: Callable):
        """Register callback for when playback completes."""
        self._on_playback_complete = callback

    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        with self._playback_lock:
            return self._playback_buffer.size > 0 or not self.output_queue.empty()

    async def wait_for_playback(self):
        """Wait until playback buffer is empty."""
        wait_count = 0
        while self.is_playing():
            wait_count += 1
            if wait_count % 100 == 0:  # Log every 5 seconds (100 * 0.05s)
                with self._playback_lock:
                    print(f"[AUDIO_IO] wait_for_playback: buffer_size={self._playback_buffer.size}, queue_size={self.output_queue.qsize()}")
            await asyncio.sleep(0.05)
        print(f"[AUDIO_IO] wait_for_playback complete after {wait_count} iterations")

    def get_audio_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """
        Get next audio chunk from input queue.

        Returns:
            Audio chunk as float32 numpy array (16kHz), or None if timeout
        """
        try:
            return self.input_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_input_queue(self):
        """Clear any buffered input audio."""
        while not self.input_queue.empty():
            try:
                self.input_queue.get_nowait()
            except queue.Empty:
                break
