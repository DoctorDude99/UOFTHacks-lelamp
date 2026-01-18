"""
System Metrics Collector.

Collects system-level metrics:
- CPU usage and temperature
- Memory usage
- Disk usage
- Network statistics
- Agent state
"""

import logging
from typing import Dict, Any, Optional, List

from lelamp.service.datacollection.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class SystemCollector(BaseCollector):
    """Collector for system metrics."""

    @property
    def collector_type(self) -> str:
        return "system"

    def collect(self) -> Optional[Dict[str, Any]]:
        """Collect system metrics."""
        try:
            data = {}

            # CPU
            data.update(self._get_cpu_metrics())

            # Memory
            data.update(self._get_memory_metrics())

            # Disk
            data.update(self._get_disk_metrics())

            # Network
            data.update(self._get_network_metrics())

            # Agent state
            data.update(self._get_agent_state())

            return data

        except Exception as e:
            logger.error(f"System collection error: {e}")
            return None

    def _get_cpu_metrics(self) -> Dict[str, Any]:
        """Get CPU usage and temperature."""
        result = {}

        try:
            import psutil
            result["cpu_percent"] = psutil.cpu_percent(interval=1)
        except ImportError:
            # Fallback to /proc/stat
            try:
                with open("/proc/stat", "r") as f:
                    line = f.readline()
                    parts = line.split()
                    if parts[0] == "cpu":
                        total = sum(int(p) for p in parts[1:])
                        idle = int(parts[4])
                        result["cpu_percent"] = round((1 - idle / total) * 100, 2)
            except Exception:
                pass

        # CPU temperature
        try:
            temp_path = "/sys/class/thermal/thermal_zone0/temp"
            with open(temp_path, "r") as f:
                temp = int(f.read().strip()) / 1000.0
                result["cpu_temp"] = round(temp, 1)
        except Exception:
            pass

        return result

    def _get_memory_metrics(self) -> Dict[str, Any]:
        """Get memory usage."""
        result = {}

        try:
            import psutil
            mem = psutil.virtual_memory()
            result["memory_total_mb"] = mem.total // (1024 * 1024)
            result["memory_used_mb"] = mem.used // (1024 * 1024)
            result["memory_percent"] = mem.percent
        except ImportError:
            # Fallback to /proc/meminfo
            try:
                with open("/proc/meminfo", "r") as f:
                    lines = f.readlines()
                    mem_info = {}
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 2:
                            mem_info[parts[0].rstrip(":")] = int(parts[1])

                    total = mem_info.get("MemTotal", 0)
                    free = mem_info.get("MemFree", 0)
                    buffers = mem_info.get("Buffers", 0)
                    cached = mem_info.get("Cached", 0)

                    used = total - free - buffers - cached
                    result["memory_total_mb"] = total // 1024
                    result["memory_used_mb"] = used // 1024
                    if total > 0:
                        result["memory_percent"] = round(used / total * 100, 1)
            except Exception:
                pass

        return result

    def _get_disk_metrics(self) -> Dict[str, Any]:
        """Get disk usage."""
        result = {}

        try:
            import psutil
            disk = psutil.disk_usage("/")
            result["disk_total_gb"] = round(disk.total / (1024 ** 3), 2)
            result["disk_used_gb"] = round(disk.used / (1024 ** 3), 2)
            result["disk_percent"] = disk.percent
        except ImportError:
            # Fallback to os.statvfs
            try:
                import os
                stat = os.statvfs("/")
                total = stat.f_blocks * stat.f_frsize
                free = stat.f_bfree * stat.f_frsize
                used = total - free

                result["disk_total_gb"] = round(total / (1024 ** 3), 2)
                result["disk_used_gb"] = round(used / (1024 ** 3), 2)
                if total > 0:
                    result["disk_percent"] = round(used / total * 100, 1)
            except Exception:
                pass

        return result

    def _get_network_metrics(self) -> Dict[str, Any]:
        """Get network statistics."""
        result = {}

        try:
            import psutil
            net = psutil.net_io_counters()
            result["network_bytes_sent"] = net.bytes_sent
            result["network_bytes_recv"] = net.bytes_recv
        except ImportError:
            # Fallback to /proc/net/dev
            try:
                with open("/proc/net/dev", "r") as f:
                    lines = f.readlines()[2:]  # Skip headers
                    total_sent = 0
                    total_recv = 0
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 10:
                            total_recv += int(parts[1])
                            total_sent += int(parts[9])
                    result["network_bytes_sent"] = total_sent
                    result["network_bytes_recv"] = total_recv
            except Exception:
                pass

        return result

    def _get_agent_state(self) -> Dict[str, Any]:
        """Get LeLamp agent state."""
        result = {}

        try:
            import lelamp.globals as g

            # Agent state
            if g.lelamp_agent:
                if hasattr(g.lelamp_agent, "is_sleeping"):
                    result["agent_state"] = "sleeping" if g.lelamp_agent.is_sleeping else "active"
                else:
                    result["agent_state"] = "active"
            else:
                result["agent_state"] = "not_running"

            # Active services
            services = []
            if g.animation_service:
                services.append("animation")
            if g.rgb_service:
                services.append("rgb")
            if g.vision_service:
                services.append("vision")
            if g.audio_service:
                services.append("audio")
            if g.wake_service:
                services.append("wake")
            if g.workflow_service:
                services.append("workflow")
            if g.alarm_service:
                services.append("alarm")

            result["active_services"] = services

        except Exception as e:
            logger.debug(f"Could not get agent state: {e}")
            result["agent_state"] = "unknown"

        return result
