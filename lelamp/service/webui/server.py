"""
WebUI server implementation.

Starts HTTP and HTTPS servers for the web dashboard.
Initializes hardware services based on their enabled flags in config.
Services default to enabled=true (assume hardware present).
"""

import logging
import os
import subprocess
import threading
from pathlib import Path

import uvicorn

import lelamp.globals as g

logger = logging.getLogger(__name__)

_hardware_initialized = False


def _check_servo_driver_udev():
    """
    Check if Waveshare servo driver matches udev rules.
    Updates rules and creates notification if board was replaced.
    """
    from lelamp.user_data import check_and_update_waveshare_udev

    try:
        result = check_and_update_waveshare_udev()

        if result["status"] == "updated":
            # Board was replaced - notify user
            g.add_notification(
                f"Servo driver board replaced. Updated from {result['old_sn'] or 'none'} to {result['new_sn']}. "
                f"Udev rules have been automatically updated.",
                notification_type="warning",
                notification_id="waveshare_replaced"
            )
            logger.warning(result["message"])
        elif result["status"] == "error":
            g.add_notification(
                f"Servo driver error: {result['message']}",
                notification_type="error",
                notification_id="waveshare_error"
            )
            logger.error(result["message"])
        elif result["status"] == "ok":
            logger.debug(f"Servo driver OK: {result['new_sn']}")
        # no_device is fine - just means no waveshare connected

    except Exception as e:
        logger.error(f"Error checking servo driver udev: {e}")


def init_hardware_services():
    """
    Initialize ALL hardware services.

    This is the single source of truth for service initialization.
    Services are stored in globals (g.*) and used by both WebUI and Agent.
    The agent consumes these services - it doesn't create them.
    """
    global _hardware_initialized

    if _hardware_initialized:
        return

    config = g.CONFIG
    logger.info("Initializing hardware services (server.py is primary)...")

    # Auto-detect hardware and update config if needed
    # This handles missing USB camera gracefully
    detection = g.auto_detect_hardware()
    if detection["updated_config"]:
        config = g.CONFIG  # Reload after save
        logger.info(f"Hardware detection: camera_audio={detection['camera_audio']}, "
                   f"camera_video={detection['camera_video']}")
    elif not detection["camera_detected"]:
        logger.info("USB camera not detected (audio capture may fail)")

    # RGB Service - default enabled
    if config.get("rgb", {}).get("enabled", True):
        _init_rgb_service(config)
    else:
        logger.info("RGB disabled in config")

    # Motor/Animation Service - default enabled
    if config.get("motors", {}).get("enabled", True):
        # Check if Waveshare board matches udev rules (handles board replacement)
        _check_servo_driver_udev()
        _init_animation_service(config)
    else:
        logger.info("Motors disabled in config")

    # Audio Service - always start (needed for playing system sounds)
    _init_audio_service(config)

    # Theme Service - always start
    _init_theme_service(config)

    # Vision Service - if vision or face_tracking enabled
    if config.get("vision", {}).get("enabled", True) or config.get("face_tracking", {}).get("enabled", False):
        _init_vision_service(config)
    else:
        logger.info("Vision disabled in config")

    # Workflow Service - for automation workflows
    _init_workflow_service(config)

    # g.vision_service.set_hand_callback(g.animation_service.hand_control_callback)

    # Set system volumes
    # _set_system_volumes(config)

    import asyncio
    from lelamp.service.agent.agent_service import init_agent_service
    def run_async_in_thread():
        asyncio.run(init_agent_service())
    thread = threading.Thread(target=run_async_in_thread)
    thread.start()

    _hardware_initialized = True
    logger.info("Hardware services initialized")

def _init_rgb_service(config: dict):
    """Initialize RGB LED service."""
    from lelamp.service.rgb import RGBService
    from lelamp.service.rgb.sequences import set_rgb_fps

    rgb_config = config.get("rgb", {})
    led_count = rgb_config.get("led_count", 93)

    if led_count == 0:
        logger.warning("RGB enabled but led_count is 0")
        return

    set_rgb_fps(rgb_config.get("fps", 1))

    try:
        g.rgb_service = RGBService(
            led_count=led_count,
            led_pin=rgb_config.get("led_pin", 10),
            led_freq_hz=rgb_config.get("led_freq_hz", 800000),
            led_dma=rgb_config.get("led_dma", 10),
            led_brightness=rgb_config.get("led_brightness", 50),
            led_invert=rgb_config.get("led_invert", False),
            led_channel=rgb_config.get("led_channel", 0),
            rings=rgb_config.get("rings"),
            default_animation=rgb_config.get("default_animation", "ripple"),
            default_color=tuple(rgb_config.get("default_color", [0, 0, 150]))
        )
        g.rgb_service.start()

        # Play startup animation if setup is complete
        if config.get("setup", {}).get("setup_complete", False):
            default_anim = rgb_config.get("default_animation", "ripple")
            g.rgb_service.handle_event("animation", {
                "name": default_anim,
                "color": tuple(rgb_config.get("default_color", [0, 0, 150]))
            })

        logger.info(f"RGB service started ({led_count} LEDs)")
    except Exception as e:
        logger.error(f"RGB service failed: {e}")
        g.rgb_service = None


def _init_animation_service(config: dict):
    """Initialize animation/motor service."""
    from lelamp.service.motors.animation_service import AnimationService

    motors_config = config.get("motors", {})
    port = motors_config.get("port") or config.get("port", "/dev/lelamp")

    if not os.path.exists(port):
        logger.warning(f"Motors enabled but port {port} not found")
        return

    try:
        g.animation_service = AnimationService(
            port=port,
            fps=30,
            duration=4.0,
            idle_recording="idle",
            config=config
        )
        g.animation_service.start()

        # Play idle if setup complete and calibrated
        if config.get("setup", {}).get("setup_complete", False) and not g.calibration_required:
            g.animation_service.dispatch("play", "idle")

        logger.info(f"Animation service started on {port}")
    except Exception as e:
        logger.error(f"Animation service failed: {e}")
        g.animation_service = None


def _init_audio_service(config: dict):
    """Initialize audio service."""
    from lelamp.service.audio import AudioService

    try:
        # Get volume from config (default 50%)
        volume = config.get("volume", 50)
        g.audio_service = AudioService(assets_dir="assets/AudioFX", volume=volume)
        g.audio_service.start()

        # Only start audio level monitoring if USB camera is detected
        # (monitoring uses lelamp_capture which requires the camera mic)
        if g.detect_usb_camera():
            g.audio_service.start_monitoring()
            logger.info(f"Audio service started with monitoring (volume: {volume}%)")
        else:
            logger.info(f"Audio service started without monitoring - USB camera not detected (volume: {volume}%)")
    except Exception as e:
        logger.warning(f"Audio service failed: {e}")
        g.audio_service = None


def _init_theme_service(config: dict):
    """Initialize theme service."""
    from lelamp.service.theme import init_theme_service, ThemeSound

    theme_config = config.get("theme", {})
    theme_name = theme_config.get("name", "Lelamp")

    try:
        g.theme_service = init_theme_service(theme_name=theme_name)
        # Note: Startup sound is played by the agent (lelamp.py) when it initializes
        # Don't play here to avoid duplicate sounds
        logger.info("Theme service initialized")
    except Exception as e:
        logger.warning(f"Theme service failed: {e}")
        g.theme_service = None


def _init_vision_service(config: dict):
    """Initialize vision service for camera/face tracking."""
    from lelamp.service.vision.vision_service import VisionService

    vision_config = config.get("vision", {})
    face_tracking_config = config.get("face_tracking", {})

    # Determine camera device/index
    camera_device = vision_config.get("camera_device")
    if camera_device:
        # Use configured device path
        camera_index = camera_device
    else:
        # Fall back to camera_index or auto-detect
        camera_index = face_tracking_config.get("camera_index", 0)

    resolution = tuple(vision_config.get("resolution", [320, 240]))
    fps = vision_config.get("fps", 10)

    try:
        g.vision_service = VisionService(
            camera_index=camera_index,
            resolution=resolution,
            fps=fps,
        )
        g.vision_service.start()
        logger.info(f"Vision service started (camera: {camera_index})")
    except Exception as e:
        logger.error(f"Vision service failed: {e}")
        g.vision_service = None


def _init_workflow_service(config: dict):
    """Initialize workflow service."""
    from lelamp.service.workflows.workflow_service import WorkflowService

    try:
        g.workflow_service = WorkflowService(db_path="lelamp.db")
        g.workflow_service.sync_workflows_to_db()
        g.workflow_service.preload_workflow_tools()
        logger.info("Workflow service initialized")
    except Exception as e:
        logger.warning(f"Workflow service failed: {e}")
        g.workflow_service = None

def _set_system_volumes(config: dict):
    """Set system audio volumes from config."""
    speaker_vol = config.get("volume", 50)
    mic_vol = config.get("microphone_volume", 50)

    try:
        subprocess.run(["amixer", "sset", "Master", f"{speaker_vol}%"],
                      capture_output=True, timeout=5)
    except Exception:
        pass

    try:
        subprocess.run(["amixer", "sset", "Capture", f"{mic_vol}%"],
                      capture_output=True, timeout=5)
    except Exception:
        pass


def create_webui_app():
    """Create FastAPI app for WebUI."""
    from api import create_api
    return create_api(vision_service=g.vision_service)


def start_webui_server() -> threading.Thread:
    """Start WebUI server in background thread."""
    if not g.CONFIG.get('webui', {}).get('enabled', True):
        logger.info("WebUI disabled in config")
        return None

    # Initialize ALL hardware services - server.py is the primary initializer
    # Agent will consume these services from globals, not create them
    init_hardware_services()

    port = g.CONFIG.get('webui', {}).get('port', 8080)
    app = create_webui_app()

    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    _log_access_urls(port)
    return thread


def _log_access_urls(port: int):
    """Log WebUI access URLs."""
    import socket
    hostname = socket.gethostname()

    try:
        import netifaces
        primary_ip = None
        for iface in netifaces.interfaces():
            if iface.startswith('eth') or iface.startswith('wlan'):
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info.get('addr')
                        if ip and not ip.startswith('127.'):
                            primary_ip = ip
                            break
                if primary_ip:
                    break
    except Exception:
        try:
            primary_ip = socket.gethostbyname(hostname)
        except Exception:
            primary_ip = None

    if primary_ip:
        print(f"\n{'='*60}")
        print(f"WebUI: http://{primary_ip}:{port}")
        print(f"{'='*60}\n")
