"""
Global variables and services for LeLamp

This module provides access to global configuration and services without
triggering re-import of the main module (which would fail due to signal handlers).
"""

import subprocess
import yaml
from pathlib import Path

# Import user data management
from lelamp.user_data import (
    get_config_path,
    get_env_path,
    init_user_data,
    USER_DATA_DIR,
)

# Global configuration
CONFIG = None
CONFIG_PATH = None  # Set dynamically by load_config()

# Global services
alarm_service = None
animation_service = None
rgb_service = None
vision_service = None
ollama_vision_service = None  # Ollama-based scene analysis
wake_service = None
workflow_service = None
audio_service = None
microphone_service = None  # Microphone input processing with VAD/AEC
audio_router = None  # Routes processed audio through loopback to LiveKit
theme_service = None
spotify_service = None  # Spotify integration
agent_session_global = None
livekit_room = None  # LiveKit room reference for disconnect/reconnect
livekit_ctx = None   # JobContext for reconnection
metrics_service = None
datacollection_service = None  # Telemetry data collection service
lelamp_agent = None  # Main agent instance
livekit_service = None  # LiveKit Cloud connection manager

# Global scene context (for quick access)
current_scene_context = None

# Calibration state (for post-assembly setup)
calibration_required = False  # Set to True if calibration file missing
calibration_path = None       # Path to calibration file
calibration_in_progress = False  # True during active calibration

# System notifications (displayed in WebUI as banners)
# Each notification: {"id": str, "type": "info"|"warning"|"error"|"success", "message": str, "timestamp": float, "dismissed": bool}
system_notifications = []


def add_notification(message: str, notification_type: str = "info", notification_id: str = None):
    """
    Add a system notification to be displayed in the WebUI.

    Args:
        message: Notification message text
        notification_type: "info", "warning", "error", or "success"
        notification_id: Optional unique ID (auto-generated if not provided)
    """
    import time
    import uuid

    notification = {
        "id": notification_id or str(uuid.uuid4())[:8],
        "type": notification_type,
        "message": message,
        "timestamp": time.time(),
        "dismissed": False,
    }
    system_notifications.append(notification)
    return notification


def get_notifications(include_dismissed: bool = False):
    """Get all system notifications."""
    if include_dismissed:
        return system_notifications
    return [n for n in system_notifications if not n.get("dismissed")]


def dismiss_notification(notification_id: str):
    """Dismiss a notification by ID."""
    for n in system_notifications:
        if n["id"] == notification_id:
            n["dismissed"] = True
            return True
    return False


def clear_notifications():
    """Clear all notifications."""
    global system_notifications
    system_notifications = []


def load_config():
    """Load configuration from YAML file.

    Always uses ~/.lelamp/config.yaml (no repo fallback).
    If file doesn't exist, copies from system/config.example.yaml template.
    """
    global CONFIG, CONFIG_PATH
    import shutil

    # Initialize user data directory (creates ~/.lelamp/ structure, migrates files)
    init_user_data()

    # Get config path (prefers ~/.lelamp/config.yaml)
    config_path = get_config_path()
    CONFIG_PATH = str(config_path)

    # If config doesn't exist anywhere, copy from example
    if not config_path.exists():
        example_path = Path(__file__).parent.parent / "system" / "config.example.yaml"
        if example_path.exists():
            shutil.copy(example_path, config_path)
            print(f"Created {config_path} from example template")
        else:
            raise FileNotFoundError(
                f"Configuration file not found at {config_path} and no example template found at {example_path}"
            )

    with open(config_path, "r") as f:
        CONFIG = yaml.safe_load(f)

    print(f"Loaded config from: {config_path}")
    return CONFIG


def save_config(config):
    """Save configuration to YAML file (always saves to user directory)"""
    global CONFIG, CONFIG_PATH

    # Always save to user directory
    from lelamp.user_data import USER_CONFIG_FILE, ensure_user_data_dir
    ensure_user_data_dir()

    CONFIG = config
    save_path = USER_CONFIG_FILE
    CONFIG_PATH = str(save_path)

    with open(save_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Saved config to: {save_path}")


# Initialize config on module load
load_config()


# =============================================================================
# Device Detection
# =============================================================================

def detect_usb_camera() -> bool:
    """
    Detect if the USB camera (InnomakerU20CAM) is connected.

    This camera provides both video and the microphone input.
    When unplugged, both vision and audio capture will fail.

    Returns:
        True if the camera is detected, False otherwise
    """
    try:
        # Check if ALSA card exists
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if "InnomakerU20CAM" in result.stdout:
            return True

        # Also check /proc/asound for the card
        asound_path = Path("/proc/asound/InnomakerU20CAM")
        if asound_path.exists():
            return True

        return False
    except Exception:
        return False


def detect_usb_camera_video() -> bool:
    """
    Detect if the USB camera video device exists.

    Returns:
        True if /dev/usbcam exists (camera video is available)
    """
    return Path("/dev/usbcam").exists()


def auto_detect_hardware() -> dict:
    """
    Auto-detect hardware and update config accordingly.

    Checks for USB camera presence and updates vision.enabled.
    This allows the system to gracefully handle missing hardware.

    Returns:
        dict with detection results: {camera_audio: bool, camera_video: bool, updated_config: bool}
    """
    global CONFIG

    camera_audio = detect_usb_camera()
    camera_video = detect_usb_camera_video()
    updated = False

    # Get current vision enabled state
    vision_config = CONFIG.get("vision", {})
    vision_enabled = vision_config.get("enabled", False)

    # If camera is missing but vision is enabled, disable it
    if vision_enabled and not (camera_audio and camera_video):
        print(f"[Auto-detect] USB camera not detected - disabling vision")
        if "vision" not in CONFIG:
            CONFIG["vision"] = {}
        CONFIG["vision"]["enabled"] = False
        save_config(CONFIG)
        updated = True

    # If camera is present and vision is disabled, we could enable it
    # but let's be conservative and only auto-disable, not auto-enable
    # The user can manually enable vision when they want it

    return {
        "camera_audio": camera_audio,
        "camera_video": camera_video,
        "camera_detected": camera_audio and camera_video,
        "updated_config": updated,
    }

if __name__ == "__main__":
    result = auto_detect_hardware()
    print("Hardware detection result:", result)
