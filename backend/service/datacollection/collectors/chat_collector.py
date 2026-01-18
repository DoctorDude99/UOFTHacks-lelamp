"""
Chat/Conversation Collector.

Collects conversation data from the MetricsService:
- Conversation turns (user and agent)
- Latency metrics
- Session information
"""

import logging
from typing import Dict, Any, Optional, List

from lelamp.service.datacollection.collectors.base import BaseCollector
from lelamp.service.datacollection.privacy import sanitize_text

logger = logging.getLogger(__name__)


class ChatCollector(BaseCollector):
    """Collector for conversation data from MetricsService."""

    def __init__(self):
        self._last_turn_count = 0
        self._collected_turn_ids = set()

    @property
    def collector_type(self) -> str:
        return "chat"

    def collect(self) -> Optional[Dict[str, Any]]:
        """
        Collect new conversation turns from MetricsService.

        Returns conversation turns that haven't been collected yet.
        """
        try:
            import lelamp.globals as g

            if not g.metrics_service:
                return None

            metrics = g.metrics_service.get_current_metrics()
            conversation = metrics.get("conversation", [])

            # Find new turns
            new_turns = []
            for turn in conversation:
                turn_id = turn.get("turn_id", "")
                if turn_id and turn_id not in self._collected_turn_ids:
                    self._collected_turn_ids.add(turn_id)

                    # Sanitize text for privacy
                    text = turn.get("text", "")
                    sanitized_text = sanitize_text(text)

                    new_turns.append({
                        "turn_id": turn_id,
                        "role": turn.get("role"),
                        "text": sanitized_text,
                        "timestamp": turn.get("timestamp"),
                    })

            if not new_turns:
                return None

            # Get session info from recent turns
            recent_turns = metrics.get("recent_turns", [])
            session_metrics = {
                "total_turns": metrics.get("session", {}).get("total_turns", 0),
                "avg_e2e_latency_ms": metrics.get("averages", {}).get("end_to_end_latency_ms", 0),
            }

            # Add latency from most recent turn
            if recent_turns:
                latest = recent_turns[-1]
                session_metrics["latest_e2e_latency_ms"] = latest.get("end_to_end_latency_ms", 0)

            return {
                "turns": new_turns,
                "session_metrics": session_metrics
            }

        except Exception as e:
            logger.error(f"Chat collection error: {e}")
            return None

    def reset(self):
        """Reset collected turn tracking (e.g., on new session)."""
        self._collected_turn_ids.clear()
        self._last_turn_count = 0
