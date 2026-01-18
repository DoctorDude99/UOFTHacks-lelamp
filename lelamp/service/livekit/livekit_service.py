"""
LiveKit Service Implementation.

Manages LiveKit Cloud connection and provides interface for AI agents.
Supports multiple realtime AI providers: OpenAI, Grok, Gemini, Azure, etc.
"""

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict

from livekit import agents
from livekit.agents import AgentSession, RoomInputOptions
from livekit.plugins import noise_cancellation, silero

import lelamp.globals as g
from lelamp.user_data import USER_DATA_DIR, get_device_serial_short

logger = logging.getLogger(__name__)

# Provider to API key environment variable mapping
PROVIDER_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "grok": "XAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "aws": "AWS_ACCESS_KEY_ID",  # AWS uses multiple keys
    "ultravox": "ULTRAVOX_API_KEY",
}


class LiveKitStatus(Enum):
    """LiveKit service status."""
    UNCONFIGURED = "unconfigured"      # Missing credentials
    READY = "ready"                     # Configured, not connected
    CONNECTING = "connecting"           # Connection in progress
    CONNECTED = "connected"             # Connected to room
    ERROR = "error"                     # Connection error


@dataclass
class LiveKitCredentials:
    """LiveKit Cloud credentials with multi-provider support."""
    url: str
    api_key: str
    api_secret: str
    # Provider API keys - stored by provider name
    provider_keys: Dict[str, str] = field(default_factory=dict)
    # Current provider
    provider: str = "openai"

    @property
    def current_provider_key(self) -> str:
        """Get API key for current provider."""
        return self.provider_keys.get(self.provider, "")

    @property
    def is_complete(self) -> bool:
        """Check if all credentials are present for current provider."""
        provider_key = self.current_provider_key
        return bool(
            self.url and
            self.api_key and
            self.api_secret and
            provider_key and
            len(provider_key) >= 10
        )

    @property
    def missing_keys(self) -> list:
        """Get list of missing credential keys."""
        missing = []
        if not self.url:
            missing.append("LIVEKIT_URL")
        if not self.api_key:
            missing.append("LIVEKIT_API_KEY")
        if not self.api_secret:
            missing.append("LIVEKIT_API_SECRET")

        # Check provider-specific API key
        provider_key = self.current_provider_key
        if not provider_key or len(provider_key) < 10:
            env_var = PROVIDER_API_KEYS.get(self.provider, f"{self.provider.upper()}_API_KEY")
            missing.append(env_var)

        return missing


class LiveKitService:
    """
    LiveKit Cloud connection manager.

    Encapsulates the LiveKit agents worker and provides a clean interface
    for AI agents to connect to rooms.
    """

    def __init__(self, config: dict):
        """
        Initialize LiveKit service.

        Args:
            config: Application configuration dict
        """
        self.config = config
        self._status = LiveKitStatus.UNCONFIGURED
        self._error_message: Optional[str] = None
        self._credentials: Optional[LiveKitCredentials] = None
        self._room_name: Optional[str] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        # Callbacks
        self._on_status_change: Optional[Callable[[LiveKitStatus], None]] = None
        self._on_connected: Optional[Callable[[], None]] = None
        self._on_disconnected: Optional[Callable[[], None]] = None

        # Load and validate credentials
        self._load_credentials()
        self._room_name = f"lelamp-{get_device_serial_short()}"

        logger.info(f"LiveKit service initialized (status={self._status.value}, room={self._room_name})")

    def _load_credentials(self):
        """Load credentials from environment and .env file."""
        # Try environment first, then .env file
        url = os.getenv("LIVEKIT_URL", "").strip() or self._get_env_value("LIVEKIT_URL")
        api_key = os.getenv("LIVEKIT_API_KEY", "").strip() or self._get_env_value("LIVEKIT_API_KEY")
        api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip() or self._get_env_value("LIVEKIT_API_SECRET")

        # Load all provider API keys
        provider_keys = {}
        for provider, env_var in PROVIDER_API_KEYS.items():
            key = os.getenv(env_var, "").strip() or self._get_env_value(env_var)
            if key:
                provider_keys[provider] = key

        # Get current provider from config
        provider = self.config.get("pipeline", {}).get("provider", "openai")

        self._credentials = LiveKitCredentials(
            url=url or "",
            api_key=api_key or "",
            api_secret=api_secret or "",
            provider_keys=provider_keys,
            provider=provider,
        )

        if self._credentials.is_complete:
            self._status = LiveKitStatus.READY
        else:
            self._status = LiveKitStatus.UNCONFIGURED
            missing = self._credentials.missing_keys
            logger.warning(f"LiveKit not configured. Missing: {', '.join(missing)}")

    def _get_env_value(self, key: str) -> Optional[str]:
        """Get a value from .env file."""
        env_path = USER_DATA_DIR / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text().splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            return v.strip()
            except Exception:
                pass
        return None

    @property
    def status(self) -> LiveKitStatus:
        """Get current service status."""
        return self._status

    @property
    def is_configured(self) -> bool:
        """Check if service has valid credentials."""
        return self._credentials is not None and self._credentials.is_complete

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to a room."""
        return self._status == LiveKitStatus.CONNECTED

    @property
    def room_name(self) -> str:
        """Get the device's room name."""
        return self._room_name or f"lelamp-{get_device_serial_short()}"

    @property
    def error_message(self) -> Optional[str]:
        """Get last error message if status is ERROR."""
        return self._error_message

    @property
    def credentials(self) -> Optional[LiveKitCredentials]:
        """Get current credentials (for status display)."""
        return self._credentials

    def _set_status(self, status: LiveKitStatus, error: Optional[str] = None):
        """Update status and notify listeners."""
        old_status = self._status
        self._status = status
        self._error_message = error

        if old_status != status:
            logger.info(f"LiveKit status: {old_status.value} -> {status.value}")
            if self._on_status_change:
                try:
                    self._on_status_change(status)
                except Exception as e:
                    logger.error(f"Status change callback error: {e}")

    def on_status_change(self, callback: Callable[[LiveKitStatus], None]):
        """Register callback for status changes."""
        self._on_status_change = callback

    def on_connected(self, callback: Callable[[], None]):
        """Register callback for when connected to room."""
        self._on_connected = callback

    def on_disconnected(self, callback: Callable[[], None]):
        """Register callback for when disconnected from room."""
        self._on_disconnected = callback

    def get_worker_options(self) -> Optional[agents.WorkerOptions]:
        """
        Get configured WorkerOptions for agents.cli.run_app().

        Returns:
            WorkerOptions if configured, None if missing credentials
        """
        if not self.is_configured:
            return None

        # Import here to avoid circular imports
        from lelamp.pipelines.livekit_realtime import entrypoint

        return agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            num_idle_processes=1,
        )

    @property
    def provider(self) -> str:
        """Get current AI provider."""
        return self._credentials.provider if self._credentials else "openai"

    def get_voice(self) -> str:
        """Get configured voice for current provider."""
        from lelamp.pipelines.livekit_realtime import DEFAULT_VOICES
        provider = self.provider
        default = DEFAULT_VOICES.get(provider, "alloy")
        return self.config.get("pipeline", {}).get("voice", default)

    # Legacy alias
    def get_openai_voice(self) -> str:
        """Get configured voice (legacy alias for get_voice)."""
        return self.get_voice()

    def create_realtime_model(self) -> "openai.realtime.RealtimeModel":
        """
        Create OpenAI Realtime model with configured settings.

        Returns:
            Configured RealtimeModel instance
        """
        mute_mic = self.config.get("mute_mic_while_speaking", False)
        turn_detection = None if mute_mic else "server_vad"
        voice = self.get_openai_voice()

        logger.info(f"Creating RealtimeModel (voice={voice}, turn_detection={turn_detection})")

        return openai.realtime.RealtimeModel(
            voice=voice,
            turn_detection=turn_detection,
        )

    def create_vad_model(self) -> Optional["silero.VAD"]:
        """
        Create VAD model if mic muting is enabled.

        Returns:
            Silero VAD model or None
        """
        mute_mic = self.config.get("mute_mic_while_speaking", False)
        if not mute_mic:
            return None

        vad_config = self.config.get("vad", {})
        return silero.VAD.load(
            min_speech_duration=vad_config.get("min_speech_duration", 0.1),
            min_silence_duration=vad_config.get("min_silence_duration", 0.8),
            activation_threshold=vad_config.get("activation_threshold", 0.6),
        )

    def start(self) -> bool:
        """
        Start the LiveKit worker in a background thread.

        Returns:
            True if started successfully, False if not configured
        """
        if not self.is_configured:
            logger.error("Cannot start LiveKit: not configured")
            self._set_status(LiveKitStatus.UNCONFIGURED)
            return False

        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("LiveKit worker already running")
            return True

        self._shutdown_event.clear()
        self._set_status(LiveKitStatus.CONNECTING)

        def run_worker():
            """Run LiveKit worker in thread."""
            try:
                worker_options = self.get_worker_options()
                if worker_options:
                    # Set LiveKit environment variables
                    os.environ["LIVEKIT_URL"] = self._credentials.url
                    os.environ["LIVEKIT_API_KEY"] = self._credentials.api_key
                    os.environ["LIVEKIT_API_SECRET"] = self._credentials.api_secret

                    # Set provider-specific API key environment variable
                    provider = self._credentials.provider
                    provider_key = self._credentials.current_provider_key
                    env_var = PROVIDER_API_KEYS.get(provider, f"{provider.upper()}_API_KEY")
                    os.environ[env_var] = provider_key
                    logger.info(f"Set {env_var} for provider: {provider}")

                    self._set_status(LiveKitStatus.CONNECTED)
                    if self._on_connected:
                        self._on_connected()

                    # This blocks until worker stops
                    agents.cli.run_app(worker_options)

            except Exception as e:
                logger.error(f"LiveKit worker error: {e}", exc_info=True)
                self._set_status(LiveKitStatus.ERROR, str(e))
            finally:
                self._set_status(LiveKitStatus.READY)
                if self._on_disconnected:
                    self._on_disconnected()

        self._worker_thread = threading.Thread(
            target=run_worker,
            name="LiveKitWorker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("LiveKit worker thread started")
        return True

    def stop(self):
        """Stop the LiveKit worker."""
        logger.info("Stopping LiveKit service...")
        self._shutdown_event.set()

        # The worker thread is daemon, so it will be killed when process exits
        # For clean shutdown, we'd need to implement worker interruption
        # which requires changes to how agents.cli.run_app() works

        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
            self._worker_thread = None

        self._set_status(LiveKitStatus.READY)
        logger.info("LiveKit service stopped")

    def reload_credentials(self):
        """Reload credentials from environment/.env file."""
        self._load_credentials()
        logger.info(f"Credentials reloaded (configured={self.is_configured})")

    def get_status_dict(self) -> dict:
        """Get status as dictionary for API responses."""
        return {
            "status": self._status.value,
            "configured": self.is_configured,
            "connected": self.is_connected,
            "room_name": self.room_name,
            "error": self._error_message,
            "missing_keys": self._credentials.missing_keys if self._credentials else [],
            "provider": self.provider,
            "voice": self.get_voice(),
            # Legacy field
            "openai_voice": self.get_voice(),
        }


# Singleton instance
_livekit_service: Optional[LiveKitService] = None


def get_livekit_service() -> Optional[LiveKitService]:
    """Get the LiveKit service singleton."""
    return _livekit_service


def init_livekit_service(config: dict) -> LiveKitService:
    """Initialize the LiveKit service singleton."""
    global _livekit_service
    _livekit_service = LiveKitService(config)
    return _livekit_service
