"""
System API endpoints - service control, network info, audio fixes.
"""
import os
import subprocess
import glob as glob_module
import logging
import socket

from fastapi import APIRouter, Query

router = APIRouter()


# =============================================================================
# Service Control (systemd)
# =============================================================================


@router.post("/service/enable")
async def enable_service():
    """Enable LeLamp systemd service."""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "enable", "lelamp.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service enabled. Will start automatically on boot."}
        return {"success": False, "error": result.stderr or "Failed to enable service"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/service/disable")
async def disable_service():
    """Disable LeLamp systemd service."""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "disable", "lelamp.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service disabled. Will not start automatically on boot."}
        return {"success": False, "error": result.stderr or "Failed to disable service"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/service/restart")
async def restart_service():
    """Restart LeLamp systemd service."""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "lelamp.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service restart initiated."}
        return {"success": False, "error": result.stderr or "Failed to restart service"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/service/status")
async def service_status():
    """Get LeLamp systemd service status."""
    try:
        result = subprocess.run(
            ["systemctl", "status", "lelamp.service", "--no-pager"],
            capture_output=True,
            text=True,
            check=False,
        )
        enabled_result = subprocess.run(
            ["systemctl", "is-enabled", "lelamp.service"],
            capture_output=True,
            text=True,
        )
        return {
            "success": True,
            "status": result.stdout,
            "enabled": enabled_result.stdout.strip() == "enabled",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Audio Troubleshooting
# =============================================================================


@router.post("/audio/fix-semaphores")
async def fix_audio_semaphores():
    """Clean up ALSA semaphores and restart audio services."""
    try:
        # Remove ALSA semaphores
        sem_files = glob_module.glob("/dev/shm/sem.ALSA_*")
        for sem_file in sem_files:
            try:
                os.remove(sem_file)
            except Exception:
                pass

        # Restart raspotify if running
        raspotify_running = (
            subprocess.run(
                ["systemctl", "is-active", "raspotify.service"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            == "active"
        )

        if raspotify_running:
            subprocess.run(["sudo", "systemctl", "restart", "raspotify"], check=False)

        return {
            "success": True,
            "message": f"Cleaned up {len(sem_files)} semaphore(s). "
            + ("Raspotify restarted." if raspotify_running else ""),
        }
    except Exception as e:
        logging.error(f"Error fixing audio semaphores: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Network Info
# =============================================================================


@router.get("/network/info")
async def network_info():
    """Get network information including hostname and IP."""
    try:
        hostname = socket.gethostname()

        # Get local IP
        ip_address = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
            s.close()
        except Exception:
            ip_address = "unknown"

        # Try to get .local address
        local_hostname = f"{hostname}.local"

        return {
            "success": True,
            "hostname": hostname,
            "local_hostname": local_hostname,
            "ip_address": ip_address,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Fan Control (RPi5 Active Cooling)
# =============================================================================

from lelamp.service.fan import FanService

# Create fan service instance
_fan_service = FanService()


@router.get("/fan/status")
async def fan_status():
    """Get fan status including RPM, PWM, temperature, and mode."""
    try:
        if not _fan_service.available:
            return {
                "success": False,
                "error": "Fan control not available on this device",
            }

        status = _fan_service.get_status()
        return {"success": True, **status}
    except Exception as e:
        logging.error(f"Error getting fan status: {e}")
        return {"success": False, "error": str(e)}


@router.post("/fan/speed")
async def set_fan_speed(percent: float = Query(..., ge=0, le=100, description="Fan speed percentage")):
    """
    Set fan speed as percentage (0-100).

    Automatically switches to manual mode.
    """
    try:
        if not _fan_service.available:
            return {
                "success": False,
                "error": "Fan control not available on this device",
            }

        logging.info(f"Setting fan speed to {percent}%")
        success = _fan_service.set_speed(percent)
        logging.info(f"Fan set_speed result: {success}")

        if success:
            return {
                "success": True,
                "speed": percent,
                "mode": "MANUAL",
                "rpm": _fan_service.get_rpm(),
            }
        return {"success": False, "error": "Failed to set fan speed - check permissions"}
    except Exception as e:
        logging.error(f"Error setting fan speed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/fan/auto")
async def set_fan_auto():
    """Enable automatic thermal control for the fan."""
    try:
        if not _fan_service.available:
            return {
                "success": False,
                "error": "Fan control not available on this device",
            }

        success = _fan_service.set_auto()

        if success:
            return {
                "success": True,
                "mode": "AUTO",
                "message": "Fan is now under automatic thermal control",
            }
        return {"success": False, "error": "Failed to enable auto mode"}
    except Exception as e:
        logging.error(f"Error enabling auto mode: {e}")
        return {"success": False, "error": str(e)}


@router.get("/fan/temperature")
async def get_temperature():
    """Get CPU temperature."""
    try:
        temp = _fan_service.get_temperature()
        if temp is not None:
            return {
                "success": True,
                "temperature": temp,
                "unit": "celsius",
            }
        return {"success": False, "error": "Failed to read temperature"}
    except Exception as e:
        logging.error(f"Error reading temperature: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# System Information
# =============================================================================

from lelamp.user_data import (
    get_system_status,
    get_device_serial_short,
)


@router.get("/info")
async def system_info():
    """
    Get comprehensive system information for dashboard display.

    Includes: device info, OS, network, temperature, memory, disk, uptime, fan status.
    """
    try:
        # Get base system status from user_data
        status = get_system_status()

        # Add fan information
        if _fan_service.available:
            fan_status = _fan_service.get_status()
            status["fan"] = {
                "available": True,
                "rpm": fan_status.get("rpm"),
                "pwm_percent": fan_status.get("pwm_percent"),
                "mode": fan_status.get("mode"),
            }
        else:
            status["fan"] = {"available": False}

        # Add device name in lelamp_serialnumber format
        serial_short = get_device_serial_short()
        status["device_name"] = f"lelamp_{serial_short}"

        # Connection status (true if we can serve this request)
        status["connected"] = True

        return {"success": True, **status}
    except Exception as e:
        logging.error(f"Error getting system info: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# System Notifications
# =============================================================================

import lelamp.globals as g


@router.get("/notifications")
async def get_notifications():
    """
    Get active system notifications.

    Returns list of notifications that should be displayed in the WebUI.
    Notifications are automatically created for events like:
    - Servo driver board replacement
    - System errors
    - Important status changes
    """
    try:
        notifications = g.get_notifications()
        return {"success": True, "notifications": notifications}
    except Exception as e:
        logging.error(f"Error getting notifications: {e}")
        return {"success": False, "error": str(e)}


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str):
    """Dismiss a notification by ID."""
    try:
        dismissed = g.dismiss_notification(notification_id)
        if dismissed:
            return {"success": True, "message": f"Notification {notification_id} dismissed"}
        return {"success": False, "error": f"Notification {notification_id} not found"}
    except Exception as e:
        logging.error(f"Error dismissing notification: {e}")
        return {"success": False, "error": str(e)}


@router.post("/notifications/clear")
async def clear_notifications():
    """Clear all notifications."""
    try:
        g.clear_notifications()
        return {"success": True, "message": "All notifications cleared"}
    except Exception as e:
        logging.error(f"Error clearing notifications: {e}")
        return {"success": False, "error": str(e)}
