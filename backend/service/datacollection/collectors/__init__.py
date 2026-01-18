"""
Data Collectors Package.

Collectors gather specific types of telemetry data:
- SystemCollector: CPU, memory, disk, temperature
- ChatCollector: Conversation turns from MetricsService
- ConfigCollector: Configuration snapshots
- AudioCollector: Audio recordings (optional)
"""

from lelamp.service.datacollection.collectors.base import BaseCollector
from lelamp.service.datacollection.collectors.system_collector import SystemCollector
from lelamp.service.datacollection.collectors.chat_collector import ChatCollector

__all__ = [
    "BaseCollector",
    "SystemCollector",
    "ChatCollector",
]
