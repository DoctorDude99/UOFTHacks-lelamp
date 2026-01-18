"""
Dependency injection for LeLamp API.

This module provides FastAPI dependencies that inject services
into route handlers. All service access should go through here.

Example usage in a route:
    @router.get("/status")
    async def get_status(
        animation: AnimationService = Depends(get_animation_service)
    ):
        return {"running": animation.is_running()}
"""

from typing import Optional
from pathlib import Path
import yaml

# Import global services
import lelamp.globals as g
from lelamp.user_data import get_config_path, USER_CONFIG_FILE


def get_config() -> dict:
    """Get the current configuration."""
    return g.CONFIG


def load_config() -> dict:
    """Load config from disk (fresh read from ~/.lelamp/config.yaml)."""
    config_path = get_config_path()
    with open(config_path, 'r') as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict) -> None:
    """Save config to disk (~/.lelamp/config.yaml) and update in-memory copy."""
    # Update the in-memory global config so other services see the changes
    g.CONFIG = config

    # Always save to user config location
    with open(USER_CONFIG_FILE, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_animation_service():
    """Get the animation service instance."""
    if g.animation_service is not None:
        return g.animation_service
    # Fallback to main module
    try:
        import main
        return getattr(main, 'animation_service_global', None)
    except (ImportError, AttributeError):
        return None


def get_rgb_service():
    """Get the RGB LED service instance."""
    if g.rgb_service is not None:
        return g.rgb_service
    # Fallback: get from agent
    agent = get_lelamp_agent()
    if agent:
        return getattr(agent, 'rgb_service', None)
    return None


def get_vision_service():
    """Get the vision/camera service instance."""
    return g.vision_service


def get_audio_service():
    """Get the audio service instance."""
    return g.audio_service


def get_alarm_service():
    """Get the alarm service instance."""
    return g.alarm_service


def get_wake_service():
    """Get the wake word service instance."""
    return g.wake_service


def get_workflow_service():
    """Get the workflow service instance."""
    return g.workflow_service


def get_metrics_service():
    """Get the metrics service instance."""
    return g.metrics_service


def get_agent_session():
    """Get the current agent session."""
    return g.agent_session_global


def get_lelamp_agent():
    """Get the LeLamp agent instance.

    Checks both lelamp.globals and main module for the agent,
    since they may be in different processes.
    """
    # First try the globals module
    if g.lelamp_agent is not None:
        return g.lelamp_agent

    # Fallback: try to get from main module directly
    try:
        import main
        return getattr(main, 'lelamp_agent_global', None)
    except (ImportError, AttributeError):
        return None


def get_spotify_service():
    """Get the Spotify service from the agent."""
    agent = get_lelamp_agent()
    if agent:
        return getattr(agent, 'spotify_service', None)
    return None


__all__ = [
    "get_config",
    "get_config_path",
    "load_config",
    "save_config",
    "get_animation_service",
    "get_rgb_service",
    "get_vision_service",
    "get_audio_service",
    "get_alarm_service",
    "get_wake_service",
    "get_workflow_service",
    "get_metrics_service",
    "get_agent_session",
    "get_lelamp_agent",
    "get_spotify_service",
]
