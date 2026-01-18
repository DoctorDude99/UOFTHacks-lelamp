"""
User Data Directory Management

Manages persistent user data in ~/.lelamp/ that survives reinstalls.

Directory structure:
    ~/.lelamp/
    ├── config.yaml          # Main configuration
    ├── .env                  # API keys and secrets
    ├── system_info.json     # Device hardware/software info
    ├── calibration/
    │   └── lelamp.json      # Motor calibration data
    ├── recordings/          # User-created animations
    │   └── *.csv
    └── telemetry/           # Buffered telemetry data
        └── *.json
"""

import os
import json
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# User data directory
USER_DATA_DIR = Path.home() / ".lelamp"

# Subdirectories
USER_CONFIG_FILE = USER_DATA_DIR / "config.yaml"
USER_ENV_FILE = USER_DATA_DIR / ".env"
USER_CALIBRATION_DIR = USER_DATA_DIR / "calibration"
USER_RECORDINGS_DIR = USER_DATA_DIR / "recordings"
USER_TELEMETRY_DIR = USER_DATA_DIR / "telemetry"
USER_SYSTEM_INFO_FILE = USER_DATA_DIR / "system_info.json"

# Hardware paths
DEVICE_SERIAL_PATH = Path("/sys/firmware/devicetree/base/serial-number")
DEVICE_MODEL_PATH = Path("/proc/device-tree/model")
OS_RELEASE_PATH = Path("/etc/os-release")

# Repo defaults (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent  # boxbots_lelampruntime/


def get_repo_path(relative_path: str) -> Path:
    """Get absolute path to a file in the repo."""
    return REPO_ROOT / relative_path


def ensure_user_data_dir():
    """Create ~/.lelamp/ directory structure if it doesn't exist."""
    USER_DATA_DIR.mkdir(exist_ok=True)
    USER_CALIBRATION_DIR.mkdir(exist_ok=True)
    USER_RECORDINGS_DIR.mkdir(exist_ok=True)
    USER_TELEMETRY_DIR.mkdir(exist_ok=True)
    logger.info(f"User data directory ready: {USER_DATA_DIR}")


def migrate_user_data():
    """
    Migrate existing config files to ~/.lelamp/ if not already there.
    Called once on startup.
    """
    ensure_user_data_dir()

    # All user data (config.yaml, .env, calibration) lives only in ~/.lelamp/
    # No repo fallback - nothing to migrate
    logger.debug("User data directory initialized (no migrations needed)")


def get_config_path() -> Path:
    """
    Get path to config.yaml.

    Always returns ~/.lelamp/config.yaml (no repo fallback).
    """
    return USER_CONFIG_FILE


def get_env_path() -> Path:
    """
    Get path to .env file.

    Always returns ~/.lelamp/.env (no repo fallback).
    """
    return USER_ENV_FILE


def get_calibration_path() -> Path:
    """
    Get path to calibration file.

    Always returns ~/.lelamp/calibration/lelamp.json.
    """
    return USER_CALIBRATION_DIR / "lelamp.json"


def save_calibration() -> Path:
    """
    Get path where calibration should be saved.

    Always returns ~/.lelamp/calibration/lelamp.json.
    """
    ensure_user_data_dir()
    return USER_CALIBRATION_DIR / "lelamp.json"


def get_recordings_paths() -> tuple[Path, Path]:
    """
    Get paths to recordings directories.

    Returns:
        (user_recordings_dir, repo_recordings_dir)
    """
    return USER_RECORDINGS_DIR, get_repo_path("lelamp/recordings")


def get_recording_path(name: str) -> Optional[Path]:
    """
    Find a recording by name, checking user directory first.

    Args:
        name: Recording name (without .csv extension)

    Returns:
        Path to recording file, or None if not found
    """
    # Check user recordings first
    user_path = USER_RECORDINGS_DIR / f"{name}.csv"
    if user_path.exists():
        return user_path

    # Fall back to repo recordings
    repo_path = get_repo_path(f"lelamp/recordings/{name}.csv")
    if repo_path.exists():
        return repo_path

    return None


def save_recording_path(name: str) -> Path:
    """
    Get path where a new recording should be saved (always user directory).

    Args:
        name: Recording name (without .csv extension)

    Returns:
        Path in ~/.lelamp/recordings/
    """
    ensure_user_data_dir()
    return USER_RECORDINGS_DIR / f"{name}.csv"


def list_all_recordings() -> list[dict]:
    """
    List all recordings from both user and repo directories.
    User recordings take priority over repo recordings with same name.

    Returns:
        List of dicts with 'name', 'path', 'source' ('user' or 'builtin')
    """
    recordings = {}

    # First add repo recordings (will be overwritten by user recordings if same name)
    repo_dir = get_repo_path("lelamp/recordings")
    if repo_dir.exists():
        for f in repo_dir.glob("*.csv"):
            recordings[f.stem] = {
                'name': f.stem,
                'path': f,
                'source': 'builtin'
            }

    # Then add user recordings (overwrites repo ones with same name)
    if USER_RECORDINGS_DIR.exists():
        for f in USER_RECORDINGS_DIR.glob("*.csv"):
            recordings[f.stem] = {
                'name': f.stem,
                'path': f,
                'source': 'user'
            }

    return list(recordings.values())


def is_user_recording(name: str) -> bool:
    """Check if a recording is a user recording (vs builtin)."""
    user_path = USER_RECORDINGS_DIR / f"{name}.csv"
    return user_path.exists()


def delete_recording(name: str) -> bool:
    """
    Delete a user recording. Cannot delete builtin recordings.

    Returns:
        True if deleted, False if not found or is builtin
    """
    user_path = USER_RECORDINGS_DIR / f"{name}.csv"
    if user_path.exists():
        user_path.unlink()
        return True
    return False


def init_user_data():
    """
    Initialize user data directory and migrate existing files.
    Call this once at application startup.
    """
    logger.info("Initializing user data directory...")
    migrate_user_data()
    logger.info(f"User data directory: {USER_DATA_DIR}")


# =============================================================================
# Device Identity Functions
# =============================================================================

def get_device_serial() -> str:
    """
    Read device serial number from hardware.

    IMPORTANT: Always reads from hardware, never trusts stored values.
    This prevents spoofing of device identity.

    Returns:
        Device serial number (e.g., "a3b381c95fcefbc0") or "unknown" if not available
    """
    try:
        if DEVICE_SERIAL_PATH.exists():
            serial = DEVICE_SERIAL_PATH.read_text().strip('\x00').strip()
            if serial:
                return serial
    except Exception as e:
        logger.warning(f"Could not read device serial: {e}")

    return "unknown"


def get_device_serial_short() -> str:
    """
    Get the last 8 characters of the device serial.
    Used for hostname and SSID generation.

    Returns:
        Last 8 chars of serial (e.g., "5fcefbc0") or "unknown"
    """
    serial = get_device_serial()
    if serial == "unknown":
        return "unknown"
    return serial[-8:] if len(serial) >= 8 else serial


def get_pi_version() -> int:
    """
    Get Raspberry Pi version number (4, 5, or 0 for unknown/non-Pi).

    Uses the device model string to determine the Pi version.
    This is useful for selecting hardware-specific drivers (e.g., RGB LEDs).

    Returns:
        5 for Raspberry Pi 5
        4 for Raspberry Pi 4
        0 for unknown or non-Raspberry Pi
    """
    model = get_device_model()
    if "Pi 5" in model or "Pi5" in model:
        return 5
    elif "Pi 4" in model or "Pi4" in model:
        return 4
    elif "Pi 3" in model or "Pi3" in model:
        return 3
    elif "Pi" in model:
        # Generic Pi, assume older model compatible with Pi 4 approach
        return 4
    return 0


def get_device_model() -> str:
    """
    Read Raspberry Pi model from device tree.

    Returns:
        Model string (e.g., "Raspberry Pi 5 Model B Rev 1.0") or "Unknown"
    """
    try:
        if DEVICE_MODEL_PATH.exists():
            model = DEVICE_MODEL_PATH.read_text().strip('\x00').strip()
            if model:
                return model
    except Exception as e:
        logger.warning(f"Could not read device model: {e}")

    return "Unknown"


def get_os_info() -> Dict[str, str]:
    """
    Read OS information from /etc/os-release.

    Returns:
        Dict with keys like 'PRETTY_NAME', 'VERSION_ID', 'ID', etc.
    """
    os_info = {}
    try:
        if OS_RELEASE_PATH.exists():
            for line in OS_RELEASE_PATH.read_text().splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes from value
                    os_info[key] = value.strip('"\'')
    except Exception as e:
        logger.warning(f"Could not read OS info: {e}")

    return os_info


def get_kernel_version() -> str:
    """
    Get kernel version using uname.

    Returns:
        Kernel version string (e.g., "6.12.47+rpt-rpi-2712")
    """
    try:
        result = subprocess.run(['uname', '-r'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Could not get kernel version: {e}")

    return platform.release()


def get_memory_mb() -> int:
    """
    Get total system memory in MB.

    Returns:
        Total memory in MB
    """
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    # Line format: "MemTotal:       8000000 kB"
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb // 1024
    except Exception as e:
        logger.warning(f"Could not read memory info: {e}")

    return 0


def get_cpu_info() -> Dict[str, Any]:
    """
    Get CPU information.

    Returns:
        Dict with 'model', 'cores', 'architecture'
    """
    cpu_info = {
        'model': 'Unknown',
        'cores': os.cpu_count() or 0,
        'architecture': platform.machine()
    }

    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Model'):
                    cpu_info['model'] = line.split(':', 1)[1].strip()
                    break
                elif line.startswith('model name'):
                    cpu_info['model'] = line.split(':', 1)[1].strip()
    except Exception as e:
        logger.warning(f"Could not read CPU info: {e}")

    return cpu_info


def get_device_info() -> Dict[str, Any]:
    """
    Collect comprehensive hardware/software information for device registration.

    IMPORTANT: Serial number is always read fresh from hardware.

    Returns:
        Dict with all device information
    """
    os_info = get_os_info()
    cpu_info = get_cpu_info()

    return {
        # Hardware identifiers (always from hardware)
        "serial": get_device_serial(),
        "serial_short": get_device_serial_short(),
        "driver_board_sn": get_servo_driver_sn(),
        "model": get_device_model(),

        # Hardware specs
        "memory_mb": get_memory_mb(),
        "cpu": cpu_info,

        # Software versions
        "os": {
            "name": os_info.get('PRETTY_NAME', 'Unknown'),
            "version": os_info.get('VERSION_ID', 'Unknown'),
            "id": os_info.get('ID', 'Unknown'),
        },
        "kernel": get_kernel_version(),
        "python_version": platform.python_version(),

        # Platform info
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "node": platform.node(),
        },

        # Timestamps
        "collected_at": datetime.utcnow().isoformat() + "Z",
    }


def get_lelamp_version() -> str:
    """
    Get LeLamp software version from pyproject.toml or git.

    Returns:
        Version string (e.g., "3.0.0" or "dev-abc1234")
    """
    # Try pyproject.toml first
    pyproject_path = REPO_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        try:
            content = pyproject_path.read_text()
            for line in content.splitlines():
                if line.strip().startswith('version'):
                    # Parse: version = "x.y.z"
                    version = line.split('=', 1)[1].strip().strip('"\'')
                    return version
        except Exception:
            pass

    # Try git commit hash
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=5
        )
        if result.returncode == 0:
            return f"dev-{result.stdout.strip()}"
    except Exception:
        pass

    return "unknown"


def save_device_info() -> Path:
    """
    Save current device info to ~/.lelamp/system_info.json.

    Returns:
        Path to saved file
    """
    ensure_user_data_dir()

    info = get_device_info()
    info["lelamp_version"] = get_lelamp_version()

    with open(USER_SYSTEM_INFO_FILE, 'w') as f:
        json.dump(info, f, indent=2)

    logger.info(f"Saved device info to {USER_SYSTEM_INFO_FILE}")
    return USER_SYSTEM_INFO_FILE


def load_device_info() -> Optional[Dict[str, Any]]:
    """
    Load cached device info from disk.

    Note: Serial number should still be verified against hardware
    using get_device_serial() for security-sensitive operations.

    Returns:
        Cached device info dict or None if not available
    """
    if USER_SYSTEM_INFO_FILE.exists():
        try:
            with open(USER_SYSTEM_INFO_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load device info: {e}")

    return None


def get_telemetry_dir() -> Path:
    """
    Get path to telemetry buffer directory.

    Returns:
        Path to ~/.lelamp/telemetry/
    """
    ensure_user_data_dir()
    return USER_TELEMETRY_DIR


# =============================================================================
# Network Status Functions
# =============================================================================

def get_local_ip(interface: str = "wlan0") -> Optional[str]:
    """
    Get local IP address for the specified interface.

    Args:
        interface: Network interface name (default: wlan0)

    Returns:
        IP address string or None if not available
    """
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", interface],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout:
            for part in result.stdout.split():
                if '/' in part and '.' in part:
                    return part.split('/')[0]
    except Exception as e:
        logger.debug(f"Could not get local IP: {e}")

    # Try alternative method using hostname
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass

    return None


def get_wan_ip() -> Optional[str]:
    """
    Get external/WAN IP address by querying an external service.

    Returns:
        External IP address string or None if not reachable
    """
    import urllib.request

    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]

    for service in services:
        try:
            with urllib.request.urlopen(service, timeout=5) as response:
                ip = response.read().decode('utf-8').strip()
                if ip and '.' in ip:
                    return ip
        except Exception:
            continue

    return None


def get_wifi_status() -> Dict[str, Any]:
    """
    Get current WiFi connection status.

    Returns:
        Dict with:
        - connected: bool
        - ssid: str or None
        - mode: "station", "ap", or "disconnected"
        - interface: str
    """
    status = {
        "connected": False,
        "ssid": None,
        "mode": "disconnected",
        "interface": "wlan0"
    }

    try:
        # Check device status - most reliable method
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                parts = line.split(':')
                # Format: DEVICE:TYPE:STATE:CONNECTION
                if len(parts) >= 4 and parts[1] == "wifi" and parts[2] == "connected":
                    connection_name = parts[3]
                    status["connected"] = True
                    status["interface"] = parts[0]

                    # Check if it's AP mode
                    if "lelamp-ap" in connection_name.lower():
                        status["ssid"] = "lelamp-ap"
                        status["mode"] = "ap"
                    else:
                        status["ssid"] = connection_name
                        status["mode"] = "station"
                    break

    except Exception as e:
        logger.debug(f"Could not get WiFi status: {e}")

    return status


def get_internet_status() -> Dict[str, Any]:
    """
    Check if we have internet connectivity.

    Tests connectivity by:
    1. DNS resolution
    2. HTTP request to reliable endpoints

    Returns:
        Dict with:
        - connected: bool
        - latency_ms: int or None (ping time)
        - method: str (how connectivity was verified)
    """
    import socket
    import time

    status = {
        "connected": False,
        "latency_ms": None,
        "method": None
    }

    # Test 1: DNS resolution
    try:
        start = time.time()
        socket.gethostbyname("google.com")
        latency = int((time.time() - start) * 1000)
        status["connected"] = True
        status["latency_ms"] = latency
        status["method"] = "dns"
    except Exception:
        pass

    # Test 2: HTTP request (if DNS failed or to confirm)
    if not status["connected"]:
        import urllib.request
        try:
            start = time.time()
            urllib.request.urlopen("http://connectivitycheck.gstatic.com/generate_204", timeout=5)
            latency = int((time.time() - start) * 1000)
            status["connected"] = True
            status["latency_ms"] = latency
            status["method"] = "http"
        except Exception:
            pass

    return status


def get_network_info() -> Dict[str, Any]:
    """
    Get comprehensive network status information.

    Returns:
        Dict with wifi_status, internet_status, local_ip, wan_ip
    """
    wifi = get_wifi_status()
    internet = get_internet_status()

    return {
        "wifi_status": wifi,
        "internet_status": internet,
        "local_ip": get_local_ip(wifi.get("interface", "wlan0")),
        "wan_ip": get_wan_ip() if internet["connected"] else None,
    }


# =============================================================================
# System Resource Functions
# =============================================================================

def get_cpu_usage() -> Optional[float]:
    """
    Get current CPU usage percentage.

    Returns:
        CPU usage as percentage (0-100) or None if unavailable
    """
    try:
        # Read /proc/stat for CPU times
        with open('/proc/stat', 'r') as f:
            line = f.readline()
            if line.startswith('cpu '):
                parts = line.split()
                # user, nice, system, idle, iowait, irq, softirq, steal
                user = int(parts[1])
                nice = int(parts[2])
                system = int(parts[3])
                idle = int(parts[4])
                iowait = int(parts[5]) if len(parts) > 5 else 0

                total = user + nice + system + idle + iowait
                active = user + nice + system

                # Store for delta calculation
                if not hasattr(get_cpu_usage, '_last'):
                    get_cpu_usage._last = (active, total)
                    return None  # First call, no delta yet

                last_active, last_total = get_cpu_usage._last
                get_cpu_usage._last = (active, total)

                delta_active = active - last_active
                delta_total = total - last_total

                if delta_total > 0:
                    return round((delta_active / delta_total) * 100, 1)
    except Exception as e:
        logger.debug(f"Could not read CPU usage: {e}")

    return None


def get_cpu_usage_instant() -> Optional[float]:
    """
    Get instantaneous CPU usage from /proc/loadavg (1-minute load average).

    Returns as percentage based on number of CPU cores.
    """
    try:
        with open('/proc/loadavg', 'r') as f:
            load_1min = float(f.read().split()[0])

        cores = os.cpu_count() or 1
        # Convert load average to percentage (load of 1.0 per core = 100%)
        return round(min((load_1min / cores) * 100, 100), 1)
    except Exception as e:
        logger.debug(f"Could not read load average: {e}")

    return None


def get_temperature() -> Optional[float]:
    """
    Get CPU temperature in Celsius.

    Tries vcgencmd first (most accurate on Pi), falls back to thermal zone.

    Returns:
        Temperature in Celsius or None if unavailable
    """
    # Try vcgencmd first (most accurate on Raspberry Pi)
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Parse "temp=49.9'C"
            temp_str = result.stdout.strip()
            if "=" in temp_str:
                temp_val = temp_str.split("=")[1].replace("'C", "")
                return float(temp_val)
    except Exception as e:
        logger.debug(f"vcgencmd failed: {e}")

    # Fallback: read from thermal zone
    try:
        temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_path.exists():
            temp_milli = int(temp_path.read_text().strip())
            return temp_milli / 1000.0
    except Exception as e:
        logger.debug(f"thermal zone read failed: {e}")

    return None


def get_memory_usage() -> Dict[str, Any]:
    """
    Get memory usage statistics.

    Returns:
        Dict with:
        - total_mb: Total memory in MB
        - used_mb: Used memory in MB
        - free_mb: Free memory in MB
        - available_mb: Available memory in MB
        - percent: Usage percentage (0-100)
    """
    memory = {
        "total_mb": 0,
        "used_mb": 0,
        "free_mb": 0,
        "available_mb": 0,
        "percent": 0.0,
    }

    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(':')
                    value_kb = int(parts[1])
                    meminfo[key] = value_kb

        total_kb = meminfo.get('MemTotal', 0)
        free_kb = meminfo.get('MemFree', 0)
        available_kb = meminfo.get('MemAvailable', free_kb)
        buffers_kb = meminfo.get('Buffers', 0)
        cached_kb = meminfo.get('Cached', 0)

        # Used = Total - Free - Buffers - Cached (approximate)
        used_kb = total_kb - available_kb

        memory["total_mb"] = total_kb // 1024
        memory["free_mb"] = free_kb // 1024
        memory["available_mb"] = available_kb // 1024
        memory["used_mb"] = used_kb // 1024
        memory["percent"] = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0

    except Exception as e:
        logger.warning(f"Could not read memory info: {e}")

    return memory


def get_disk_usage(path: str = "/") -> Dict[str, Any]:
    """
    Get disk usage statistics for a given path.

    Args:
        path: Filesystem path to check (default: root)

    Returns:
        Dict with:
        - total_gb: Total space in GB
        - used_gb: Used space in GB
        - free_gb: Free space in GB
        - percent: Usage percentage (0-100)
    """
    disk = {
        "total_gb": 0.0,
        "used_gb": 0.0,
        "free_gb": 0.0,
        "percent": 0.0,
    }

    try:
        statvfs = os.statvfs(path)
        total_bytes = statvfs.f_frsize * statvfs.f_blocks
        free_bytes = statvfs.f_frsize * statvfs.f_bfree  # Use f_bfree to match df
        used_bytes = total_bytes - free_bytes

        disk["total_gb"] = round(total_bytes / (1024**3), 1)
        disk["used_gb"] = round(used_bytes / (1024**3), 1)
        disk["free_gb"] = round(free_bytes / (1024**3), 1)
        disk["percent"] = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0

    except Exception as e:
        logger.warning(f"Could not read disk usage: {e}")

    return disk


def get_uptime() -> Dict[str, Any]:
    """
    Get system uptime.

    Returns:
        Dict with:
        - seconds: Total uptime in seconds
        - formatted: Human-readable string (e.g., "2d 5h 30m")
    """
    uptime = {
        "seconds": 0,
        "formatted": "unknown",
    }

    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            uptime["seconds"] = int(uptime_seconds)

            # Format as human-readable
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)

            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0 or days > 0:
                parts.append(f"{hours}h")
            parts.append(f"{minutes}m")

            uptime["formatted"] = " ".join(parts)

    except Exception as e:
        logger.warning(f"Could not read uptime: {e}")

    return uptime


# =============================================================================
# Servo Driver (Waveshare) Functions
# =============================================================================

UDEV_RULE_FILE = Path("/etc/udev/rules.d/99-lelamp.rules")


def get_servo_driver_sn() -> Optional[str]:
    """
    Detect connected Waveshare USB Servo Bus Adapter serial number.

    Uses usb-devices to find the Waveshare adapter (Vendor=1a86, ProdID=55d3).

    Returns:
        Serial number string or None if not connected
    """
    try:
        result = subprocess.run(
            ["usb-devices"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Parse usb-devices output to find Waveshare adapter
            output = result.stdout.replace('\x00', '')
            # Look for Vendor=1a86 ProdID=55d3 (Waveshare USB Servo Bus Adapter)
            in_waveshare_block = False
            for line in output.splitlines():
                if "Vendor=1a86 ProdID=55d3" in line:
                    in_waveshare_block = True
                elif in_waveshare_block and line.startswith("S:"):
                    if "SerialNumber=" in line:
                        serial = line.split("SerialNumber=")[1].strip()
                        if serial:
                            return serial
                elif in_waveshare_block and line.strip() == "":
                    # End of block
                    in_waveshare_block = False
    except Exception as e:
        logger.debug(f"Could not detect servo driver: {e}")

    return None


def get_udev_waveshare_sn() -> Optional[str]:
    """
    Read the Waveshare serial number from the current udev rules.

    Returns:
        Serial number configured in udev rules, or None if not found
    """
    try:
        if UDEV_RULE_FILE.exists():
            content = UDEV_RULE_FILE.read_text()
            # Look for: ATTRS{serial}=="5A46083171"
            import re
            match = re.search(r'ATTRS\{serial\}=="([^"]+)"', content)
            if match:
                return match.group(1)
    except Exception as e:
        logger.debug(f"Could not read udev rules: {e}")

    return None


def check_and_update_waveshare_udev() -> Dict[str, Any]:
    """
    Check if connected Waveshare board matches udev rules, update if different.

    This should be called on motor initialization to handle board replacement.

    Returns:
        Dict with:
        - status: "ok", "updated", "no_device", or "error"
        - old_sn: Previous serial number (if updated)
        - new_sn: Current serial number
        - message: Human-readable status message
    """
    result = {
        "status": "ok",
        "old_sn": None,
        "new_sn": None,
        "message": None,
    }

    # Get currently connected device
    connected_sn = get_servo_driver_sn()
    if not connected_sn:
        result["status"] = "no_device"
        result["message"] = "No Waveshare servo driver detected"
        return result

    result["new_sn"] = connected_sn

    # Get configured udev SN
    udev_sn = get_udev_waveshare_sn()
    result["old_sn"] = udev_sn

    if udev_sn == connected_sn:
        result["status"] = "ok"
        result["message"] = f"Servo driver {connected_sn} matches udev rules"
        return result

    # Serial numbers don't match - need to update udev rules
    logger.warning(f"Waveshare board changed: {udev_sn} -> {connected_sn}")

    try:
        # Create new udev rule content
        udev_content = f'''# LeLamp Motor Controller (Waveshare USB Servo Bus Adapter)
# Auto-updated by LeLamp on {datetime.now().isoformat()}
# Previous SerialNumber: {udev_sn or 'none'}
SUBSYSTEM=="tty", ATTRS{{idVendor}}=="1a86", ATTRS{{idProduct}}=="55d3", ATTRS{{serial}}=="{connected_sn}", SYMLINK+="lelamp", MODE="0666"

# USB Camera symlink
SUBSYSTEM=="video4linux", ATTRS{{idVendor}}=="0c45", KERNEL=="video[0-9]*", ATTR{{index}}=="0", SYMLINK+="usbcam", MODE="0666"
'''

        # Write new udev rules (requires sudo)
        write_result = subprocess.run(
            ["sudo", "tee", str(UDEV_RULE_FILE)],
            input=udev_content,
            capture_output=True,
            text=True,
            timeout=10
        )

        if write_result.returncode != 0:
            result["status"] = "error"
            result["message"] = f"Failed to write udev rules: {write_result.stderr}"
            return result

        # Reload udev rules
        subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], timeout=10)
        subprocess.run(["sudo", "udevadm", "trigger"], timeout=10)

        result["status"] = "updated"
        result["message"] = f"Waveshare board replaced: {udev_sn or 'none'} → {connected_sn}. Udev rules updated."
        logger.info(result["message"])

    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["message"] = "Timeout updating udev rules"
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Error updating udev rules: {e}"
        logger.error(result["message"])

    return result


def get_system_status() -> Dict[str, Any]:
    """
    Get comprehensive system status for dashboard display.

    Returns:
        Dict with temperature, cpu, memory, disk, uptime, network info
    """
    # Use instant CPU usage (load average based) for API calls
    # since delta-based requires two calls
    cpu = get_cpu_usage_instant()

    return {
        "temperature": get_temperature(),
        "cpu_percent": cpu,
        "memory": get_memory_usage(),
        "disk": get_disk_usage("/"),
        "uptime": get_uptime(),
        "network": get_network_info(),
        "device": {
            "serial": get_device_serial(),
            "serial_short": get_device_serial_short(),
            "model": get_device_model(),
            "hostname": platform.node(),
            "servo_driver_sn": get_servo_driver_sn(),
        },
        "os": get_os_info().get('PRETTY_NAME', 'Unknown'),
        "kernel": get_kernel_version(),
        "lelamp_version": get_lelamp_version(),
    }
