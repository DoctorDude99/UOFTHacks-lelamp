"""
Wake Service - Local wake word detection using Whisper
Listens for "wake up" locally without sending audio to cloud
"""
import threading
import logging
from typing import Optional, Callable
import numpy as np
import sounddevice as sd
import queue
import time

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    whisper = None


class WakeService:
    """
    Local wake word detection service using Whisper tiny model
    Runs in background thread, calls callback when wake word detected
    """

    def __init__(self, wake_phrases: list = None, model_size: str = "tiny"):
        """
        Initialize wake service

        Args:
            wake_phrases: List of phrases to detect (default: ["wake up", "hey lamp"])
            model_size: Whisper model size (tiny, base, small) - tiny is fastest
        """
        if not WHISPER_AVAILABLE:
            raise RuntimeError("Whisper not installed. Install with: pip install openai-whisper")

        self.logger = logging.getLogger("service.WakeService")

        self.wake_phrases = wake_phrases or ["wake up", "hey lamp", "wake"]
        self.model_size = model_size
        self.model = None
        self._running = False
        self._thread = None
        self._callback: Optional[Callable[[], None]] = None
        self._audio_queue = queue.Queue(maxsize=50)  # Limit queue size to prevent buildup

        # Audio settings
        # Capture at 24kHz to match ALSA dsnoop config, resample to 16kHz for Whisper
        self.capture_rate = 24000  # ALSA dsnoop is configured for 24kHz
        self.whisper_rate = 16000  # Whisper expects 16kHz
        self.chunk_duration = 2  # Process 2-second chunks (faster processing)
        self.chunk_samples = self.capture_rate * self.chunk_duration
        self.blocksize = 512  # Smaller blocks to reduce overflow

        # Overflow tracking
        self._overflow_logged = False

    def start(self, callback: Callable[[], None]):
        """
        Start listening for wake word

        Args:
            callback: Function to call when wake word detected
        """
        if self._running:
            self.logger.warning("Wake word service already running")
            return

        self._callback = callback
        self._running = True

        # Load Whisper model
        try:
            self.logger.info(f"Loading Whisper {self.model_size} model...")
            self.model = whisper.load_model(self.model_size)
            self.logger.info("Whisper model loaded")

            # Start audio capture with smaller blocksize to reduce overflow
            # Use the dsnoop device for mic sharing (lelamp_capture or hw_capture_dsnoop)
            # Find the device by name since index can change
            device = None
            try:
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    dev_name = dev['name'] if isinstance(dev, dict) else str(dev)
                    if 'lelamp_capture' in dev_name or 'hw_capture_dsnoop' in dev_name:
                        device = i
                        self.logger.info(f"Found capture device: {dev_name} (index {i})")
                        break
                if device is None:
                    # Fallback to default input
                    device = sd.default.device[0]
                    self.logger.warning(f"Using default input device: {device}")
            except Exception as e:
                self.logger.warning(f"Error finding device, using default: {e}")

            self._audio_stream = sd.InputStream(
                samplerate=self.capture_rate,
                channels=1,
                dtype='float32',
                blocksize=self.blocksize,
                callback=self._audio_callback,
                device=device
            )
            self._audio_stream.start()

            # Start processing thread
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()

            self.logger.info(f"Wake word service started, listening for: {self.wake_phrases}")

        except Exception as e:
            self.logger.error(f"Failed to start wake word service: {e}")
            self._running = False
            raise

    def stop(self):
        """Stop listening for wake word"""
        self._running = False

        if hasattr(self, '_audio_stream') and self._audio_stream:
            self._audio_stream.stop()
            self._audio_stream.close()

        if self._thread:
            self._thread.join(timeout=2.0)

        self.logger.info("Wake word service stopped")

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio callback - queues audio chunks for processing"""
        if status:
            # Only log overflow once to avoid spam
            if not self._overflow_logged:
                self.logger.info(f"Audio input overflow (CPU busy) - this is normal during processing")
                self._overflow_logged = True

        # Try to add to queue, drop if full
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
            # Queue full, drop oldest audio chunk to make room
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(indata.copy())
            except:
                pass  # Just drop this frame if we can't add it

    def _listen_loop(self):
        """Main listening loop (runs in background thread)"""
        audio_buffer = []

        while self._running:
            try:
                # Get audio chunk (timeout to allow checking _running flag)
                try:
                    chunk = self._audio_queue.get(timeout=0.5)
                    audio_buffer.append(chunk)
                except queue.Empty:
                    continue

                # Process when we have enough audio
                total_samples = sum(len(c) for c in audio_buffer)
                if total_samples >= self.chunk_samples:
                    # Clear queue to avoid processing stale audio while Whisper runs
                    # This prevents the queue from building up during processing
                    while not self._audio_queue.empty():
                        try:
                            self._audio_queue.get_nowait()
                        except queue.Empty:
                            break

                    # Concatenate and convert to format Whisper expects
                    # Flatten each chunk first to handle both 1D and 2D arrays
                    flattened_chunks = [c.flatten() for c in audio_buffer]
                    audio_24k = np.concatenate(flattened_chunks)

                    # Check if audio has enough energy (skip if too quiet)
                    audio_energy = np.sqrt(np.mean(audio_24k**2))
                    if audio_energy < 0.01:  # Very quiet, likely silence
                        audio_buffer = []
                        continue

                    # Resample from 24kHz to 16kHz for Whisper
                    if self.capture_rate != self.whisper_rate:
                        # Simple linear interpolation resampling
                        num_samples = int(len(audio_24k) * self.whisper_rate / self.capture_rate)
                        indices = np.linspace(0, len(audio_24k) - 1, num_samples)
                        audio_16k = np.interp(indices, np.arange(len(audio_24k)), audio_24k).astype(np.float32)
                    else:
                        audio_16k = audio_24k

                    # Transcribe with Whisper (using 16kHz resampled audio)
                    result = self.model.transcribe(
                        audio_16k,
                        language="en",
                        fp16=False,  # RPi doesn't have FP16
                        task="transcribe"
                    )

                    text = result["text"].lower().strip()
                    self.logger.debug(f"Detected: '{text}'")

                    # Check if any wake phrase is in the transcription
                    for phrase in self.wake_phrases:
                        if phrase in text:
                            self.logger.info(f"Wake phrase '{phrase}' detected!")

                            # Call the callback
                            if self._callback:
                                try:
                                    self._callback()
                                except Exception as e:
                                    self.logger.error(f"Error in wake word callback: {e}")

                            # Clear buffer after detection
                            audio_buffer = []
                            break

                    # Keep only last 1 second of original 24kHz audio (for overlap)
                    # Store as 2D to match what audio callback provides
                    overlap_samples = self.capture_rate * 1
                    if len(audio_24k) > overlap_samples:
                        # Reshape back to 2D (N, 1) to match audio callback format
                        audio_buffer = [audio_24k[-overlap_samples:].reshape(-1, 1)]
                    else:
                        audio_buffer = []

            except Exception as e:
                if self._running:  # Only log if we're supposed to be running
                    self.logger.error(f"Error in wake word detection: {e}")
                time.sleep(0.1)

    def is_running(self) -> bool:
        """Check if service is running"""
        return self._running
