"""
Local speech-to-text using Faster Whisper.

Adapted from ~/Faster-Local-Voice-AI-Whisper/server.py
"""

import numpy as np
import time
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# Lazy import for faster startup
_whisper_model = None


def get_whisper_model(model_size: str = "tiny", compute_type: str = "int8"):
    """Get or create Whisper model (singleton)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        logger.info(f"Loading Whisper model: {model_size} ({compute_type})")
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        logger.info("Whisper model loaded")
    return _whisper_model


class LocalSTTService:
    """Local speech-to-text using Faster Whisper."""

    # VAD settings
    SILENCE_THRESHOLD = 0.01  # RMS threshold for silence
    SILENCE_DURATION = 0.5  # Seconds of silence to trigger transcription
    MIN_AUDIO_LENGTH = 0.3  # Minimum audio length to transcribe
    MIN_SPEECH_DURATION = 0.15  # Minimum speech duration before counting silence (prevents false triggers)
    RATE = 16000  # Expected input sample rate

    # Filter garbage transcriptions
    LOW_EFFORT_UTTERANCES = {"huh", "uh", "um", "erm", "hmm", "he's", "but", "the"}
    GARBAGE_PATTERNS = [
        # Non-English hallucinations from noise
        "Музыкальная",
        "музыка",
        "Untertitelung",
        "字幕",
        "謝謝",
        "ご視聴",
        "구독",
        # Common Whisper hallucinations
        "Thank you for watching",
        "Thanks for watching",
        "Please subscribe",
        "Like and subscribe",
        "See you next time",
        "Bye bye",
    ]

    def __init__(
        self,
        model_size: str = "tiny",
        compute_type: str = "int8",
        silence_threshold: float = None,
        silence_duration: float = None,
        min_audio_length: float = None,
    ):
        self.model_size = model_size
        self.compute_type = compute_type
        self.model = None  # Lazy loaded

        # Configurable VAD settings
        self.silence_threshold = silence_threshold or self.SILENCE_THRESHOLD
        self.silence_duration = silence_duration or self.SILENCE_DURATION
        self.min_audio_length = min_audio_length or self.MIN_AUDIO_LENGTH

        # State for VAD
        self.audio_buffer: List[float] = []
        self.silence_start: Optional[float] = None
        self.is_speaking = False
        self.speech_start_time: Optional[float] = None

    def _ensure_model(self):
        """Ensure Whisper model is loaded."""
        if self.model is None:
            self.model = get_whisper_model(self.model_size, self.compute_type)

    def _detect_silence(self, audio_chunk: np.ndarray) -> bool:
        """Check if audio chunk is silence based on RMS."""
        rms = np.sqrt(np.mean(np.square(audio_chunk)))
        is_silence = rms < self.silence_threshold
        # Debug: print RMS periodically
        if not hasattr(self, '_rms_counter'):
            self._rms_counter = 0
        self._rms_counter += 1
        if self._rms_counter % 50 == 0:  # Print every 50 chunks (~5 seconds)
            print(f"[STT] RMS: {rms:.4f}, threshold: {self.silence_threshold}, silence: {is_silence}, speaking: {self.is_speaking}")
        return is_silence

    def _is_garbage(self, text: str) -> bool:
        """Check if transcription is garbage/hallucination."""
        if not text or len(text.strip()) < 2:
            return True

        text_lower = text.lower().strip()

        # Check low effort utterances
        cleaned = text_lower.strip(".,!? ")
        if cleaned in self.LOW_EFFORT_UTTERANCES:
            return True

        # Check garbage patterns
        for pattern in self.GARBAGE_PATTERNS:
            if pattern.lower() in text_lower:
                return True

        # Check if mostly non-ASCII (likely non-English hallucination)
        ascii_count = sum(1 for c in text if ord(c) < 128)
        if len(text) > 0 and ascii_count / len(text) < 0.5:
            return True

        return False

    def _transcribe(self) -> Tuple[str, float]:
        """Transcribe accumulated audio buffer."""
        self._ensure_model()

        if len(self.audio_buffer) < int(self.RATE * self.min_audio_length):
            return "", 0

        stt_start = time.time()

        # Convert to numpy array
        audio_np = np.array(self.audio_buffer, dtype=np.float32)

        # Transcribe with faster-whisper
        segments, info = self.model.transcribe(
            audio_np,
            language="en",
            beam_size=1,  # Faster
            best_of=1,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=100,
            ),
        )

        # Collect all text
        text = " ".join(segment.text for segment in segments).strip()

        stt_time = (time.time() - stt_start) * 1000
        return text, stt_time

    def process_audio_chunk(
        self, audio_chunk: np.ndarray
    ) -> Optional[Tuple[str, float, float]]:
        """
        Process audio chunk with VAD.

        Args:
            audio_chunk: Audio data as float32 numpy array (16kHz)

        Returns:
            Tuple of (transcription, stt_time_ms, audio_duration_ms) when speech ends,
            None otherwise
        """
        is_silence = self._detect_silence(audio_chunk)

        if not is_silence:
            # Speech detected
            if not self.is_speaking:
                self.speech_start_time = time.time()
                logger.debug("Speech started")
            self.is_speaking = True
            self.silence_start = None
            self.audio_buffer.extend(audio_chunk.tolist())
        else:
            if self.is_speaking:
                # Only count silence if we've had enough actual speech
                # This prevents false triggers from brief noise spikes
                speech_duration = time.time() - self.speech_start_time if self.speech_start_time else 0
                if speech_duration < self.MIN_SPEECH_DURATION:
                    # Not enough speech yet - reset and ignore
                    logger.debug(f"Ignoring short speech burst ({speech_duration:.2f}s < {self.MIN_SPEECH_DURATION}s)")
                    self.audio_buffer = []
                    self.is_speaking = False
                    self.speech_start_time = None
                    self.silence_start = None
                    return None

                # Silence after real speech - keep buffering briefly
                self.audio_buffer.extend(audio_chunk.tolist())

                if self.silence_start is None:
                    self.silence_start = time.time()
                elif time.time() - self.silence_start >= self.silence_duration:
                    # Enough silence, transcribe
                    audio_duration = (
                        (time.time() - self.speech_start_time) * 1000
                        if self.speech_start_time
                        else 0
                    )
                    text, stt_time = self._transcribe()

                    # Reset state
                    self.audio_buffer = []
                    self.silence_start = None
                    self.is_speaking = False
                    self.speech_start_time = None

                    # Filter garbage
                    if self._is_garbage(text):
                        logger.debug(f"Filtered garbage transcription: {text[:50]}")
                        return None

                    if text:
                        logger.info(f"Transcribed: {text}")
                        return (text, stt_time, audio_duration)

        return None

    def reset(self):
        """Reset VAD state."""
        self.audio_buffer = []
        self.silence_start = None
        self.is_speaking = False
        self.speech_start_time = None

    def transcribe_buffer(self, audio_data: np.ndarray) -> Tuple[str, float]:
        """
        Directly transcribe an audio buffer (bypass VAD).

        Args:
            audio_data: Audio as float32 numpy array (16kHz)

        Returns:
            Tuple of (transcription, stt_time_ms)
        """
        self._ensure_model()

        stt_start = time.time()

        segments, info = self.model.transcribe(
            audio_data,
            language="en",
            beam_size=1,
            best_of=1,
            vad_filter=True,
        )

        text = " ".join(segment.text for segment in segments).strip()
        stt_time = (time.time() - stt_start) * 1000

        return text, stt_time
