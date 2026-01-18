"""
Data Collection Service Package.

Collects telemetry data from the device and uploads to Hub server:
- System metrics (CPU, memory, disk, temperature)
- Conversation logs
- Audio recordings
- Configuration snapshots

Usage:
    from lelamp.service.datacollection import get_datacollection_service

    service = get_datacollection_service()
    service.start()
"""

from lelamp.service.datacollection.datacollection_service import (
    DataCollectionService,
    get_datacollection_service,
    init_datacollection_service,
)

__all__ = [
    "DataCollectionService",
    "get_datacollection_service",
    "init_datacollection_service",
]
