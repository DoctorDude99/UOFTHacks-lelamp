"""
Configuration Snapshot Collector.

Collects configuration snapshots for tracking device settings:
- Agent configuration
- Service states
- Setup status
"""

import logging
from typing import Dict, Any, Optional

from lelamp.service.datacollection.collectors.base import BaseCollector
from lelamp.service.datacollection.privacy import sanitize_dict

logger = logging.getLogger(__name__)


class ConfigCollector(BaseCollector):
    """Collector for configuration snapshots."""

    def __init__(self):
        self._last_config_hash = None

    @property
    def collector_type(self) -> str:
        return "config"

    def collect(self) -> Optional[Dict[str, Any]]:
        """
        Collect configuration snapshot.

        Only returns data if config has changed since last collection.
        """
        try:
            import lelamp.globals as g

            if not g.CONFIG:
                return None

            # Create a hash to detect changes
            config_str = str(sorted(g.CONFIG.items()))
            config_hash = hash(config_str)

            # Skip if unchanged
            if config_hash == self._last_config_hash:
                return None

            self._last_config_hash = config_hash

            # Extract safe config subset (no secrets)
            safe_config = self._extract_safe_config(g.CONFIG)

            return {
                "config_snapshot": safe_config,
                "config_hash": str(config_hash)
            }

        except Exception as e:
            logger.error(f"Config collection error: {e}")
            return None

    def _extract_safe_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract configuration without sensitive data."""
        # Keys to include (whitelist approach for safety)
        safe_keys = {
            "id",
            "agent",
            "pipeline",
            "setup",
            "motors",
            "language",
            "volume",
            "microphone_volume",
            "vad",
            "endpointing",
            "motor_preset",
            "face_tracking",
            "vision",
            "webui",
            "modifiers",
            "rgb",
        }

        # Extract only safe keys
        safe_config = {}
        for key in safe_keys:
            if key in config:
                value = config[key]
                # Remove any nested sensitive data
                if isinstance(value, dict):
                    safe_config[key] = sanitize_dict(value)
                else:
                    safe_config[key] = value

        return safe_config
