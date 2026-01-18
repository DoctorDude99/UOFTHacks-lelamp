"""
Audio setup API endpoints.

Provides endpoints for testing and configuring audio hardware:
- Speaker test with volume control
- Microphone test with live monitoring and waveform visualization
- Volume level adjustment
"""

import asyncio
import json
import logging
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from api.deps import load_config, save_config

router = APIRouter()
logger = logging.getLogger(__name__)

# Audio monitoring state (global for this module)
_monitoring_active = False
_monitoring_thread: Optional[threading.Thread] = None
_monitoring_stop_event = threading.Event()

# Speaker test state (for non-blocking playback)
_speaker_test_process: Optional[subprocess.Popen] = None


# =============================================================================
# Pydantic Models
# =============================================================================

class VolumeRequest(BaseModel):
    """Request to set volume levels."""
    speaker_volume: Optional[int] = None
    microphone_volume: Optional[int] = None


class AudioDevice(BaseModel):
    """Audio device info."""
    name: str
    card_index: int
    device_type: str  # "playback" or "capture"


# =============================================================================
# Helper Functions
# =============================================================================

def get_audio_devices() -> Dict[str, List[AudioDevice]]:
    """Get available audio devices."""
    devices = {"playback": [], "capture": []}

    try:
        # Get playback devices
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("card"):
                    # Parse: "card 0: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM..."
                    try:
                        parts = line.split(":")
                        card_num = int(parts[0].split()[1])
                        name = parts[1].split("[")[1].split("]")[0] if "[" in parts[1] else parts[1].strip()
                        devices["playback"].append(AudioDevice(
                            name=name,
                            card_index=card_num,
                            device_type="playback"
                        ))
                    except Exception:
                        pass

        # Get capture devices
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("card"):
                    try:
                        parts = line.split(":")
                        card_num = int(parts[0].split()[1])
                        name = parts[1].split("[")[1].split("]")[0] if "[" in parts[1] else parts[1].strip()
                        devices["capture"].append(AudioDevice(
                            name=name,
                            card_index=card_num,
                            device_type="capture"
                        ))
                    except Exception:
                        pass

    except Exception as e:
        logger.error(f"Error getting audio devices: {e}")

    return devices


def set_volume(volume_type: str, volume_percent: int) -> bool:
    """
    Set volume using amixer.

    Args:
        volume_type: "speaker" or "microphone"
        volume_percent: Volume level 0-100

    Returns:
        True if successful
    """
    volume_percent = max(0, min(100, volume_percent))

    # Use appropriate card based on volume type
    # Speaker: Device (GeneralPlus USB Audio)
    # Microphone: InnomakerU20CAM (camera with mic)
    if volume_type == "speaker":
        cards_to_try = ["Device", None]
        controls = ["Speaker", "Master", "PCM", "Headphone"]
    else:  # microphone
        cards_to_try = ["InnomakerU20CAM", "Device", None]
        controls = ["Mic", "Capture", "ADC", "ADC PCM"]

    # Try each card/control combination until one works
    for card in cards_to_try:
        for control in controls:
            try:
                cmd = ["amixer"]
                if card:
                    cmd.extend(["-c", card])
                cmd.extend(["sset", control, f"{volume_percent}%"])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=2  # Reduced timeout for faster response
                )
                if result.returncode == 0:
                    return True  # Exit immediately on success
            except Exception:
                pass

    return False


def get_current_volume(volume_type: str) -> Optional[int]:
    """Get current volume level."""
    import re

    # Use appropriate card based on volume type
    if volume_type == "speaker":
        cards_to_try = ["Device", None]
        controls = ["Speaker", "Master", "PCM"]
    else:  # microphone
        cards_to_try = ["InnomakerU20CAM", "Device", None]
        controls = ["Mic", "Capture", "ADC"]

    for card in cards_to_try:
        for control in controls:
            try:
                cmd = ["amixer"]
                if card:
                    cmd.extend(["-c", card])
                cmd.extend(["sget", control])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    # Parse output for percentage
                    for line in result.stdout.splitlines():
                        if "%" in line:
                            match = re.search(r'\[(\d+)%\]', line)
                            if match:
                                return int(match.group(1))
            except Exception:
                pass

    return None


def play_test_sound(blocking: bool = True) -> bool:
    """
    Play speaker test sound.

    Args:
        blocking: If True, wait for sound to finish. If False, return immediately.

    Returns:
        True if playback started successfully
    """
    global _speaker_test_process

    test_sound = Path("/home/administrator/lelamp_v3_runtime/assets/setup/LeLamp-SpeakerTest.wav")

    if not test_sound.exists():
        # Fallback to any available test sound
        alternatives = [
            Path("/home/administrator/lelamp_v3_runtime/assets/AudioFX/Effects/Scifi-PositiveDigitization.wav"),
            Path("/home/administrator/lelamp_v3_runtime/assets/Theme/Lelamp/audio/Notify.wav"),
        ]
        for alt in alternatives:
            if alt.exists():
                test_sound = alt
                break

    if not test_sound.exists():
        logger.error("No test sound file found")
        return False

    try:
        # Stop any existing playback first
        stop_test_sound()

        if blocking:
            result = subprocess.run(
                ["aplay", "-D", "lelamp_playback", str(test_sound)],
                capture_output=True,
                timeout=15  # Test sound is ~11.5 seconds
            )
            return result.returncode == 0
        else:
            # Non-blocking: start process and return immediately
            _speaker_test_process = subprocess.Popen(
                ["aplay", "-D", "lelamp_playback", str(test_sound)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        logger.error(f"Error playing test sound: {e}")
        return False


def stop_test_sound() -> bool:
    """Stop any currently playing test sound."""
    global _speaker_test_process

    if _speaker_test_process is not None:
        try:
            _speaker_test_process.terminate()
            _speaker_test_process.wait(timeout=1)
        except Exception:
            try:
                _speaker_test_process.kill()
            except Exception:
                pass
        _speaker_test_process = None
    return True


def is_test_sound_playing() -> bool:
    """Check if test sound is currently playing."""
    global _speaker_test_process

    if _speaker_test_process is None:
        return False

    # Check if process is still running
    poll_result = _speaker_test_process.poll()
    if poll_result is not None:
        # Process has finished
        _speaker_test_process = None
        return False
    return True


def start_mic_monitoring() -> bool:
    """
    Start live microphone monitoring (passthrough to speakers).

    Uses sounddevice to create a real-time audio stream.
    """
    global _monitoring_active, _monitoring_thread, _monitoring_stop_event

    if _monitoring_active:
        return True  # Already running

    _monitoring_stop_event.clear()

    def monitor_thread():
        global _monitoring_active
        try:
            import sounddevice as sd
            import numpy as np

            def callback(indata, outdata, frames, time, status):
                if status:
                    logger.debug(f"Audio status: {status}")
                # Direct passthrough with slight gain
                outdata[:] = indata * 1.0

            _monitoring_active = True
            logger.info("Starting mic monitoring")

            with sd.Stream(
                channels=1,
                callback=callback,
                samplerate=24000,  # Standardized sample rate
                blocksize=512,
                latency='low'
            ):
                # Keep running until stop event
                while not _monitoring_stop_event.is_set():
                    _monitoring_stop_event.wait(0.1)

        except ImportError:
            logger.error("sounddevice not installed")
        except Exception as e:
            logger.error(f"Error in mic monitoring: {e}")
        finally:
            _monitoring_active = False
            logger.info("Mic monitoring stopped")

    _monitoring_thread = threading.Thread(target=monitor_thread, daemon=True)
    _monitoring_thread.start()

    # Wait a moment for thread to start
    import time
    time.sleep(0.2)

    return _monitoring_active


def stop_mic_monitoring() -> bool:
    """Stop live microphone monitoring."""
    global _monitoring_active, _monitoring_thread, _monitoring_stop_event

    if not _monitoring_active:
        return True  # Already stopped

    _monitoring_stop_event.set()

    if _monitoring_thread:
        _monitoring_thread.join(timeout=2.0)
        _monitoring_thread = None

    _monitoring_active = False
    return True


def record_and_playback(duration: float = 3.0) -> bool:
    """
    Record from microphone and play back through speakers.

    Args:
        duration: Recording duration in seconds

    Returns:
        True if successful
    """
    try:
        import sounddevice as sd
        import numpy as np

        sample_rate = 24000  # Standardized sample rate

        # Record
        logger.info(f"Recording {duration}s...")
        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype='int16'
        )
        sd.wait()

        # Play back
        logger.info("Playing back recording...")
        sd.play(recording, samplerate=sample_rate)
        sd.wait()

        return True

    except ImportError:
        logger.error("sounddevice not installed")
        return False
    except Exception as e:
        logger.error(f"Error in record/playback: {e}")
        return False


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/status")
async def get_audio_status():
    """
    Check audio hardware availability.

    Returns whether audio hardware is available and ready for setup.
    """
    try:
        devices = get_audio_devices()

        has_playback = len(devices["playback"]) > 0
        has_capture = len(devices["capture"]) > 0

        # Filter out HDMI-only playback (not useful for setup)
        usb_playback = [d for d in devices["playback"]
                       if "hdmi" not in d.name.lower()]

        return {
            "success": True,
            "available": has_playback and has_capture,
            "has_speaker": has_playback,
            "has_microphone": has_capture,
            "has_usb_audio": len(usb_playback) > 0,
            "playback_count": len(devices["playback"]),
            "capture_count": len(devices["capture"]),
        }

    except Exception as e:
        logger.error(f"Error checking audio status: {e}")
        return {
            "success": False,
            "available": False,
            "error": str(e)
        }


@router.get("/devices")
async def get_audio_devices_endpoint():
    """Get list of available audio devices."""
    try:
        devices = get_audio_devices()
        return {
            "success": True,
            "playback": [d.model_dump() for d in devices["playback"]],
            "capture": [d.model_dump() for d in devices["capture"]],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/test-speaker")
async def test_speaker():
    """
    Play a test sound through speakers (non-blocking).

    Returns immediately after starting playback so volume can be adjusted
    while the sound is playing.
    """
    try:
        success = play_test_sound(blocking=False)
        return {
            "success": success,
            "playing": success,
            "message": "Test sound started" if success else "Failed to play test sound"
        }
    except Exception as e:
        return {"success": False, "playing": False, "error": str(e)}


@router.post("/test-speaker/stop")
async def stop_speaker_test():
    """Stop the currently playing test sound."""
    try:
        stop_test_sound()
        return {"success": True, "message": "Stopped"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/test-speaker/status")
async def get_speaker_test_status():
    """Check if test sound is currently playing."""
    return {
        "success": True,
        "playing": is_test_sound_playing()
    }


@router.post("/test-mic")
async def test_microphone():
    """
    Record from microphone and play back through speakers.

    Records for 3 seconds, then plays back the recording.
    """
    try:
        success = record_and_playback(3.0)
        return {
            "success": success,
            "message": "Recorded and played back" if success else "Failed to record/playback"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/monitor/start")
async def start_monitoring():
    """
    Start live microphone monitoring.

    Passes microphone input directly to speakers so user can hear themselves.
    """
    try:
        success = start_mic_monitoring()
        return {
            "success": success,
            "monitoring": _monitoring_active,
            "message": "Monitoring started" if success else "Failed to start monitoring"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/monitor/stop")
async def stop_monitoring():
    """Stop live microphone monitoring."""
    try:
        success = stop_mic_monitoring()
        return {
            "success": success,
            "monitoring": _monitoring_active,
            "message": "Monitoring stopped" if success else "Failed to stop monitoring"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/monitor/status")
async def get_monitoring_status():
    """Get current monitoring status."""
    return {
        "success": True,
        "monitoring": _monitoring_active
    }


@router.get("/mic-level")
async def get_mic_level():
    """
    Get current microphone input level.

    Returns level as percentage (0-100) based on RMS of a short sample.
    """
    try:
        import sounddevice as sd
        import numpy as np

        # Record a very short sample (50ms)
        sample_rate = 24000  # Standardized sample rate
        duration = 0.05  # 50ms
        samples = int(sample_rate * duration)

        recording = sd.rec(samples, samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()

        # Calculate RMS level
        audio_data = recording.flatten().astype(np.float32)
        rms = np.sqrt(np.mean(audio_data ** 2))

        # Normalize to 0-100 (int16 max is 32767)
        # Use a lower reference for more sensitivity
        level = min(100, int((rms / 10000) * 100))

        return {
            "success": True,
            "level": level
        }

    except ImportError:
        return {"success": False, "level": 0, "error": "sounddevice not installed"}
    except Exception as e:
        logger.error(f"Error getting mic level: {e}")
        return {"success": False, "level": 0, "error": str(e)}


@router.get("/volume")
async def get_volumes():
    """Get current volume levels."""
    try:
        config = load_config()

        # Try to get live values, fall back to config
        speaker_vol = get_current_volume("speaker")
        mic_vol = get_current_volume("microphone")

        return {
            "success": True,
            "speaker_volume": speaker_vol if speaker_vol is not None else config.get("volume", 50),
            "microphone_volume": mic_vol if mic_vol is not None else config.get("microphone_volume", 50),
            "speaker_live": speaker_vol is not None,
            "microphone_live": mic_vol is not None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/volume")
async def set_volumes(request: VolumeRequest):
    """
    Set speaker and/or microphone volume.

    Updates both the system volume (via amixer) and config file.
    """
    try:
        config = load_config()
        results = {}

        if request.speaker_volume is not None:
            vol = max(0, min(100, request.speaker_volume))
            success = set_volume("speaker", vol)
            config["volume"] = vol
            results["speaker"] = {"success": success, "volume": vol}

        if request.microphone_volume is not None:
            vol = max(0, min(100, request.microphone_volume))
            success = set_volume("microphone", vol)
            config["microphone_volume"] = vol
            results["microphone"] = {"success": success, "volume": vol}

        save_config(config)

        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/skip")
async def skip_audio_setup():
    """
    Skip audio setup step.

    Marks the step as complete without testing.
    """
    try:
        config = load_config()
        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"]["steps_completed"]["audio"] = True
        save_config(config)

        return {
            "success": True,
            "message": "Audio setup skipped"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/complete")
async def complete_audio_setup():
    """
    Mark audio setup as complete.

    Called after successful speaker and mic tests.
    """
    try:
        config = load_config()
        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"]["steps_completed"]["audio"] = True
        config["setup"].setdefault("audio", {})
        config["setup"]["audio"]["tested"] = True
        save_config(config)

        return {
            "success": True,
            "message": "Audio setup completed"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Microphone Calibration
# =============================================================================

# Room presets for mic calibration
MIC_PRESETS = {
    "quiet": {"target_low": 70, "target_high": 90, "description": "Quiet room (library, bedroom)"},
    "normal": {"target_low": 65, "target_high": 85, "description": "Normal room (office, living room)"},
    "loud": {"target_low": 55, "target_high": 75, "description": "Loud environment (cafe, outdoors)"},
}

# Calibration state
_calibration_active = False
_calibration_data = {
    "samples": [],
    "adjustments": 0,
    "current_volume": 50,
    "status": "idle",
    "preset": "normal",
}


@router.get("/calibration/presets")
async def get_mic_presets():
    """Get available microphone calibration presets."""
    return {
        "success": True,
        "presets": MIC_PRESETS,
        "current": _calibration_data.get("preset", "normal"),
    }


@router.post("/calibration/start")
async def start_mic_calibration(preset: str = "normal"):
    """
    Start microphone auto-calibration.

    Args:
        preset: Room type preset (quiet, normal, loud)

    The calibration will:
    1. Monitor microphone levels
    2. Adjust volume to reach optimal range for the preset
    3. Return when optimal level achieved or max adjustments reached
    """
    global _calibration_active, _calibration_data

    if _calibration_active:
        return {"success": False, "error": "Calibration already in progress"}

    if preset not in MIC_PRESETS:
        preset = "normal"

    config = load_config()
    current_vol = config.get("microphone_volume", 50)

    _calibration_active = True
    _calibration_data = {
        "samples": [],
        "adjustments": 0,
        "current_volume": current_vol,
        "status": "listening",
        "preset": preset,
        "target_low": MIC_PRESETS[preset]["target_low"],
        "target_high": MIC_PRESETS[preset]["target_high"],
    }

    return {
        "success": True,
        "message": "Calibration started",
        "preset": preset,
        "target_range": [MIC_PRESETS[preset]["target_low"], MIC_PRESETS[preset]["target_high"]],
    }


@router.post("/calibration/sample")
async def submit_calibration_sample(level: int):
    """
    Submit a mic level sample for calibration.

    Called by the frontend during calibration to feed level data.
    Returns adjustment instructions.
    """
    global _calibration_active, _calibration_data

    if not _calibration_active:
        return {"success": False, "error": "No calibration in progress"}

    NOISE_FLOOR = 3
    target_low = _calibration_data["target_low"]
    target_high = _calibration_data["target_high"]

    # Only track levels above noise floor
    if level > NOISE_FLOOR:
        _calibration_data["samples"].append(level)

    # Keep last 20 samples
    if len(_calibration_data["samples"]) > 20:
        _calibration_data["samples"].pop(0)

    samples = _calibration_data["samples"]

    # Need enough samples to make decisions
    if len(samples) < 6:
        _calibration_data["status"] = f"Collecting samples ({len(samples)}/6)"
        return {
            "success": True,
            "status": _calibration_data["status"],
            "action": "wait",
            "volume": _calibration_data["current_volume"],
        }

    # Calculate weighted average (recent samples weighted more)
    weights = [1 + (i / len(samples)) for i in range(len(samples))]
    weighted_sum = sum(s * w for s, w in zip(samples, weights))
    total_weight = sum(weights)
    avg_level = weighted_sum / total_weight
    peak_level = max(samples)

    # Check if we're in optimal range
    if avg_level >= target_low and avg_level <= target_high and peak_level < 95:
        _calibration_data["status"] = f"Optimal! Avg: {avg_level:.0f}%, Peak: {peak_level:.0f}%"
        return {
            "success": True,
            "status": _calibration_data["status"],
            "action": "complete",
            "volume": _calibration_data["current_volume"],
            "avg_level": round(avg_level),
            "peak_level": round(peak_level),
        }

    # Determine adjustment
    action = "wait"
    new_volume = _calibration_data["current_volume"]

    if peak_level >= 95:
        # Clipping - reduce volume
        new_volume = max(10, _calibration_data["current_volume"] - 10)
        action = "decrease"
        _calibration_data["status"] = f"Clipping detected ({peak_level:.0f}%) - reducing"
    elif avg_level < target_low:
        # Too quiet - increase volume
        increment = 10 if avg_level < 30 else 5
        new_volume = min(100, _calibration_data["current_volume"] + increment)
        action = "increase"
        _calibration_data["status"] = f"Too quiet ({avg_level:.0f}%) - increasing"
    elif avg_level > target_high:
        # Too loud - decrease volume
        decrement = 10 if avg_level > 95 else 5
        new_volume = max(10, _calibration_data["current_volume"] - decrement)
        action = "decrease"
        _calibration_data["status"] = f"Too loud ({avg_level:.0f}%) - reducing"

    if new_volume != _calibration_data["current_volume"]:
        # Apply volume change
        set_volume("microphone", new_volume)
        _calibration_data["current_volume"] = new_volume
        _calibration_data["adjustments"] += 1
        _calibration_data["samples"] = []  # Reset after adjustment

        # Update config
        config = load_config()
        config["microphone_volume"] = new_volume
        save_config(config)

    # Check if we've made too many adjustments
    if _calibration_data["adjustments"] > 15:
        _calibration_data["status"] = f"Calibration complete at {new_volume}%"
        return {
            "success": True,
            "status": _calibration_data["status"],
            "action": "complete",
            "volume": new_volume,
            "avg_level": round(avg_level),
        }

    return {
        "success": True,
        "status": _calibration_data["status"],
        "action": action,
        "volume": new_volume,
        "avg_level": round(avg_level),
        "peak_level": round(peak_level),
        "adjustments": _calibration_data["adjustments"],
    }


@router.post("/calibration/stop")
async def stop_mic_calibration():
    """Stop microphone calibration."""
    global _calibration_active, _calibration_data

    _calibration_active = False
    result_volume = _calibration_data.get("current_volume", 50)
    _calibration_data = {
        "samples": [],
        "adjustments": 0,
        "current_volume": result_volume,
        "status": "idle",
        "preset": "normal",
    }

    return {
        "success": True,
        "message": "Calibration stopped",
        "final_volume": result_volume,
    }


@router.get("/calibration/status")
async def get_calibration_status():
    """Get current calibration status."""
    return {
        "success": True,
        "active": _calibration_active,
        "status": _calibration_data.get("status", "idle"),
        "volume": _calibration_data.get("current_volume", 50),
        "adjustments": _calibration_data.get("adjustments", 0),
        "preset": _calibration_data.get("preset", "normal"),
    }


# =============================================================================
# WebSocket for Real-time Audio Waveform
# =============================================================================

@router.websocket("/waveform")
async def audio_waveform_ws(websocket: WebSocket):
    """
    WebSocket endpoint for real-time microphone waveform visualization.

    Streams audio samples at ~30fps for smooth waveform rendering.
    Each message contains:
    - samples: array of normalized audio samples (-1 to 1)
    - rms: current RMS level (0-100)
    - peak: peak level in this chunk (0-100)
    """
    await websocket.accept()
    logger.info("Audio waveform WebSocket connected")

    stream = None
    stop_event = threading.Event()
    audio_queue = asyncio.Queue(maxsize=10)

    def audio_callback(indata, frames, time_info, status):
        """Sounddevice callback - runs in separate thread."""
        if status:
            logger.debug(f"Audio callback status: {status}")
        if stop_event.is_set():
            return

        try:
            import numpy as np
            # Convert to float and normalize
            samples = indata[:, 0].astype(np.float32)

            # Downsample to ~128 points for visualization
            if len(samples) > 128:
                # Take evenly spaced samples
                indices = np.linspace(0, len(samples) - 1, 128, dtype=int)
                samples = samples[indices]

            # Normalize to -1 to 1 range
            samples = samples / 32768.0

            # Calculate RMS and peak
            rms = np.sqrt(np.mean(samples ** 2))
            peak = np.max(np.abs(samples))

            # Scale to 0-100 for display
            rms_percent = min(100, int(rms * 300))  # Scale up for visibility
            peak_percent = min(100, int(peak * 150))

            # Put in queue (non-blocking)
            try:
                audio_queue.put_nowait({
                    "samples": samples.tolist(),
                    "rms": rms_percent,
                    "peak": peak_percent,
                })
            except asyncio.QueueFull:
                pass  # Drop frame if queue is full

        except Exception as e:
            logger.error(f"Error in audio callback: {e}")

    try:
        import sounddevice as sd
        import numpy as np

        # Start audio stream
        stream = sd.InputStream(
            samplerate=24000,  # Standardized sample rate
            channels=1,
            dtype='int16',
            blocksize=800,  # ~33ms chunks at 24kHz = ~30fps
            callback=audio_callback,
        )
        stream.start()
        logger.info("Audio waveform stream started")

        # Stream data to WebSocket
        while True:
            try:
                # Wait for audio data with timeout
                data = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                try:
                    await websocket.send_json(data)
                except WebSocketDisconnect:
                    logger.debug("WebSocket disconnected during send")
                    break
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                try:
                    await websocket.send_json({"heartbeat": True})
                except WebSocketDisconnect:
                    logger.debug("WebSocket disconnected during heartbeat")
                    break

    except ImportError as e:
        logger.error(f"sounddevice not installed: {e}")
        try:
            await websocket.send_json({"error": "sounddevice not installed"})
        except Exception:
            pass
    except Exception as e:
        import traceback
        error_name = type(e).__name__
        error_msg = str(e) or error_name
        logger.error(f"Error in waveform WebSocket: {error_name}: {error_msg}\n{traceback.format_exc()}")
        try:
            await websocket.send_json({"error": f"{error_name}: {error_msg}"})
        except Exception:
            pass
    finally:
        stop_event.set()
        if stream:
            stream.stop()
            stream.close()
        logger.info("Audio waveform stream closed")


# =============================================================================
# Microphone Service Status (Runtime VAD/AEC)
# =============================================================================

@router.get("/microphone-service/status")
async def get_microphone_service_status():
    """
    Get status of the microphone service (VAD, gating, echo cancellation).

    Returns current state for debugging audio pipeline issues.
    """
    try:
        import lelamp.globals as g

        if g.microphone_service is None:
            # Try AudioRouter as fallback (used when audio_routing_enabled)
            if g.audio_router is not None:
                stats = g.audio_router.get_stats()
                return {
                    "success": True,
                    "available": True,
                    "source": "audio_router",
                    "running": stats.get("running", False),
                    "gate_closed": stats.get("gate_closed", False),
                    "current_rms": stats.get("current_rms", 0.0),
                    "vad_available": False,  # AudioRouter doesn't have VAD
                    "is_speech": False,
                    "gate_ratio": stats.get("gate_ratio", 0.0),
                }
            return {
                "success": True,
                "available": False,
                "message": "Microphone service not initialized"
            }

        status = g.microphone_service.get_status()
        return {
            "success": True,
            "available": True,
            **status
        }
    except Exception as e:
        logger.error(f"Error getting microphone service status: {e}")
        return {"success": False, "error": str(e)}


@router.post("/microphone-service/vad-threshold")
async def set_microphone_vad_threshold(threshold: float):
    """
    Set VAD (Voice Activity Detection) threshold.

    Args:
        threshold: VAD threshold 0.0-1.0 (higher = needs louder speech)
    """
    try:
        import lelamp.globals as g

        if g.microphone_service is None:
            return {"success": False, "error": "Microphone service not available"}

        g.microphone_service.set_vad_threshold(threshold)
        return {
            "success": True,
            "threshold": threshold,
            "message": f"VAD threshold set to {threshold}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/microphone-service/gate")
async def control_microphone_gate(action: str):
    """
    Manually control the microphone gate.

    Args:
        action: "open" or "close"
    """
    try:
        import lelamp.globals as g

        if g.microphone_service is None:
            # Try AudioRouter as fallback
            if g.audio_router is not None:
                if action == "open":
                    g.audio_router.set_gate_enabled(False)  # Disable gating = always open
                    return {"success": True, "gate_closed": False, "message": "Gate opened (AudioRouter)"}
                elif action == "close":
                    g.audio_router.set_gate_enabled(True)  # Enable gating
                    return {"success": True, "gate_closed": True, "message": "Gate enabled (AudioRouter)"}
            return {"success": False, "error": "Microphone service not available"}

        if action == "open":
            g.microphone_service.force_gate_open()
            return {"success": True, "gate_closed": False, "message": "Gate opened"}
        elif action == "close":
            g.microphone_service.force_gate_close()
            return {"success": True, "gate_closed": True, "message": "Gate closed"}
        else:
            return {"success": False, "error": f"Unknown action: {action}. Use 'open' or 'close'"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/microphone-service/barge-in-threshold")
async def set_barge_in_threshold(threshold: float):
    """
    Set barge-in RMS threshold.

    Args:
        threshold: RMS threshold for barge-in detection (0.0-1.0)
    """
    try:
        import lelamp.globals as g

        if g.microphone_service is None:
            return {"success": False, "error": "Microphone service not available"}

        g.microphone_service.set_barge_in_threshold(threshold)
        return {
            "success": True,
            "threshold": threshold,
            "message": f"Barge-in threshold set to {threshold}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/microphone-service/gate-release-time")
async def set_gate_release_time(seconds: float):
    """
    Set gate release delay time.

    Args:
        seconds: Seconds to wait after playback stops before ungating mic
    """
    try:
        import lelamp.globals as g

        if g.microphone_service is None:
            # Try AudioRouter as fallback
            if g.audio_router is not None:
                g.audio_router.set_gate_release_delay(seconds)
                return {
                    "success": True,
                    "gate_release_time": seconds,
                    "message": f"Gate release time set to {seconds}s (AudioRouter)"
                }
            return {"success": False, "error": "Microphone service not available"}

        g.microphone_service.set_gate_release_time(seconds)
        return {
            "success": True,
            "gate_release_time": seconds,
            "message": f"Gate release time set to {seconds}s"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/microphone-service/debug-logging")
async def set_debug_logging(enabled: bool):
    """
    Enable/disable verbose debug logging for microphone service.

    Args:
        enabled: True to enable debug logging
    """
    try:
        import lelamp.globals as g

        if g.microphone_service is None:
            return {"success": False, "error": "Microphone service not available"}

        g.microphone_service._debug_logging = enabled
        return {
            "success": True,
            "debug_logging": enabled,
            "message": f"Debug logging {'enabled' if enabled else 'disabled'}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
