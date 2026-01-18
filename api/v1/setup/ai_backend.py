"""
AI Backend Selection API endpoints.

Provides endpoints for selecting and configuring the AI backend:
- LiveKit Realtime with multiple providers (OpenAI, Grok, Gemini, etc.)
- Local AI (Ollama + Whisper + Piper with voice selection)
- Voice preview/testing
- API key validation
"""

import asyncio
import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.deps import load_config, save_config

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# AI Backend Definitions
# =============================================================================

AI_BACKENDS = {
    "livekit-realtime": {
        "name": "LiveKit Realtime",
        "description": "Real-time voice AI via LiveKit Cloud",
        "requires": [],  # Depends on provider
        "features": ["Real-time voice", "Low latency", "Cloud-based", "Multiple providers"],
        "recommended": True,
        "has_providers": True,
    },
    "local": {
        "name": "Local AI",
        "description": "Offline AI using Faster Whisper + Ollama + Piper TTS",
        "requires": [],
        "features": ["Offline capable", "Privacy focused", "No API costs", "Multiple voices"],
        "recommended": False,
        "has_providers": False,
    },
}

# Provider definitions for livekit-realtime
REALTIME_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "description": "GPT-4o Realtime API",
        "api_key_env": "OPENAI_API_KEY",
        "api_key_url": "https://platform.openai.com/api-keys",
        "recommended": True,
    },
    "grok": {
        "name": "xAI Grok",
        "description": "Grok Voice Agent API",
        "api_key_env": "XAI_API_KEY",
        "api_key_url": "https://console.x.ai",
        "recommended": False,
    },
    "gemini": {
        "name": "Google Gemini",
        "description": "Gemini Live API (supports vision)",
        "api_key_env": "GOOGLE_API_KEY",
        "api_key_url": "https://aistudio.google.com/apikey",
        "recommended": False,
    },
    "azure": {
        "name": "Azure OpenAI",
        "description": "OpenAI via Azure",
        "api_key_env": "AZURE_OPENAI_API_KEY",
        "api_key_url": "https://portal.azure.com",
        "recommended": False,
    },
    # Future providers (commented out until tested)
    # "aws": {
    #     "name": "AWS Nova Sonic",
    #     "description": "Amazon Nova Sonic",
    #     "api_key_env": "AWS_ACCESS_KEY_ID",
    #     "api_key_url": "https://console.aws.amazon.com",
    #     "recommended": False,
    # },
    # "ultravox": {
    #     "name": "Ultravox",
    #     "description": "Ultravox Realtime",
    #     "api_key_env": "ULTRAVOX_API_KEY",
    #     "api_key_url": "https://ultravox.ai",
    #     "recommended": False,
    # },
}

# OpenAI Realtime voices
OPENAI_VOICES = [
    {"id": "alloy", "name": "Alloy", "description": "Neutral and balanced", "gender": "neutral"},
    {"id": "ash", "name": "Ash", "description": "Warm and engaging", "gender": "male"},
    {"id": "ballad", "name": "Ballad", "description": "Smooth and expressive", "gender": "male", "default": True},
    {"id": "coral", "name": "Coral", "description": "Clear and friendly", "gender": "female"},
    {"id": "echo", "name": "Echo", "description": "Soft and soothing", "gender": "male"},
    {"id": "sage", "name": "Sage", "description": "Wise and thoughtful", "gender": "female"},
    {"id": "shimmer", "name": "Shimmer", "description": "Bright and cheerful", "gender": "female"},
    {"id": "verse", "name": "Verse", "description": "Articulate and clear", "gender": "male"},
]

# xAI Grok voices
GROK_VOICES = [
    {"id": "Charon", "name": "Charon", "description": "Default Grok voice", "gender": "neutral", "default": True},
    {"id": "Clio", "name": "Clio", "description": "Clear and articulate", "gender": "female"},
    {"id": "Puck", "name": "Puck", "description": "Playful and energetic", "gender": "neutral"},
    {"id": "Sage", "name": "Sage", "description": "Calm and wise", "gender": "neutral"},
    {"id": "Vale", "name": "Vale", "description": "Warm and friendly", "gender": "neutral"},
    {"id": "Zephyr", "name": "Zephyr", "description": "Light and airy", "gender": "neutral"},
]

# Gemini voices (placeholder)
GEMINI_VOICES = [
    {"id": "Puck", "name": "Puck", "description": "Default Gemini voice", "gender": "neutral", "default": True},
    {"id": "Charon", "name": "Charon", "description": "Warm and steady", "gender": "neutral"},
    {"id": "Kore", "name": "Kore", "description": "Bright and clear", "gender": "female"},
    {"id": "Fenrir", "name": "Fenrir", "description": "Deep and resonant", "gender": "male"},
    {"id": "Aoede", "name": "Aoede", "description": "Melodic and expressive", "gender": "female"},
]

# Provider to voices mapping
PROVIDER_VOICES = {
    "openai": OPENAI_VOICES,
    "grok": GROK_VOICES,
    "gemini": GEMINI_VOICES,
    "azure": OPENAI_VOICES,  # Azure uses OpenAI voices
}

# Mapping from Realtime-only voices to TTS API equivalents for preview
# ballad and verse are Realtime-only, so we map to similar TTS voices
REALTIME_TO_TTS_VOICE = {
    "ballad": "onyx",   # ballad is smooth male -> onyx is deep male
    "verse": "fable",   # verse is articulate male -> fable is expressive
}

# Piper voices directory (relative to LELAMP_DIR)
def _get_lelamp_dir() -> Path:
    """Get lelamp directory from environment or default."""
    lelamp_dir = os.environ.get("LELAMP_DIR")
    if lelamp_dir:
        return Path(lelamp_dir)
    return Path.home() / "lelampv2"

PIPER_VOICES_DIR = _get_lelamp_dir() / "piper" / "voices"
PIPER_PATH = _get_lelamp_dir() / "piper" / "piper"


# =============================================================================
# Pydantic Models
# =============================================================================

class AIBackendOption(BaseModel):
    """AI backend option."""
    id: str
    name: str
    description: str
    requires: List[str]
    features: List[str]
    recommended: bool = False
    coming_soon: bool = False
    configured: bool = False


class VoiceOption(BaseModel):
    """Voice option for TTS."""
    id: str
    name: str
    description: str
    gender: str = "neutral"
    default: bool = False


class AIBackendConfigRequest(BaseModel):
    """Request to configure AI backend."""
    backend: str
    # Provider for livekit-realtime (openai, grok, gemini, azure)
    provider: Optional[str] = None
    # Provider API key
    api_key: Optional[str] = None
    # Voice setting
    voice: Optional[str] = None
    # Legacy fields (for backwards compatibility)
    openai_key: Optional[str] = None
    openai_voice: Optional[str] = None
    # Local pipeline
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    whisper_model: Optional[str] = None
    piper_voice: Optional[str] = None


class ValidateKeyRequest(BaseModel):
    """Request to validate an API key."""
    key: str


class VoiceTestRequest(BaseModel):
    """Request to test a voice."""
    backend: str
    voice_id: str
    text: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def check_env_keys(required_keys: List[str]) -> dict:
    """Check which required env keys are set."""
    from lelamp.user_data import USER_DATA_DIR

    env_path = USER_DATA_DIR / ".env"
    env_vars = {}

    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if value and value not in ('""', "''"):
                        env_vars[key] = True
        except Exception:
            pass

    result = {}
    for key in required_keys:
        result[key] = key in env_vars

    return result


def get_env_value(key: str) -> Optional[str]:
    """Get a value from .env file."""
    from lelamp.user_data import USER_DATA_DIR

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


def update_env_file(updates: dict):
    """Update .env file with new values."""
    from lelamp.user_data import USER_DATA_DIR

    env_path = USER_DATA_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                existing[key.strip()] = value.strip()

    # Merge updates
    existing.update(updates)

    # Write back
    with open(env_path, "w") as f:
        for key, value in existing.items():
            if value:  # Only write non-empty values
                f.write(f"{key}={value}\n")

    env_path.chmod(0o600)


def get_piper_voices() -> List[dict]:
    """Get list of available Piper voices."""
    voices = []

    if not PIPER_VOICES_DIR.exists():
        return voices

    for voice_file in sorted(PIPER_VOICES_DIR.glob("*.onnx")):
        voice_id = voice_file.name
        voice_name = voice_file.stem.replace("-", " ").replace("_", " ").title()

        # Try to get metadata from JSON
        json_path = voice_file.with_suffix(".onnx.json")
        description = ""
        gender = "neutral"

        if json_path.exists():
            try:
                import json
                meta = json.loads(json_path.read_text())
                # Extract quality from filename
                if "-high" in voice_id:
                    description = "High quality"
                elif "-medium" in voice_id:
                    description = "Medium quality"
                elif "-low" in voice_id:
                    description = "Low quality (fast)"

                # Try to infer gender from common voice names
                name_lower = voice_id.lower()
                if any(n in name_lower for n in ["amy", "kathleen", "kristin", "lessac", "ljspeech"]):
                    gender = "female"
                elif any(n in name_lower for n in ["alan", "ryan", "danny", "joe", "john", "bryce", "kusal", "norman"]):
                    gender = "male"
            except Exception:
                pass

        voices.append({
            "id": voice_id,
            "name": voice_name,
            "description": description,
            "gender": gender,
            "default": voice_id == "ryan-medium.onnx"
        })

    return voices


async def validate_openai_key(api_key: str) -> tuple:
    """
    Validate an OpenAI API key by making a simple API call.

    Returns (is_valid, error_message)
    """
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )

            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Invalid API key"
            elif response.status_code == 429:
                # Rate limited but key is valid
                return True, None
            else:
                return False, f"API error: {response.status_code}"

    except httpx.ConnectError:
        return False, "Could not connect to OpenAI API"
    except httpx.TimeoutException:
        return False, "Connection timed out"
    except Exception as e:
        return False, str(e)


async def generate_piper_preview(voice_id: str, text: str) -> Optional[str]:
    """
    Generate a voice preview using Piper TTS.

    Returns path to generated audio file.
    """
    if not PIPER_PATH.exists():
        return None

    voice_path = PIPER_VOICES_DIR / voice_id
    if not voice_path.exists():
        return None

    # Create temp file for output
    fd, output_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        # Set library path for Piper dependencies
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"{PIPER_PATH.parent}:{env.get('LD_LIBRARY_PATH', '')}"

        # Run Piper to generate audio
        process = await asyncio.create_subprocess_exec(
            str(PIPER_PATH),
            "--model", str(voice_path),
            "--output_file", output_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=text.encode()),
            timeout=30.0
        )

        if process.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            logger.error(f"Piper error: {stderr.decode()}")
            return None

    except asyncio.TimeoutError:
        logger.error("Piper timed out")
        return None
    except Exception as e:
        logger.error(f"Piper error: {e}")
        return None


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/options")
async def get_ai_backend_options():
    """
    Get available AI backend options.

    Returns list of backends with their requirements and configuration status.
    """
    try:
        options = []

        for backend_id, backend_info in AI_BACKENDS.items():
            # Check if required keys are configured
            required = backend_info.get("requires", [])
            env_status = check_env_keys(required)
            configured = all(env_status.values()) if required else True

            options.append(AIBackendOption(
                id=backend_id,
                name=backend_info["name"],
                description=backend_info["description"],
                requires=required,
                features=backend_info.get("features", []),
                recommended=backend_info.get("recommended", False),
                coming_soon=backend_info.get("coming_soon", False),
                configured=configured
            ).model_dump())

        # Get current selection
        config = load_config()
        pipeline_config = config.get("pipeline", {})
        # Support legacy "livekit" type
        current_type = pipeline_config.get("type", "livekit-realtime")
        if current_type == "livekit":
            current_type = "livekit-realtime"
        current_provider = pipeline_config.get("provider", "openai")

        # Build providers list with configuration status
        providers = []
        for provider_id, provider_info in REALTIME_PROVIDERS.items():
            api_key_env = provider_info.get("api_key_env", "")
            env_status = check_env_keys([api_key_env]) if api_key_env else {}
            is_configured = env_status.get(api_key_env, False)

            providers.append({
                "id": provider_id,
                "name": provider_info["name"],
                "description": provider_info["description"],
                "api_key_env": api_key_env,
                "api_key_url": provider_info.get("api_key_url", ""),
                "recommended": provider_info.get("recommended", False),
                "coming_soon": provider_info.get("coming_soon", False),
                "configured": is_configured,
            })

        return {
            "success": True,
            "backends": options,
            "providers": providers,
            "current": current_type,
            "current_provider": current_provider,
        }

    except Exception as e:
        logger.error(f"Error getting AI backends: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/current")
async def get_current_backend():
    """Get currently configured AI backend with voice settings."""
    try:
        config = load_config()
        pipeline_config = config.get("pipeline", {})

        # Support legacy "livekit" type
        current = pipeline_config.get("type", "livekit-realtime")
        if current == "livekit":
            current = "livekit-realtime"

        # Get provider for livekit-realtime
        provider = pipeline_config.get("provider", "openai")

        backend_info = AI_BACKENDS.get(current, AI_BACKENDS.get("livekit-realtime", {}))

        # Determine required keys based on provider
        if current == "livekit-realtime":
            provider_info = REALTIME_PROVIDERS.get(provider, {})
            required = [provider_info.get("api_key_env", "OPENAI_API_KEY")]
        else:
            required = backend_info.get("requires", [])

        env_status = check_env_keys(required)

        # Get current voice setting
        voice = None
        if current in ("livekit-realtime", "livekit"):
            # Try new voice field first, then legacy openai_voice
            voice = pipeline_config.get("voice") or pipeline_config.get("openai_voice", "ballad")
        elif current == "local":
            local_config = pipeline_config.get("local", {})
            voice = local_config.get("voice", "ryan-medium.onnx")

        return {
            "success": True,
            "backend": current,
            "provider": provider if current == "livekit-realtime" else None,
            "name": backend_info.get("name", current),
            "voice": voice,
            "configured": all(env_status.values()) if required else True,
            "missing_keys": [k for k, v in env_status.items() if not v]
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/voices/{backend}")
async def get_voices(backend: str, provider: Optional[str] = None):
    """
    Get available voices for a backend.

    Args:
        backend: "livekit-realtime", "livekit" (legacy), or "local"
        provider: For livekit-realtime, specify provider (openai, grok, gemini)
    """
    try:
        # Get current provider from config if not specified
        config = load_config()
        pipeline_config = config.get("pipeline", {})

        if backend in ("livekit-realtime", "livekit"):
            # Use specified provider or get from config
            active_provider = provider or pipeline_config.get("provider", "openai")
            voices = PROVIDER_VOICES.get(active_provider, OPENAI_VOICES)
        elif backend == "local":
            voices = get_piper_voices()
            active_provider = None
        else:
            return {
                "success": False,
                "error": f"Unknown backend: {backend}"
            }

        # Get current voice from config
        current_voice = None
        if backend in ("livekit-realtime", "livekit"):
            current_voice = pipeline_config.get("voice") or pipeline_config.get("openai_voice", "ballad")
        elif backend == "local":
            local_config = pipeline_config.get("local", {})
            current_voice = local_config.get("voice", "ryan-medium.onnx")

        return {
            "success": True,
            "backend": backend,
            "provider": active_provider,
            "voices": voices,
            "current": current_voice
        }

    except Exception as e:
        logger.error(f"Error getting voices: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/validate-key")
async def validate_api_key(request: ValidateKeyRequest):
    """
    Validate an OpenAI API key.

    Makes a test API call to verify the key works.
    """
    try:
        is_valid, error = await validate_openai_key(request.key)

        return {
            "success": True,
            "valid": is_valid,
            "error": error
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/test-voice")
async def test_voice(request: VoiceTestRequest):
    """
    Generate and play a voice preview on the Pi.

    For local backend, generates audio using Piper and plays it on the device.
    For livekit backend, returns info about the voice (audio preview not available without API call).
    """
    try:
        text = request.text or "Hello! I am your LeLamp, ready to assist you."

        if request.backend == "local":
            # Generate audio using Piper
            audio_path = await generate_piper_preview(request.voice_id, text)

            if audio_path:
                # Play on the Pi's speakers using aplay
                try:
                    import subprocess
                    process = await asyncio.create_subprocess_exec(
                        "aplay", audio_path,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    # Don't wait for completion - let it play in background
                    asyncio.create_task(_cleanup_after_playback(process, audio_path))

                    return {
                        "success": True,
                        "message": "Playing voice preview on device",
                        "voice_id": request.voice_id
                    }
                except Exception as e:
                    logger.error(f"Error playing audio: {e}")
                    # Fallback: try to clean up
                    try:
                        os.unlink(audio_path)
                    except Exception:
                        pass
                    return {
                        "success": False,
                        "error": f"Failed to play audio: {e}"
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to generate audio preview"
                }

        elif request.backend in ("livekit", "livekit-realtime"):
            # Generate preview using OpenAI TTS API
            voice_info = next((v for v in OPENAI_VOICES if v["id"] == request.voice_id), None)

            if not voice_info:
                return {
                    "success": False,
                    "error": f"Unknown voice: {request.voice_id}"
                }

            # Check for API key - try environment first, then .env file
            openai_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not openai_key:
                # Try reading from .env file (key may have been saved but not in env)
                openai_key = get_env_value("OPENAI_API_KEY") or ""
                openai_key = openai_key.strip()
            if not openai_key:
                return {
                    "success": False,
                    "error": "OpenAI API key not configured"
                }

            try:
                import httpx
                import tempfile

                # Map Realtime-only voices to TTS equivalents for preview
                tts_voice = REALTIME_TO_TTS_VOICE.get(request.voice_id, request.voice_id)

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/speech",
                        headers={
                            "Authorization": f"Bearer {openai_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "tts-1",
                            "input": text,
                            "voice": tts_voice,
                            "response_format": "wav",
                        },
                        timeout=30.0
                    )

                    if response.status_code == 200:
                        # Save to temp file and play
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                            f.write(response.content)
                            audio_path = f.name

                        # Play on the Pi's speakers
                        import subprocess
                        process = await asyncio.create_subprocess_exec(
                            "aplay", "-D", "lelamp_playback", audio_path,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        asyncio.create_task(_cleanup_after_playback(process, audio_path))

                        # Note if using substitute voice for preview
                        if tts_voice != request.voice_id:
                            msg = f"Playing similar voice preview ({tts_voice})"
                        else:
                            msg = "Playing voice preview"

                        return {
                            "success": True,
                            "message": msg,
                            "voice_id": request.voice_id
                        }
                    else:
                        error_text = response.text[:200] if response.text else f"Status {response.status_code}"
                        return {
                            "success": False,
                            "error": f"OpenAI API error: {error_text}"
                        }

            except Exception as e:
                logger.error(f"OpenAI TTS error: {e}")
                return {
                    "success": False,
                    "error": f"Failed to generate preview: {str(e)}"
                }

        else:
            return {
                "success": False,
                "error": f"Unknown backend: {request.backend}"
            }

    except Exception as e:
        logger.error(f"Error testing voice: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _cleanup_after_playback(process, audio_path: str):
    """Wait for playback to finish then clean up temp file."""
    try:
        await process.wait()
    except Exception:
        pass
    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass


@router.post("/configure")
async def configure_ai_backend(request: AIBackendConfigRequest):
    """
    Configure the AI backend with voice selection.

    Sets the pipeline type, provider, stores API keys, and configures voice settings.
    """
    try:
        # Normalize backend name (support legacy "livekit")
        backend = request.backend
        if backend == "livekit":
            backend = "livekit-realtime"

        if backend not in AI_BACKENDS:
            return {
                "success": False,
                "error": f"Unknown backend: {backend}"
            }

        backend_info = AI_BACKENDS[backend]
        if backend_info.get("coming_soon"):
            return {
                "success": False,
                "error": f"{backend_info['name']} is coming soon"
            }

        # Prepare env updates
        env_updates = {}

        if backend == "livekit-realtime":
            # Get provider (default to openai)
            provider = request.provider or "openai"

            # Check if provider is coming soon
            provider_info = REALTIME_PROVIDERS.get(provider, {})
            if provider_info.get("coming_soon"):
                return {
                    "success": False,
                    "error": f"{provider_info['name']} provider is coming soon"
                }

            # Handle API key - use new api_key field or legacy openai_key
            api_key = request.api_key or request.openai_key
            if api_key:
                # Validate key for OpenAI (TODO: add validation for other providers)
                if provider == "openai":
                    is_valid, error = await validate_openai_key(api_key)
                    if not is_valid:
                        return {
                            "success": False,
                            "error": f"Invalid API key: {error}"
                        }

                # Store under provider-specific env var
                api_key_env = provider_info.get("api_key_env", "OPENAI_API_KEY")
                env_updates[api_key_env] = api_key

        # Update .env file
        if env_updates:
            update_env_file(env_updates)

        # Update config
        config = load_config()

        config.setdefault("pipeline", {})
        config["pipeline"]["type"] = backend

        if backend == "livekit-realtime":
            # Provider setting
            provider = request.provider or "openai"
            config["pipeline"]["provider"] = provider

            # Voice setting - use new voice field or legacy openai_voice
            voice = request.voice or request.openai_voice
            if voice:
                config["pipeline"]["voice"] = voice
            elif "voice" not in config["pipeline"]:
                # Set default voice for provider
                from lelamp.pipelines.livekit_realtime import DEFAULT_VOICES
                config["pipeline"]["voice"] = DEFAULT_VOICES.get(provider, "ballad")

            # Keep legacy field for backwards compatibility
            config["pipeline"]["openai_voice"] = config["pipeline"]["voice"]

        elif backend == "local":
            config["pipeline"].setdefault("local", {})

            if request.ollama_url:
                config["pipeline"]["local"]["ollama_url"] = request.ollama_url
            if request.ollama_model:
                config["pipeline"]["local"]["ollama_model"] = request.ollama_model
            if request.whisper_model:
                config["pipeline"]["local"]["whisper_model"] = request.whisper_model
            if request.piper_voice:
                config["pipeline"]["local"]["voice"] = request.piper_voice

        # Enable agent
        config.setdefault("agent", {})
        config["agent"]["enabled"] = True

        # Mark setup step complete
        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"]["steps_completed"]["ai_backend"] = True
        config["setup"]["steps_completed"]["environment"] = True  # Also mark old step

        save_config(config)

        # Build response message
        if backend == "livekit-realtime":
            provider_name = REALTIME_PROVIDERS.get(provider, {}).get("name", provider)
            message = f"AI backend set to LiveKit Realtime with {provider_name}"
        else:
            message = f"AI backend set to {backend_info['name']}"

        return {
            "success": True,
            "backend": backend,
            "provider": request.provider if backend == "livekit-realtime" else None,
            "message": message,
            "restart_required": True
        }

    except Exception as e:
        logger.error(f"Error configuring AI backend: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/check-keys")
async def check_api_keys():
    """Check which API keys are configured."""
    try:
        all_required_keys = set()
        for backend in AI_BACKENDS.values():
            all_required_keys.update(backend.get("requires", []))

        env_status = check_env_keys(list(all_required_keys))

        return {
            "success": True,
            "keys": env_status
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/local-config")
async def get_local_config():
    """Get local pipeline configuration options."""
    try:
        config = load_config()
        local_config = config.get("pipeline", {}).get("local", {})

        # Check if Ollama is available
        ollama_available = False
        ollama_models = []
        ollama_url = local_config.get("ollama_url", "http://localhost:11434")

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ollama_url}/api/tags", timeout=5.0)
                if response.status_code == 200:
                    ollama_available = True
                    data = response.json()
                    ollama_models = [m["name"] for m in data.get("models", [])]
        except Exception:
            pass

        # Check if Piper is available
        piper_available = PIPER_PATH.exists()
        piper_voices = get_piper_voices() if piper_available else []

        return {
            "success": True,
            "ollama": {
                "available": ollama_available,
                "url": ollama_url,
                "models": ollama_models,
                "current_model": local_config.get("ollama_model", "llama3.2:3b")
            },
            "whisper": {
                "models": ["tiny", "base", "small"],
                "current_model": local_config.get("whisper_model", "tiny")
            },
            "piper": {
                "available": piper_available,
                "voices": piper_voices,
                "current_voice": local_config.get("voice", "ryan-medium.onnx")
            }
        }

    except Exception as e:
        logger.error(f"Error getting local config: {e}")
        return {
            "success": False,
            "error": str(e)
        }
