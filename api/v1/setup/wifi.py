"""
WiFi Configuration API endpoints for setup wizard.

Provides endpoints for:
- Scanning available WiFi networks
- Connecting to a WiFi network
- Checking connection status
- Switching from AP mode to station mode
"""

import subprocess
import asyncio
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter

from api.deps import load_config, save_config

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class WifiNetwork(BaseModel):
    """WiFi network information."""
    ssid: str
    signal_strength: int  # 0-100
    security: str  # e.g., "WPA2", "Open"
    connected: bool = False
    in_use: bool = False


class WifiConnectRequest(BaseModel):
    """Request to connect to a WiFi network."""
    ssid: str
    password: Optional[str] = None


class WifiStatus(BaseModel):
    """Current WiFi connection status."""
    connected: bool
    ssid: Optional[str] = None
    ip_address: Optional[str] = None
    mode: str = "unknown"  # "ap", "station", "disconnected"


# =============================================================================
# Helper Functions
# =============================================================================

def run_command(cmd: List[str], timeout: int = 30) -> tuple:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def parse_nmcli_networks(output: str) -> List[WifiNetwork]:
    """Parse nmcli wifi list output into WifiNetwork objects."""
    networks = []
    seen_ssids = set()

    for line in output.strip().split('\n'):
        if not line:
            continue

        # Format: IN-USE:SSID:SIGNAL:SECURITY
        parts = line.split(':')
        if len(parts) >= 4:
            in_use = parts[0].strip() == '*'
            ssid = parts[1].strip()
            signal = parts[2].strip()
            security = parts[3].strip() if parts[3] else "Open"

            # Skip empty SSIDs and duplicates
            if not ssid or ssid in seen_ssids:
                continue

            seen_ssids.add(ssid)

            try:
                signal_int = int(signal) if signal else 0
            except ValueError:
                signal_int = 0

            networks.append(WifiNetwork(
                ssid=ssid,
                signal_strength=signal_int,
                security=security,
                connected=in_use,
                in_use=in_use
            ))

    # Sort by signal strength (strongest first)
    networks.sort(key=lambda x: x.signal_strength, reverse=True)
    return networks


def get_current_connection() -> Optional[dict]:
    """Get current WiFi connection info."""
    success, stdout, _ = run_command([
        "nmcli", "-t", "-f", "ACTIVE,SSID,DEVICE,TYPE",
        "connection", "show", "--active"
    ])

    if not success:
        return None

    for line in stdout.strip().split('\n'):
        parts = line.split(':')
        if len(parts) >= 4 and parts[3] == "802-11-wireless":
            return {
                "active": parts[0] == "yes",
                "ssid": parts[1],
                "device": parts[2],
                "type": parts[3]
            }

    return None


def get_ip_address(interface: str = "wlan0") -> Optional[str]:
    """Get IP address for interface."""
    success, stdout, _ = run_command([
        "ip", "-4", "-o", "addr", "show", interface
    ])

    if success and stdout:
        # Parse: "2: wlan0    inet 192.168.4.1/24 brd ..."
        for part in stdout.split():
            if '/' in part and '.' in part:
                return part.split('/')[0]

    return None


def is_ap_mode() -> bool:
    """Check if currently in AP mode."""
    success, stdout, _ = run_command([
        "nmcli", "connection", "show", "--active"
    ])

    if success:
        return "lelamp-ap" in stdout

    return False


# =============================================================================
# API Endpoints
# =============================================================================

def check_and_fix_rfkill() -> tuple:
    """Check if WiFi is blocked by rfkill and attempt to fix it."""
    success, stdout, stderr = run_command(["rfkill", "list", "wifi"])

    if not success:
        return True, "Could not check rfkill status"

    if "Soft blocked: yes" in stdout or "Hard blocked: yes" in stdout:
        # WiFi is blocked - try to unblock and set country
        run_command(["sudo", "raspi-config", "nonint", "do_wifi_country", "CA"])
        run_command(["sudo", "rfkill", "unblock", "wifi"])

        # Check again
        success2, stdout2, _ = run_command(["rfkill", "list", "wifi"])
        if "Soft blocked: yes" in stdout2:
            return False, "WiFi is blocked by rfkill. Run: sudo rfkill unblock wifi"
        if "Hard blocked: yes" in stdout2:
            return False, "WiFi is hardware blocked. Check physical WiFi switch."

    return True, None


def check_wifi_interface() -> tuple:
    """Check if WiFi interface exists and is available."""
    success, stdout, stderr = run_command(["nmcli", "device", "status"])

    if not success:
        return False, "NetworkManager not responding"

    if "wlan0" not in stdout and "wlan1" not in stdout:
        return False, "No WiFi interface found"

    if "unavailable" in stdout.lower() and "wifi" in stdout.lower():
        return False, "WiFi interface unavailable - may need country code set"

    return True, None


@router.get("/scan")
async def scan_wifi_networks():
    """
    Scan for available WiFi networks.

    Returns list of networks sorted by signal strength.
    """
    try:
        # Check if WiFi is blocked by rfkill
        rfkill_ok, rfkill_error = check_and_fix_rfkill()
        if not rfkill_ok:
            return {
                "success": False,
                "error": rfkill_error,
                "error_type": "rfkill_blocked",
                "networks": [],
                "fix_hint": "Run: sudo raspi-config nonint do_wifi_country CA && sudo rfkill unblock wifi"
            }

        # Check if WiFi interface exists
        iface_ok, iface_error = check_wifi_interface()
        if not iface_ok:
            return {
                "success": False,
                "error": iface_error,
                "error_type": "interface_unavailable",
                "networks": [],
                "fix_hint": "Check WiFi hardware or run: sudo systemctl restart NetworkManager"
            }

        # Trigger a rescan first
        run_command(["sudo", "nmcli", "device", "wifi", "rescan"], timeout=10)

        # Small delay to allow scan to complete
        await asyncio.sleep(2)

        # Get list of networks
        success, stdout, stderr = run_command([
            "nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
            "device", "wifi", "list"
        ])

        if not success:
            return {
                "success": False,
                "error": f"Failed to scan networks: {stderr}",
                "error_type": "scan_failed",
                "networks": []
            }

        networks = parse_nmcli_networks(stdout)

        # If no networks found, might still be initializing
        if not networks:
            return {
                "success": True,
                "networks": [],
                "count": 0,
                "message": "No networks found. WiFi may still be initializing - try refreshing."
            }

        return {
            "success": True,
            "networks": [n.model_dump() for n in networks],
            "count": len(networks)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "exception",
            "networks": []
        }


@router.post("/connect")
async def connect_to_wifi(request: WifiConnectRequest):
    """
    Connect to a WiFi network.

    If currently in AP mode, this will switch to station mode.
    """
    try:
        ssid = request.ssid
        password = request.password

        # Build connection command
        if password:
            cmd = [
                "sudo", "nmcli", "device", "wifi", "connect", ssid,
                "password", password
            ]
        else:
            cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid]

        # If in AP mode, disconnect AP first
        if is_ap_mode():
            run_command(["sudo", "nmcli", "connection", "down", "lelamp-ap"])
            await asyncio.sleep(1)

        # Connect to network
        success, stdout, stderr = run_command(cmd, timeout=60)

        if success:
            # Wait for connection to establish
            await asyncio.sleep(3)

            # Get IP address
            ip = get_ip_address()

            return {
                "success": True,
                "message": f"Connected to {ssid}",
                "ssid": ssid,
                "ip_address": ip
            }
        else:
            # Try to restore AP mode if connection failed
            if is_ap_mode() is False:
                run_command(["sudo", "nmcli", "connection", "up", "lelamp-ap"])

            return {
                "success": False,
                "error": stderr or "Failed to connect",
                "ssid": ssid
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/status")
async def get_wifi_status():
    """
    Get current WiFi connection status including internet connectivity.

    Returns:
        - connected: WiFi connected
        - has_internet: Can reach internet
        - ssid: Connected network name
        - mode: "station", "ap", or "disconnected"
        - local_ip: Local IP address
        - wan_ip: External IP (if has internet)
    """
    try:
        from lelamp.user_data import get_network_info

        network = get_network_info()
        wifi = network["wifi_status"]
        internet = network["internet_status"]

        return {
            "success": True,
            "connected": wifi["connected"],
            "has_internet": internet["connected"],
            "ssid": wifi["ssid"],
            "mode": wifi["mode"],
            "local_ip": network["local_ip"],
            "wan_ip": network["wan_ip"],
            "latency_ms": internet.get("latency_ms"),
            # Legacy format for backwards compatibility
            "status": WifiStatus(
                connected=wifi["connected"],
                ssid=wifi["ssid"],
                ip_address=network["local_ip"],
                mode=wifi["mode"]
            ).model_dump()
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/configure-station")
async def configure_station_mode(request: WifiConnectRequest):
    """
    Configure WiFi station mode and disable AP.

    This is called after user selects their home WiFi network.
    Creates a marker file to prevent AP from starting on next boot.
    """
    try:
        ssid = request.ssid
        password = request.password

        # 1. Connect to user's WiFi
        if password:
            cmd = [
                "sudo", "nmcli", "device", "wifi", "connect", ssid,
                "password", password
            ]
        else:
            cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid]

        # Disconnect AP first
        run_command(["sudo", "nmcli", "connection", "down", "lelamp-ap"])
        await asyncio.sleep(1)

        # Connect to station network
        success, stdout, stderr = run_command(cmd, timeout=60)

        if not success:
            # Restore AP mode on failure
            run_command(["sudo", "nmcli", "connection", "up", "lelamp-ap"])
            return {
                "success": False,
                "error": stderr or "Failed to connect to network"
            }

        # Wait for connection
        await asyncio.sleep(3)

        # 2. Mark WiFi as configured (prevents AP on next boot)
        config_marker = Path.home() / ".lelamp" / ".wifi_configured"
        config_marker.parent.mkdir(parents=True, exist_ok=True)
        config_marker.touch()

        # 3. Disable AP service
        run_command(["sudo", "systemctl", "disable", "lelamp-ap"])

        # 4. Update config
        config = load_config()
        config.setdefault("setup", {})
        config["setup"]["wifi_configured"] = True
        config["setup"]["wifi_ssid"] = ssid
        config["setup"]["steps_completed"] = config["setup"].get("steps_completed", {})
        config["setup"]["steps_completed"]["wifi"] = True
        save_config(config)

        # Get new IP
        ip = get_ip_address()

        return {
            "success": True,
            "message": f"Connected to {ssid}",
            "ssid": ssid,
            "ip_address": ip,
            "reboot_required": False,
            "note": "Device is now connected to your WiFi network"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/enable-ap")
async def enable_ap_mode():
    """
    Enable AP mode (for re-configuration).
    """
    try:
        # Disconnect from current network
        run_command(["sudo", "nmcli", "device", "disconnect", "wlan0"])
        await asyncio.sleep(1)

        # Start AP
        success, _, stderr = run_command([
            "sudo", "nmcli", "connection", "up", "lelamp-ap"
        ])

        if success:
            ip = get_ip_address()
            return {
                "success": True,
                "message": "AP mode enabled",
                "ip_address": ip or "192.168.4.1"
            }
        else:
            return {
                "success": False,
                "error": stderr or "Failed to enable AP mode"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/disable-ap")
async def disable_ap_mode():
    """
    Disable AP mode.
    """
    try:
        if is_ap_mode():
            success, _, stderr = run_command([
                "sudo", "nmcli", "connection", "down", "lelamp-ap"
            ])

            if success:
                return {"success": True, "message": "AP mode disabled"}
            else:
                return {"success": False, "error": stderr}

        return {"success": True, "message": "AP mode was not active"}

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/ap-info")
async def get_ap_info():
    """
    Get AP configuration info.
    """
    try:
        # Get device serial for SSID
        from lelamp.user_data import get_device_serial_short
        serial = get_device_serial_short()

        return {
            "success": True,
            "ap_ssid": f"lelamp_{serial}",
            "ap_password": "lelamp",
            "ap_ip": "192.168.4.1",
            "is_active": is_ap_mode()
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/skip")
async def skip_wifi_setup():
    """
    Skip WiFi setup for local-only use.

    This marks WiFi setup as complete but doesn't configure any network.
    The device will continue to use whatever network it's currently on
    (or none if in AP mode).
    """
    try:
        config = load_config()

        # Mark WiFi setup as skipped
        config.setdefault("setup", {})
        config["setup"].setdefault("steps_completed", {})
        config["setup"].setdefault("steps_skipped", {})
        config["setup"]["steps_completed"]["wifi"] = True
        config["setup"]["steps_skipped"]["wifi"] = True

        # Mark WiFi as not configured (local-only mode)
        config.setdefault("wifi", {})
        config["wifi"]["configured"] = False
        config["wifi"]["skipped"] = True

        save_config(config)

        return {
            "success": True,
            "message": "WiFi setup skipped - using local-only mode",
            "local_only": True
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
