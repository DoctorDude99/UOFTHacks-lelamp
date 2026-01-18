"""
Local text-to-speech using Piper.

Adapted from ~/Faster-Local-Voice-AI-Whisper/server.py
"""

import asyncio
import json
import os
import logging
import numpy as np
from typing import AsyncGenerator, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalTTSService:
    """Local text-to-speech using Piper."""

    # Default paths (relative to lelampv2 repo directory)
    @staticmethod
    def _get_lelamp_dir() -> Path:
        """Get the lelampv2 directory."""
        # Try environment variable first
        if os.environ.get("LELAMP_DIR"):
            return Path(os.environ["LELAMP_DIR"])
        # Fall back to relative path from this file
        return Path(__file__).parent.parent.parent.parent

    @classmethod
    def _default_piper_path(cls) -> Path:
        return cls._get_lelamp_dir() / "piper" / "piper"

    @classmethod
    def _default_voices_dir(cls) -> Path:
        return cls._get_lelamp_dir() / "piper" / "voices"

    # Legacy paths for backwards compatibility
    LEGACY_PIPER_PATH = Path.home() / "Faster-Local-Voice-AI-Whisper" / "piper" / "piper"
    LEGACY_VOICES_DIR = Path.home() / "Faster-Local-Voice-AI-Whisper" / "voices"

    def __init__(
        self,
        piper_path: str = None,
        voices_dir: str = None,
        voice: str = "en_US-ryan-medium.onnx",
    ):
        # Determine piper path - check new location first, then legacy
        if piper_path:
            self.piper_path = Path(piper_path)
        elif self._default_piper_path().exists():
            self.piper_path = self._default_piper_path()
        elif self.LEGACY_PIPER_PATH.exists():
            self.piper_path = self.LEGACY_PIPER_PATH
            logger.info(f"Using legacy Piper path: {self.piper_path}")
        else:
            self.piper_path = self._default_piper_path()  # Will fail with clear error

        # Determine voices directory - check new location first, then legacy
        if voices_dir:
            self.voices_dir = Path(voices_dir)
        elif self._default_voices_dir().exists():
            self.voices_dir = self._default_voices_dir()
        elif self.LEGACY_VOICES_DIR.exists():
            self.voices_dir = self.LEGACY_VOICES_DIR
            logger.info(f"Using legacy voices path: {self.voices_dir}")
        else:
            self.voices_dir = self._default_voices_dir()  # Will fail with clear error
        self.voice = voice
        self.piper_proc: Optional[asyncio.subprocess.Process] = None
        self._sample_rate: Optional[int] = None

    def get_voice_sample_rate(self) -> int:
        """Get sample rate for current voice from JSON metadata."""
        if self._sample_rate:
            return self._sample_rate

        json_path = self.voices_dir / f"{self.voice}.json"
        try:
            with open(json_path) as f:
                meta = json.load(f)
            self._sample_rate = meta.get("audio", {}).get("sample_rate", 22050)
        except Exception:
            self._sample_rate = 22050  # Default for most Piper voices

        return self._sample_rate

    def list_voices(self) -> list:
        """List available voice models."""
        voices = []
        if self.voices_dir.exists():
            for f in self.voices_dir.glob("*.onnx"):
                voices.append(f.name)
        return sorted(voices)

    def set_voice(self, voice: str):
        """Change voice model (requires restart)."""
        voice_path = self.voices_dir / voice
        if not voice_path.exists():
            raise ValueError(f"Voice not found: {voice}")
        self.voice = voice
        self._sample_rate = None  # Reset cached sample rate

    async def start(self):
        """Start Piper subprocess."""
        if self.piper_proc and self.piper_proc.returncode is None:
            return  # Already running

        voice_model_path = self.voices_dir / self.voice

        if not self.piper_path.exists():
            raise FileNotFoundError(f"Piper binary not found: {self.piper_path}")
        if not voice_model_path.exists():
            raise FileNotFoundError(f"Voice model not found: {voice_model_path}")

        logger.info(f"Starting Piper with voice: {self.voice}")

        # Set library path for Piper dependencies
        env = os.environ.copy()
        piper_dir = self.piper_path.parent
        env["LD_LIBRARY_PATH"] = f"{piper_dir}:{env.get('LD_LIBRARY_PATH', '')}"

        self.piper_proc = await asyncio.create_subprocess_exec(
            str(self.piper_path),
            "--model",
            str(voice_model_path),
            "--output_raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Start stderr monitor
        asyncio.create_task(self._monitor_stderr())
        logger.info("Piper subprocess started")

    async def _monitor_stderr(self):
        """Monitor Piper stderr for errors."""
        if not self.piper_proc or not self.piper_proc.stderr:
            return
        while True:
            line = await self.piper_proc.stderr.readline()
            if not line:
                break
            # Only log warnings/errors
            text = line.decode().strip()
            if text and not text.startswith("["):
                logger.debug(f"Piper: {text}")

    async def stop(self):
        """Stop Piper subprocess."""
        if self.piper_proc:
            try:
                self.piper_proc.stdin.close()
                await self.piper_proc.wait()
            except Exception as e:
                logger.warning(f"Error stopping Piper: {e}")
            self.piper_proc = None
        logger.info("Piper subprocess stopped")

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text to audio chunks.

        Yields raw PCM audio data (int16 stereo 48kHz).
        """
        if not text or not text.strip():
            return

        if not self.piper_proc or self.piper_proc.returncode is not None:
            await self.start()

        sample_rate = self.get_voice_sample_rate()

        # Send text to Piper
        try:
            self.piper_proc.stdin.write(text.encode() + b"\n")
            await self.piper_proc.stdin.drain()
        except Exception as e:
            logger.error(f"Error writing to Piper: {e}")
            await self.start()  # Restart and retry
            self.piper_proc.stdin.write(text.encode() + b"\n")
            await self.piper_proc.stdin.drain()

        # Read raw PCM output
        # Piper can take 2-3 seconds to generate audio on first request
        raw_pcm = b""
        start_time = asyncio.get_event_loop().time()
        last_data_time = start_time
        initial_timeout = 5.0  # Wait up to 5s for first audio
        streaming_timeout = 1.0  # Once streaming, wait up to 1s for more data

        while True:
            try:
                # Use longer timeout until we get first data
                timeout = streaming_timeout if raw_pcm else initial_timeout
                chunk = await asyncio.wait_for(
                    self.piper_proc.stdout.read(4096), timeout=timeout
                )
                if chunk:
                    raw_pcm += chunk
                    last_data_time = asyncio.get_event_loop().time()
                else:
                    break
            except asyncio.TimeoutError:
                # If we have data and haven't received more in streaming_timeout, we're done
                if raw_pcm and (asyncio.get_event_loop().time() - last_data_time > streaming_timeout):
                    break
                # If no data after initial_timeout, give up
                if not raw_pcm and (asyncio.get_event_loop().time() - start_time > initial_timeout):
                    logger.warning("Piper timeout - no audio generated")
                    break

        if not raw_pcm:
            return

        # Normalize audio levels
        pcm_array = np.frombuffer(raw_pcm, dtype=np.int16)
        if len(pcm_array) > 0:
            max_amplitude = np.max(np.abs(pcm_array))
            if max_amplitude > 0:
                # Normalize to ~70% max amplitude
                scale = 22937 / max_amplitude
                pcm_array = (pcm_array * scale).astype(np.int16)
                raw_pcm = pcm_array.tobytes()

        # Add small silence padding at end
        duration_secs = len(raw_pcm) / (sample_rate * 2)  # 2 bytes per sample
        silence_ms = 150 if duration_secs < 0.5 else 20
        raw_pcm += b"\x00" * int(sample_rate * silence_ms / 1000 * 2)

        # Resample to 48kHz stereo for playback
        resampled = await self._resample_audio(raw_pcm, sample_rate)

        # Yield in chunks
        chunk_size = 2048
        for i in range(0, len(resampled), chunk_size):
            yield resampled[i : i + chunk_size]

    async def _resample_audio(self, raw_pcm: bytes, input_rate: int) -> bytes:
        """Resample audio to 24kHz stereo using sox (matches OpenAI Realtime API rate)."""
        sox_cmd = [
            "sox",
            "-t",
            "raw",
            "-r",
            str(input_rate),
            "-c",
            "1",
            "-b",
            "16",
            "-e",
            "signed-integer",
            "-",
            "-r",
            "24000",  # Standardized to match OpenAI Realtime API
            "-c",
            "2",
            "-t",
            "raw",
            "-",
            "gain",
            "-3",
        ]

        sox_proc = await asyncio.create_subprocess_exec(
            *sox_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await sox_proc.communicate(input=raw_pcm)

        if stderr:
            error = stderr.decode().strip()
            if error and "WARN" not in error:
                logger.warning(f"Sox: {error}")

        return stdout

    async def synthesize_to_bytes(self, text: str) -> bytes:
        """
        Synthesize text to complete audio bytes.

        Returns all audio as a single bytes object.
        """
        chunks = []
        async for chunk in self.synthesize(text):
            chunks.append(chunk)
        return b"".join(chunks)
