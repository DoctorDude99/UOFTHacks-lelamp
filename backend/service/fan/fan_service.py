"""
Fan service for Raspberry Pi 5 active cooling control.

Controls the PWM fan connected to the 4-pin JST connector on the Pi 5.
Supports reading RPM, setting fan speed, and switching between auto/manual modes.

Sysfs paths:
- /sys/class/hwmon/hwmon2/ (may vary, we search for 'cooling_fan')
- pwm1: PWM duty cycle (0-255)
- pwm1_enable: 0=off, 1=manual PWM, 2=automatic thermal control
- fan1_input: Fan RPM reading
"""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from enum import IntEnum

logger = logging.getLogger(__name__)


class FanMode(IntEnum):
    """Fan control modes."""
    OFF = 0          # Fan disabled
    MANUAL = 1       # Manual PWM control
    AUTO = 2         # Automatic thermal control


class FanService:
    """Service for controlling the Raspberry Pi 5 cooling fan."""

    # Default paths - we'll search for the actual hwmon device
    HWMON_BASE = Path("/sys/class/hwmon")
    COOLING_DEVICE = Path("/sys/class/thermal/cooling_device0")

    def __init__(self):
        self._hwmon_path: Optional[Path] = None
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # Find the fan hwmon device
        self._hwmon_path = self._find_fan_hwmon()
        if self._hwmon_path:
            logger.info(f"Found fan hwmon at: {self._hwmon_path}")
        else:
            logger.warning("Fan hwmon device not found - fan control unavailable")

    def _find_fan_hwmon(self) -> Optional[Path]:
        """Find the hwmon device for the cooling fan."""
        try:
            for hwmon in self.HWMON_BASE.iterdir():
                # Check if this hwmon is for the cooling fan
                device_link = hwmon / "device"
                if device_link.exists():
                    resolved = device_link.resolve()
                    if "cooling_fan" in str(resolved):
                        return hwmon

                # Also check by name
                name_file = hwmon / "name"
                if name_file.exists():
                    name = name_file.read_text().strip()
                    if "fan" in name.lower() or "pwm" in name.lower():
                        # Verify it has the expected files
                        if (hwmon / "pwm1").exists() and (hwmon / "fan1_input").exists():
                            return hwmon
        except Exception as e:
            logger.error(f"Error finding fan hwmon: {e}")

        return None

    @property
    def available(self) -> bool:
        """Check if fan control is available."""
        return self._hwmon_path is not None

    def _read_sysfs(self, filename: str) -> Optional[int]:
        """Read an integer value from a sysfs file."""
        if not self._hwmon_path:
            return None
        try:
            path = self._hwmon_path / filename
            return int(path.read_text().strip())
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}")
            return None

    def _write_sysfs(self, filename: str, value: int) -> bool:
        """Write an integer value to a sysfs file."""
        if not self._hwmon_path:
            return False
        try:
            path = self._hwmon_path / filename
            path.write_text(str(value))
            return True
        except PermissionError:
            logger.error(f"Permission denied writing to {filename}. Run with sudo or add udev rule.")
            return False
        except Exception as e:
            logger.error(f"Error writing {filename}: {e}")
            return False

    def get_rpm(self) -> Optional[int]:
        """Get current fan RPM."""
        return self._read_sysfs("fan1_input")

    def get_pwm(self) -> Optional[int]:
        """Get current PWM value (0-255)."""
        return self._read_sysfs("pwm1")

    def get_pwm_percent(self) -> Optional[float]:
        """Get current PWM as percentage (0-100)."""
        pwm = self.get_pwm()
        if pwm is not None:
            return round((pwm / 255) * 100, 1)
        return None

    def get_mode(self) -> Optional[FanMode]:
        """Get current fan control mode."""
        value = self._read_sysfs("pwm1_enable")
        if value is not None:
            try:
                return FanMode(value)
            except ValueError:
                return FanMode.MANUAL
        return None

    def set_pwm(self, value: int) -> bool:
        """
        Set PWM duty cycle (0-255).

        Note: Fan must be in MANUAL mode for this to take effect.
        """
        value = max(0, min(255, value))
        return self._write_sysfs("pwm1", value)

    def set_pwm_percent(self, percent: float) -> bool:
        """Set PWM as percentage (0-100)."""
        pwm = int((percent / 100) * 255)
        return self.set_pwm(pwm)

    def set_mode(self, mode: FanMode) -> bool:
        """Set fan control mode."""
        return self._write_sysfs("pwm1_enable", mode.value)

    def set_speed(self, percent: float) -> bool:
        """
        Set fan speed as percentage.

        Automatically switches to manual mode if needed.
        """
        # Ensure we're in manual mode
        current_mode = self.get_mode()
        if current_mode != FanMode.MANUAL:
            if not self.set_mode(FanMode.MANUAL):
                return False

        return self.set_pwm_percent(percent)

    def set_auto(self) -> bool:
        """Enable automatic thermal control."""
        return self.set_mode(FanMode.AUTO)

    def get_temperature(self) -> Optional[float]:
        """Get CPU temperature in Celsius."""
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
            logger.error(f"Error reading temperature: {e}")

        # Fallback: read from thermal zone
        try:
            temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
            if temp_path.exists():
                temp_milli = int(temp_path.read_text().strip())
                return temp_milli / 1000.0
        except Exception as e:
            logger.error(f"Error reading thermal zone: {e}")

        return None

    def get_status(self) -> Dict[str, Any]:
        """Get complete fan status."""
        mode = self.get_mode()
        return {
            "available": self.available,
            "rpm": self.get_rpm(),
            "pwm": self.get_pwm(),
            "pwm_percent": self.get_pwm_percent(),
            "mode": mode.name if mode else None,
            "mode_value": mode.value if mode else None,
            "temperature": self.get_temperature(),
        }

    async def start_monitor(self, interval: float = 5.0, callback=None):
        """
        Start background monitoring of fan status.

        Args:
            interval: Seconds between status checks
            callback: Optional async callback(status_dict) for each update
        """
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(interval, callback)
        )
        logger.info("Fan monitor started")

    async def stop_monitor(self):
        """Stop background monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("Fan monitor stopped")

    async def _monitor_loop(self, interval: float, callback):
        """Background monitoring loop."""
        while self._running:
            try:
                status = self.get_status()

                # Log if temperature is high
                temp = status.get("temperature")
                if temp and temp > 70:
                    logger.warning(f"High CPU temperature: {temp}°C")
                elif temp and temp > 80:
                    logger.error(f"Critical CPU temperature: {temp}°C")

                if callback:
                    await callback(status)

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fan monitor error: {e}")
                await asyncio.sleep(interval)


# Singleton instance
_fan_service: Optional[FanService] = None


def get_fan_service() -> FanService:
    """Get or create the fan service singleton."""
    global _fan_service
    if _fan_service is None:
        _fan_service = FanService()
    return _fan_service
