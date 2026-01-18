"""
WebSocket handlers for real-time data streaming.

Provides:
- /ws/stats - Real-time face tracking and system stats
- /ws/metrics - Real-time performance metrics
- /ws/agent - Real-time agent state and metrics
- /ws/audio - Real-time microphone audio levels
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import time
import numpy as np
import logging

from api.deps import get_vision_service, get_metrics_service, get_lelamp_agent, get_audio_service
from api.v1.dashboard.tracking import get_tracking_stats, is_tracking_enabled
import lelamp.globals as g

logger = logging.getLogger(__name__)
router = APIRouter()

# Audio level capture
_audio_stream = None
_audio_level = 0.0
_audio_levels_buffer = []


@router.websocket("/stats")
async def websocket_stats(websocket: WebSocket):
    """WebSocket endpoint for real-time face tracking stats."""
    await websocket.accept()

    try:
        last_frame_time = time.time()
        frame_count = 0
        fps = 0.0

        while True:
            # Calculate FPS
            current_time = time.time()
            frame_count += 1
            if current_time - last_frame_time >= 1.0:
                fps = frame_count / (current_time - last_frame_time)
                frame_count = 0
                last_frame_time = current_time

            # Get vision service and face data
            vision = get_vision_service()

            # Always send stats if vision service exists
            if vision:
                face_data = vision.get_face_data()

                # Build stats - use defaults if no face data
                stats = {
                    'fps': round(fps, 1),
                    'face_detected': False,
                    'position': [0.0, 0.0],
                    'size': 0.0,
                    'timestamp': time.time(),
                    'tracking_enabled': is_tracking_enabled()
                }

                if face_data:
                    stats['face_detected'] = face_data.detected
                    stats['position'] = face_data.position
                    stats['size'] = round(face_data.size, 2)
                    stats['timestamp'] = face_data.timestamp

                    if hasattr(face_data, 'head_pose') and face_data.head_pose:
                        stats['head_pose'] = {
                            'pitch': round(face_data.head_pose['pitch'], 1),
                            'yaw': round(face_data.head_pose['yaw'], 1),
                            'roll': round(face_data.head_pose['roll'], 1)
                        }

                await websocket.send_json(stats)

            await asyncio.sleep(0.1)  # 10Hz update rate

    except WebSocketDisconnect:
        pass  # Client disconnected


@router.websocket("/metrics")
async def websocket_metrics(websocket: WebSocket):
    """WebSocket endpoint for real-time performance metrics."""
    await websocket.accept()

    try:
        while True:
            metrics = get_metrics_service()
            if metrics:
                try:
                    data = {
                        "latency": metrics.get_latency_stats(),
                        "pipeline": metrics.get_pipeline_stats(),
                    }
                    await websocket.send_json(data)
                except Exception:
                    pass  # Skip if metrics unavailable

            await asyncio.sleep(1.0)  # 1Hz update rate

    except WebSocketDisconnect:
        pass  # Client disconnected


@router.websocket("/agent")
async def websocket_agent(websocket: WebSocket):
    """WebSocket endpoint for real-time agent state and metrics."""
    await websocket.accept()

    try:
        while True:
            metrics = get_metrics_service()
            agent = get_lelamp_agent()

            # Get pipeline type from config
            pipeline_type = "livekit"
            if g.CONFIG:
                pipeline_type = g.CONFIG.get("pipeline", {}).get("type", "livekit")

            # Debug logging (remove after verified working)
            # logging.debug(f"WebSocket /agent: pipeline_type={pipeline_type}, config exists={g.CONFIG is not None}")

            data = {
                "state": "idle",
                "is_user_speaking": False,
                "is_agent_speaking": False,
                "running": agent is not None,
                "sleeping": False,
                "latency": None,
                "last_turn": None,
                "tokens": None,
                "pipeline_type": pipeline_type,
            }

            if agent:
                data["sleeping"] = getattr(agent, '_sleeping', False)

            if metrics:
                try:
                    current = metrics.get_current_metrics()
                    state_info = current.get("current_state", {})

                    data["state"] = state_info.get("agent_state", "idle")
                    data["is_user_speaking"] = state_info.get("is_user_speaking", False)
                    data["is_agent_speaking"] = state_info.get("is_agent_speaking", False)

                    # Get average latencies
                    averages = current.get("averages", {})
                    data["latency"] = {
                        "e2e_ms": averages.get("end_to_end_latency_ms", 0),
                        "llm_ttft_ms": averages.get("llm_time_to_first_token_ms", 0),
                        "tts_ttfa_ms": averages.get("tts_time_to_first_audio_ms", 0),
                    }

                    # Get last turn metrics
                    recent_turns = current.get("recent_turns", [])
                    if recent_turns:
                        last = recent_turns[-1]
                        data["last_turn"] = {
                            "e2e_ms": last.get("end_to_end_latency_ms", 0),
                            "llm_ttft_ms": last.get("llm_time_to_first_token_ms", 0),
                            "stt_ms": last.get("stt_latency_ms", 0),
                            "tts_ttfa_ms": last.get("tts_time_to_first_audio_ms", 0),
                        }

                    # Session info
                    session = current.get("session", {})
                    data["session"] = {
                        "total_turns": session.get("total_turns", 0),
                        "duration_s": session.get("duration_seconds", 0),
                    }

                    # Token usage
                    tokens = current.get("tokens", {})
                    data["tokens"] = {
                        "session": tokens.get("session_total", 0),
                        "total": tokens.get("all_time_total", 0),
                    }

                except Exception:
                    pass  # Skip if metrics unavailable

            await websocket.send_json(data)
            await asyncio.sleep(0.2)  # 5Hz update rate for responsive UI

    except WebSocketDisconnect:
        pass  # Client disconnected


@router.websocket("/audio")
async def websocket_audio(websocket: WebSocket):
    """WebSocket endpoint for real-time microphone audio levels from AudioService."""
    await websocket.accept()
    logger.info("Audio WebSocket: Client connected")

    try:
        frame_count = 0
        while True:
            audio_service = get_audio_service()

            if not audio_service:
                # Service not available yet, send empty data and retry
                if frame_count == 0:
                    logger.warning("Audio WebSocket: AudioService not available")
                await websocket.send_json({
                    "level": 0.0,
                    "bars": [0.0] * 16,
                })
                await asyncio.sleep(0.5)
                frame_count += 1
                continue

            # Ensure monitoring is started
            if not audio_service.is_monitoring():
                logger.info("Audio WebSocket: Starting AudioService monitoring")
                audio_service.start_monitoring()
                # Give the monitor thread time to start capturing
                await asyncio.sleep(0.2)

            # Get levels from AudioService
            level, bars = audio_service.get_audio_levels()

            # Log periodically to verify data flow
            if frame_count % 200 == 0:  # Every ~5 seconds at 40fps
                logger.debug(f"Audio WebSocket: level={level:.3f}, bars_max={max(bars):.3f}")

            # Convert numpy float32 to Python float for JSON serialization
            await websocket.send_json({
                "level": float(level),
                "bars": [float(b) for b in bars],
            })

            frame_count += 1
            await asyncio.sleep(0.025)  # ~40fps

    except WebSocketDisconnect:
        logger.info("Audio WebSocket: Client disconnected")
    except Exception as e:
        logger.error(f"Audio WebSocket error: {e}", exc_info=True)
