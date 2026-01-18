"""
LiveKit Service - Manages LiveKit Cloud connection and agent lifecycle.

This service:
- Checks credentials (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, OPENAI_API_KEY)
- Manages room connection lifecycle (connect/disconnect on demand)
- Publishes device tracks (mic, camera) to room
- Subscribes to agent audio tracks for playback
- Provides clean interface for AI agents (OpenAI Realtime, Local, Custom GPU)

Architecture:
    livekit_service (always manages connection)
    ├── connect() / disconnect()
    ├── publish_mic_track()
    ├── publish_video_track()
    └── on_agent_audio(callback)

    Agents connect on top:
    ├── OpenAI Realtime (joins room, E2E processing)
    ├── Local Pipeline (processes locally, mirrors to room)
    └── Custom GPU Agent (joins room from server)
"""

from .livekit_service import LiveKitService, LiveKitStatus, init_livekit_service, get_livekit_service

__all__ = ["LiveKitService", "LiveKitStatus", "init_livekit_service", "get_livekit_service"]
