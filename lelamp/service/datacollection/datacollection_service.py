"""
Data Collection Service.

Collects telemetry data from the device and uploads to Hub server.
Follows the existing service patterns in the codebase.

Features:
- System metrics collection (CPU, memory, disk, temp)
- Conversation log collection (from metrics_service)
- Audio recording collection
- Configuration snapshot collection
- Local buffering with retry logic
- Background upload to Hub server
- Privacy controls and PII sanitization
"""

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from lelamp.user_data import (
    get_device_serial,
    get_device_info,
    get_telemetry_dir,
    USER_DATA_DIR,
)

logger = logging.getLogger(__name__)


class DataCollectionService:
    """
    Service for collecting and uploading device telemetry.

    Follows the singleton pattern used by MetricsService.
    Uses threading for background collection and upload.
    """

    MAX_BUFFER_SIZE = 1000
    COLLECTION_INTERVAL = 60  # seconds
    UPLOAD_INTERVAL = 300  # 5 minutes
    MAX_RETRY_COUNT = 3
    BUFFER_FILE = "telemetry_buffer.json"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the data collection service.

        Args:
            config: Configuration dict from config.yaml['datacollection']
        """
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._stop_event = threading.Event()

        # Threads
        self._collection_thread: Optional[threading.Thread] = None
        self._upload_thread: Optional[threading.Thread] = None

        # Data buffer
        self._buffer: deque = deque(maxlen=self.MAX_BUFFER_SIZE)
        self._failed_uploads: deque = deque(maxlen=100)

        # Configuration
        self.config = config or {}
        self.enabled = self.config.get("enabled", False)
        self.hub_url = self.config.get("hub_url", "http://192.168.10.10:8000")
        self.upload_interval = self.config.get("upload_interval_seconds", self.UPLOAD_INTERVAL)
        self.audio_collection = self.config.get("audio_collection", False)
        self.user_consent = self.config.get("user_consent", False)

        # Device identity
        self._device_serial = get_device_serial()
        self._api_key: Optional[str] = None

        # Collectors
        self._collectors: List = []
        self._init_collectors()

        # Uploader
        self._uploader = None

        logger.info(f"DataCollectionService initialized (enabled={self.enabled})")

    def _init_collectors(self):
        """Initialize data collectors."""
        from lelamp.service.datacollection.collectors.system_collector import SystemCollector
        from lelamp.service.datacollection.collectors.chat_collector import ChatCollector

        self._collectors = [
            SystemCollector(),
            ChatCollector(),
        ]

        # Add config collector
        try:
            from lelamp.service.datacollection.collectors.config_collector import ConfigCollector
            self._collectors.append(ConfigCollector())
        except ImportError:
            pass

        logger.info(f"Initialized {len(self._collectors)} collectors")

    def _load_api_key(self):
        """Load Hub API key from .env file."""
        env_path = USER_DATA_DIR / ".env"
        if env_path.exists():
            try:
                content = env_path.read_text()
                for line in content.splitlines():
                    if line.startswith("HUB_API_KEY="):
                        self._api_key = line.split("=", 1)[1].strip()
                        return
            except Exception as e:
                logger.warning(f"Could not load API key: {e}")

    def start(self):
        """Start the data collection service."""
        if not self.enabled:
            logger.info("DataCollectionService is disabled")
            return

        if self._running.is_set():
            logger.warning("DataCollectionService already running")
            return

        # Load API key
        self._load_api_key()

        # Load buffered data from disk
        self._load_buffer()

        # Start threads
        self._running.set()
        self._stop_event.clear()

        self._collection_thread = threading.Thread(
            target=self._collection_loop,
            daemon=True,
            name="datacollection-collector"
        )
        self._collection_thread.start()

        self._upload_thread = threading.Thread(
            target=self._upload_loop,
            daemon=True,
            name="datacollection-uploader"
        )
        self._upload_thread.start()

        logger.info("DataCollectionService started")

    def stop(self, timeout: float = 5.0):
        """Stop the data collection service."""
        if not self._running.is_set():
            return

        logger.info("Stopping DataCollectionService...")

        self._stop_event.set()
        self._running.clear()

        # Wait for threads to finish
        if self._collection_thread:
            self._collection_thread.join(timeout=timeout)
        if self._upload_thread:
            self._upload_thread.join(timeout=timeout)

        # Save buffer to disk
        self._save_buffer()

        logger.info("DataCollectionService stopped")

    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running.is_set()

    def _collection_loop(self):
        """Background loop for data collection."""
        logger.debug("Collection loop started")

        while self._running.is_set() and not self._stop_event.is_set():
            try:
                self._collect_data()
            except Exception as e:
                logger.error(f"Collection error: {e}")

            # Wait for next collection interval
            self._stop_event.wait(timeout=self.COLLECTION_INTERVAL)

        logger.debug("Collection loop stopped")

    def _upload_loop(self):
        """Background loop for uploading data."""
        logger.debug("Upload loop started")

        # Initial delay before first upload
        self._stop_event.wait(timeout=30)

        while self._running.is_set() and not self._stop_event.is_set():
            try:
                self._upload_data()
            except Exception as e:
                logger.error(f"Upload error: {e}")

            # Wait for next upload interval
            self._stop_event.wait(timeout=self.upload_interval)

        logger.debug("Upload loop stopped")

    def _collect_data(self):
        """Collect data from all collectors."""
        for collector in self._collectors:
            try:
                data = collector.collect()
                if data:
                    with self._lock:
                        self._buffer.append({
                            "type": collector.collector_type,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "device_serial": self._device_serial,
                            "data": data,
                            "retry_count": 0
                        })
            except Exception as e:
                logger.error(f"Collector {collector.collector_type} error: {e}")

    def _upload_data(self):
        """Upload buffered data to Hub server."""
        if not self._api_key:
            self._load_api_key()
            if not self._api_key:
                logger.debug("No API key available - skipping upload")
                return

        if not self._buffer:
            logger.debug("Buffer empty - nothing to upload")
            return

        # Get items to upload
        items_to_upload = []
        with self._lock:
            while self._buffer and len(items_to_upload) < 100:
                items_to_upload.append(self._buffer.popleft())

        if not items_to_upload:
            return

        # Group by type
        metrics_batch = []
        conversations_batch = []

        for item in items_to_upload:
            item_type = item.get("type")
            if item_type == "system":
                metrics_batch.append(item)
            elif item_type == "chat":
                conversations_batch.append(item)

        # Upload metrics
        if metrics_batch:
            success = self._upload_metrics(metrics_batch)
            if not success:
                self._requeue_items(metrics_batch)

        # Upload conversations
        if conversations_batch:
            success = self._upload_conversations(conversations_batch)
            if not success:
                self._requeue_items(conversations_batch)

    def _upload_metrics(self, items: List[Dict]) -> bool:
        """Upload system metrics to Hub."""
        try:
            import httpx

            metrics_data = []
            for item in items:
                data = item.get("data", {})
                metrics_data.append({
                    "timestamp": item.get("timestamp"),
                    "cpu_percent": data.get("cpu_percent"),
                    "cpu_temp_celsius": data.get("cpu_temp"),
                    "memory_percent": data.get("memory_percent"),
                    "memory_used_mb": data.get("memory_used_mb"),
                    "disk_percent": data.get("disk_percent"),
                    "agent_state": data.get("agent_state"),
                    "active_services": data.get("active_services"),
                })

            response = httpx.post(
                f"{self.hub_url}/api/v1/telemetry/metrics",
                json={
                    "device_serial": self._device_serial,
                    "metrics": metrics_data
                },
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "X-Device-Serial": self._device_serial
                },
                timeout=30.0
            )

            if response.status_code == 200:
                logger.debug(f"Uploaded {len(metrics_data)} metrics")
                return True
            else:
                logger.warning(f"Metrics upload failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Metrics upload error: {e}")
            return False

    def _upload_conversations(self, items: List[Dict]) -> bool:
        """Upload conversation turns to Hub."""
        try:
            import httpx

            # Group by session
            sessions: Dict[str, List] = {}
            for item in items:
                data = item.get("data", {})
                session_id = data.get("session_id", "unknown")
                if session_id not in sessions:
                    sessions[session_id] = []
                sessions[session_id].append({
                    "turn_id": data.get("turn_id"),
                    "timestamp": item.get("timestamp"),
                    "role": data.get("role"),
                    "text": data.get("text"),
                    "e2e_latency_ms": data.get("e2e_latency_ms"),
                })

            # Upload each session
            for session_id, turns in sessions.items():
                response = httpx.post(
                    f"{self.hub_url}/api/v1/telemetry/conversations",
                    json={
                        "device_serial": self._device_serial,
                        "session_id": session_id,
                        "turns": turns
                    },
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "X-Device-Serial": self._device_serial
                    },
                    timeout=30.0
                )

                if response.status_code != 200:
                    logger.warning(f"Conversation upload failed: {response.status_code}")
                    return False

            logger.debug(f"Uploaded {len(items)} conversation turns")
            return True

        except Exception as e:
            logger.error(f"Conversation upload error: {e}")
            return False

    def _requeue_items(self, items: List[Dict]):
        """Requeue failed items for retry."""
        with self._lock:
            for item in items:
                retry_count = item.get("retry_count", 0)
                if retry_count < self.MAX_RETRY_COUNT:
                    item["retry_count"] = retry_count + 1
                    self._buffer.appendleft(item)
                else:
                    self._failed_uploads.append(item)

    def _save_buffer(self):
        """Save buffer to disk for persistence."""
        try:
            buffer_path = get_telemetry_dir() / self.BUFFER_FILE
            with self._lock:
                data = list(self._buffer)

            with open(buffer_path, 'w') as f:
                json.dump(data, f)

            logger.debug(f"Saved {len(data)} items to buffer file")
        except Exception as e:
            logger.error(f"Could not save buffer: {e}")

    def _load_buffer(self):
        """Load buffer from disk."""
        try:
            buffer_path = get_telemetry_dir() / self.BUFFER_FILE
            if buffer_path.exists():
                with open(buffer_path, 'r') as f:
                    data = json.load(f)

                with self._lock:
                    for item in data:
                        self._buffer.append(item)

                logger.debug(f"Loaded {len(data)} items from buffer file")

                # Remove file after loading
                buffer_path.unlink()
        except Exception as e:
            logger.error(f"Could not load buffer: {e}")

    def collect_now(self):
        """Force immediate data collection."""
        if not self.enabled:
            return

        self._collect_data()

    def upload_now(self):
        """Force immediate data upload."""
        if not self.enabled:
            return

        self._upload_data()

    def add_conversation_turn(
        self,
        session_id: str,
        turn_id: str,
        role: str,
        text: str,
        latency_ms: Optional[float] = None
    ):
        """Add a conversation turn to the buffer."""
        if not self.enabled or not self.user_consent:
            return

        # Sanitize text
        from lelamp.service.datacollection.privacy import sanitize_text
        sanitized_text = sanitize_text(text)

        with self._lock:
            self._buffer.append({
                "type": "chat",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "device_serial": self._device_serial,
                "data": {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "role": role,
                    "text": sanitized_text,
                    "e2e_latency_ms": latency_ms
                },
                "retry_count": 0
            })

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "running": self._running.is_set(),
                "buffer_size": len(self._buffer),
                "failed_uploads": len(self._failed_uploads),
                "device_serial": self._device_serial,
                "has_api_key": self._api_key is not None,
                "hub_url": self.hub_url
            }


# =============================================================================
# Global Singleton
# =============================================================================

_datacollection_service: Optional[DataCollectionService] = None


def get_datacollection_service() -> Optional[DataCollectionService]:
    """Get the global data collection service instance."""
    return _datacollection_service


def init_datacollection_service(config: Dict[str, Any]) -> DataCollectionService:
    """Initialize the global data collection service."""
    global _datacollection_service
    _datacollection_service = DataCollectionService(config)
    return _datacollection_service
