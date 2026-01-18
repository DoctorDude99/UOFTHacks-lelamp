"""
Database models for LeLamp Hub.

Tables:
- devices: Registered LeLamp devices
- system_metrics: Device system telemetry
- conversation_turns: Chat history
- audio_uploads: Audio file metadata
"""

import uuid
import secrets
from datetime import datetime
from typing import Generator

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, create_engine, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

from app.config import settings, get_database_url

# Database setup
engine = create_engine(
    get_database_url(),
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def generate_api_key() -> str:
    """Generate a secure API key for devices."""
    return f"{settings.DEVICE_API_KEY_PREFIX}{secrets.token_urlsafe(settings.API_KEY_LENGTH)}"


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


# =============================================================================
# Device Model
# =============================================================================

class Device(Base):
    """Registered LeLamp device."""
    __tablename__ = "devices"

    serial = Column(String(64), primary_key=True, index=True)
    api_key = Column(String(128), unique=True, nullable=False, default=generate_api_key)

    # User linking (Clerk user ID)
    user_id = Column(String(128), nullable=True, index=True)
    linking_code = Column(String(6), nullable=True)  # 6-digit code for linking
    linking_code_expires = Column(DateTime, nullable=True)

    # Device info
    model = Column(String(128), nullable=True)
    hostname = Column(String(128), nullable=True)
    lelamp_version = Column(String(32), nullable=True)
    os_version = Column(String(128), nullable=True)
    kernel = Column(String(64), nullable=True)
    memory_mb = Column(Integer, nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    architecture = Column(String(32), nullable=True)

    # Status
    status = Column(String(32), default="active")  # active, inactive, maintenance
    last_seen = Column(DateTime, nullable=True)
    last_ip = Column(String(64), nullable=True)

    # Timestamps
    registered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    metrics = relationship("SystemMetric", back_populates="device", lazy="dynamic")
    conversations = relationship("ConversationTurn", back_populates="device", lazy="dynamic")
    audio_uploads = relationship("AudioUpload", back_populates="device", lazy="dynamic")

    def to_dict(self) -> dict:
        """Convert to dictionary (excludes API key)."""
        return {
            "serial": self.serial,
            "user_id": self.user_id,
            "model": self.model,
            "hostname": self.hostname,
            "lelamp_version": self.lelamp_version,
            "os_version": self.os_version,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
        }


# =============================================================================
# System Metrics Model
# =============================================================================

class SystemMetric(Base):
    """System telemetry data from devices."""
    __tablename__ = "system_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    device_serial = Column(String(64), ForeignKey("devices.serial"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # CPU
    cpu_percent = Column(Float, nullable=True)
    cpu_temp_celsius = Column(Float, nullable=True)

    # Memory
    memory_total_mb = Column(Integer, nullable=True)
    memory_used_mb = Column(Integer, nullable=True)
    memory_percent = Column(Float, nullable=True)

    # Disk
    disk_total_gb = Column(Float, nullable=True)
    disk_used_gb = Column(Float, nullable=True)
    disk_percent = Column(Float, nullable=True)

    # Network
    network_bytes_sent = Column(Integer, nullable=True)
    network_bytes_recv = Column(Integer, nullable=True)

    # LeLamp specific
    agent_state = Column(String(32), nullable=True)
    active_services = Column(JSON, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    device = relationship("Device", back_populates="metrics")

    # Indexes
    __table_args__ = (
        Index('idx_metrics_device_time', 'device_serial', 'timestamp'),
    )


# =============================================================================
# Conversation Model
# =============================================================================

class ConversationTurn(Base):
    """Conversation turn (user or agent message)."""
    __tablename__ = "conversation_turns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    device_serial = Column(String(64), ForeignKey("devices.serial"), nullable=False, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    turn_id = Column(String(64), nullable=True)

    # Content
    timestamp = Column(DateTime, nullable=False, index=True)
    role = Column(String(16), nullable=False)  # "user" or "agent"
    text = Column(Text, nullable=True)

    # Latency metrics (ms)
    stt_latency_ms = Column(Float, nullable=True)
    llm_latency_ms = Column(Float, nullable=True)
    tts_latency_ms = Column(Float, nullable=True)
    e2e_latency_ms = Column(Float, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    device = relationship("Device", back_populates="conversations")

    # Indexes
    __table_args__ = (
        Index('idx_conv_device_time', 'device_serial', 'timestamp'),
        Index('idx_conv_session', 'session_id'),
    )


# =============================================================================
# Audio Upload Model
# =============================================================================

class AudioUpload(Base):
    """Audio file upload metadata."""
    __tablename__ = "audio_uploads"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    device_serial = Column(String(64), ForeignKey("devices.serial"), nullable=False, index=True)
    session_id = Column(String(36), nullable=True, index=True)

    # Storage location
    storage_type = Column(String(16), default="local")  # "local" or "gcs"
    storage_path = Column(String(512), nullable=False)
    gcs_bucket = Column(String(128), nullable=True)

    # Audio metadata
    audio_type = Column(String(32), nullable=False)  # user_speech, agent_speech, ambient
    duration_seconds = Column(Float, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    format = Column(String(16), nullable=True)  # wav, mp3
    sample_rate = Column(Integer, nullable=True)

    # Timestamps
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    device = relationship("Device", back_populates="audio_uploads")


# =============================================================================
# Database Initialization
# =============================================================================

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def drop_db():
    """Drop all database tables (use with caution!)."""
    Base.metadata.drop_all(bind=engine)


# Export models
__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "drop_db",
    "generate_api_key",
    "generate_uuid",
    "Device",
    "SystemMetric",
    "ConversationTurn",
    "AudioUpload",
]
