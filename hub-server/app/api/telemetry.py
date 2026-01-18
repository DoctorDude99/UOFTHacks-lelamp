"""
Telemetry Upload API.

Endpoints:
- POST /metrics - Upload system metrics batch
- POST /conversations - Upload conversation turns
- POST /audio - Upload audio recording
- GET /metrics/{serial} - Get metrics for device
- GET /conversations/{serial} - Get conversations for device
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.models import get_db, Device, SystemMetric, ConversationTurn, AudioUpload

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class MetricData(BaseModel):
    """Single metric data point."""
    timestamp: datetime
    cpu_percent: Optional[float] = None
    cpu_temp_celsius: Optional[float] = None
    memory_total_mb: Optional[int] = None
    memory_used_mb: Optional[int] = None
    memory_percent: Optional[float] = None
    disk_total_gb: Optional[float] = None
    disk_used_gb: Optional[float] = None
    disk_percent: Optional[float] = None
    network_bytes_sent: Optional[int] = None
    network_bytes_recv: Optional[int] = None
    agent_state: Optional[str] = None
    active_services: Optional[List[str]] = None


class MetricsBatchRequest(BaseModel):
    """Batch of metrics to upload."""
    device_serial: str
    batch_id: Optional[str] = None
    metrics: List[MetricData]


class ConversationTurnData(BaseModel):
    """Single conversation turn."""
    turn_id: Optional[str] = None
    timestamp: datetime
    role: str  # "user" or "agent"
    text: str
    stt_latency_ms: Optional[float] = None
    llm_latency_ms: Optional[float] = None
    tts_latency_ms: Optional[float] = None
    e2e_latency_ms: Optional[float] = None


class ConversationBatchRequest(BaseModel):
    """Batch of conversation turns to upload."""
    device_serial: str
    session_id: str
    turns: List[ConversationTurnData]


class AudioMetadata(BaseModel):
    """Audio upload metadata."""
    session_id: Optional[str] = None
    timestamp: datetime
    duration_seconds: Optional[float] = None
    audio_type: str  # user_speech, agent_speech, ambient
    sample_rate: Optional[int] = None


# =============================================================================
# Authentication Helper
# =============================================================================

def verify_device(
    authorization: str = Header(...),
    x_device_serial: str = Header(...),
    db: Session = Depends(get_db)
) -> Device:
    """Verify device API key and return device."""
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization

    device = db.query(Device).filter(Device.api_key == token).first()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if device.serial != x_device_serial:
        raise HTTPException(status_code=401, detail="Serial mismatch")

    # Update last seen
    device.last_seen = datetime.utcnow()
    db.commit()

    return device


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/metrics")
async def upload_metrics(
    request: MetricsBatchRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    """Upload a batch of system metrics."""
    if device.serial != request.device_serial:
        raise HTTPException(status_code=403, detail="Serial mismatch")

    if len(request.metrics) > settings.MAX_METRICS_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Too many metrics (max {settings.MAX_METRICS_PER_BATCH})"
        )

    batch_id = request.batch_id or str(uuid.uuid4())
    accepted = 0

    for metric in request.metrics:
        db_metric = SystemMetric(
            device_serial=device.serial,
            timestamp=metric.timestamp,
            cpu_percent=metric.cpu_percent,
            cpu_temp_celsius=metric.cpu_temp_celsius,
            memory_total_mb=metric.memory_total_mb,
            memory_used_mb=metric.memory_used_mb,
            memory_percent=metric.memory_percent,
            disk_total_gb=metric.disk_total_gb,
            disk_used_gb=metric.disk_used_gb,
            disk_percent=metric.disk_percent,
            network_bytes_sent=metric.network_bytes_sent,
            network_bytes_recv=metric.network_bytes_recv,
            agent_state=metric.agent_state,
            active_services=metric.active_services
        )
        db.add(db_metric)
        accepted += 1

    db.commit()

    return {
        "success": True,
        "accepted": accepted,
        "batch_id": batch_id
    }


@router.post("/conversations")
async def upload_conversations(
    request: ConversationBatchRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    """Upload conversation turns."""
    if device.serial != request.device_serial:
        raise HTTPException(status_code=403, detail="Serial mismatch")

    if len(request.turns) > settings.MAX_CONVERSATIONS_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Too many turns (max {settings.MAX_CONVERSATIONS_PER_BATCH})"
        )

    accepted = 0

    for turn in request.turns:
        db_turn = ConversationTurn(
            device_serial=device.serial,
            session_id=request.session_id,
            turn_id=turn.turn_id,
            timestamp=turn.timestamp,
            role=turn.role,
            text=turn.text,
            stt_latency_ms=turn.stt_latency_ms,
            llm_latency_ms=turn.llm_latency_ms,
            tts_latency_ms=turn.tts_latency_ms,
            e2e_latency_ms=turn.e2e_latency_ms
        )
        db.add(db_turn)
        accepted += 1

    db.commit()

    return {
        "success": True,
        "session_id": request.session_id,
        "turns_accepted": accepted
    }


@router.post("/audio")
async def upload_audio(
    file: UploadFile = File(...),
    metadata: str = Form(...),
    authorization: str = Header(...),
    x_device_serial: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Upload an audio recording.

    Audio files are stored locally or in GCS depending on configuration.
    """
    # Verify device
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    device = db.query(Device).filter(Device.api_key == token).first()
    if not device or device.serial != x_device_serial:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Parse metadata
    import json
    try:
        meta = AudioMetadata(**json.loads(metadata))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid metadata: {e}")

    # Generate unique filename
    upload_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix if file.filename else ".wav"
    filename = f"{device.serial}/{meta.audio_type}/{upload_id}{file_ext}"

    # Save file locally
    upload_path = Path(settings.UPLOAD_DIR) / filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    # Read and save file
    content = await file.read()
    upload_path.write_bytes(content)

    # Create database record
    audio_upload = AudioUpload(
        device_serial=device.serial,
        session_id=meta.session_id,
        storage_type="local",
        storage_path=str(upload_path),
        audio_type=meta.audio_type,
        duration_seconds=meta.duration_seconds,
        size_bytes=len(content),
        format=file_ext.lstrip('.'),
        sample_rate=meta.sample_rate,
        timestamp=meta.timestamp
    )
    db.add(audio_upload)
    db.commit()
    db.refresh(audio_upload)

    return {
        "success": True,
        "upload_id": audio_upload.id,
        "storage_path": str(upload_path),
        "size_bytes": len(content)
    }


@router.get("/metrics/{serial}")
async def get_device_metrics(
    serial: str,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    """Get metrics for a device."""
    if device.serial != serial:
        raise HTTPException(status_code=403, detail="Access denied")

    metrics = (
        db.query(SystemMetric)
        .filter(SystemMetric.device_serial == serial)
        .order_by(SystemMetric.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    total = db.query(SystemMetric).filter(SystemMetric.device_serial == serial).count()

    return {
        "success": True,
        "metrics": [
            {
                "id": m.id,
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent,
                "memory_percent": m.memory_percent,
                "disk_percent": m.disk_percent,
                "agent_state": m.agent_state
            }
            for m in metrics
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/conversations/{serial}")
async def get_device_conversations(
    serial: str,
    session_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    """Get conversation history for a device."""
    if device.serial != serial:
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(ConversationTurn).filter(ConversationTurn.device_serial == serial)

    if session_id:
        query = query.filter(ConversationTurn.session_id == session_id)

    turns = (
        query
        .order_by(ConversationTurn.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    total = query.count()

    return {
        "success": True,
        "conversations": [
            {
                "id": t.id,
                "session_id": t.session_id,
                "turn_id": t.turn_id,
                "timestamp": t.timestamp.isoformat(),
                "role": t.role,
                "text": t.text,
                "e2e_latency_ms": t.e2e_latency_ms
            }
            for t in turns
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/audio/{serial}")
async def get_device_audio_uploads(
    serial: str,
    audio_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    """Get audio upload records for a device."""
    if device.serial != serial:
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(AudioUpload).filter(AudioUpload.device_serial == serial)

    if audio_type:
        query = query.filter(AudioUpload.audio_type == audio_type)

    uploads = (
        query
        .order_by(AudioUpload.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    total = query.count()

    return {
        "success": True,
        "uploads": [
            {
                "id": u.id,
                "audio_type": u.audio_type,
                "duration_seconds": u.duration_seconds,
                "size_bytes": u.size_bytes,
                "timestamp": u.timestamp.isoformat(),
                "storage_type": u.storage_type
            }
            for u in uploads
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }
