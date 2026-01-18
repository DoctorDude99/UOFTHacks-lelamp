"""
Animations management endpoints.

Handles listing, playing, recording, and deleting motor animations.
"""

import os
import csv
import time
import threading
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import logging

from api.deps import get_animation_service
from lelamp.user_data import (
    list_all_recordings,
    get_recording_path,
    save_recording_path,
    is_user_recording,
    delete_recording,
    USER_RECORDINGS_DIR,
)

router = APIRouter()

# Repo recordings (builtin animations)
RECORDINGS_DIR = Path("lelamp/recordings")


class PlayRequest(BaseModel):
    name: str


class RecordRequest(BaseModel):
    name: str


class DeleteRequest(BaseModel):
    name: str


# Recording state
_recording_active = False
_recording_thread: Optional[threading.Thread] = None
_recording_name: Optional[str] = None
_recording_data: list = []
_recording_start_time: float = 0


@router.get("/")
async def list_animations():
    """List all available animations (from both user and builtin directories)."""
    try:
        animations = []

        # Use user_data helper to get all recordings from both locations
        all_recordings = list_all_recordings()

        for rec in all_recordings:
            name = rec['name']
            path = rec['path']
            source = rec['source']  # 'user' or 'builtin'

            # Get file stats
            stat = path.stat()
            size = stat.st_size

            # Count frames (lines - 1 for header)
            with open(path, 'r') as csvfile:
                frame_count = sum(1 for _ in csvfile) - 1

            # Estimate duration at 30fps
            duration_sec = frame_count / 30.0

            animations.append({
                "name": name,
                "frames": frame_count,
                "duration": round(duration_sec, 1),
                "size_kb": round(size / 1024, 1),
                "source": source  # 'user' or 'builtin'
            })

        # Sort by name
        animations.sort(key=lambda x: x['name'])

        # Get current playing animation
        animation_service = get_animation_service()
        current = None
        if animation_service:
            current = animation_service._current_recording

        return {
            "success": True,
            "animations": animations,
            "current": current,
            "recording_active": _recording_active
        }
    except Exception as e:
        logging.error(f"Error listing animations: {e}")
        return {"success": False, "error": str(e)}


@router.post("/play")
async def play_animation(request: PlayRequest):
    """Play an animation by name."""
    global _recording_active

    try:
        # Don't allow playing animations while recording
        if _recording_active:
            return {"success": False, "error": "Cannot play animations while recording"}

        animation_service = get_animation_service()

        if not animation_service:
            return {"success": False, "error": "Animation service not available"}

        if not animation_service.robot:
            return {"success": False, "error": "Robot not connected"}

        # Check if animation exists (in user or builtin directory)
        csv_path = get_recording_path(request.name)
        if csv_path is None:
            return {"success": False, "error": f"Animation '{request.name}' not found"}

        # Play the animation
        animation_service.dispatch("play", request.name)

        return {
            "success": True,
            "name": request.name,
            "message": f"Playing animation '{request.name}'"
        }
    except Exception as e:
        logging.error(f"Error playing animation: {e}")
        return {"success": False, "error": str(e)}


@router.post("/prepare-record")
async def prepare_recording():
    """
    Prepare for recording: play sleep animation in gentle mode, then release motors.
    Call this before starting the actual recording.
    """
    global _recording_active

    try:
        if _recording_active:
            return {"success": False, "error": "Recording already in progress"}

        animation_service = get_animation_service()

        if not animation_service:
            return {"success": False, "error": "Animation service not available"}

        if not animation_service.robot:
            return {"success": False, "error": "Robot not connected"}

        # Apply gentle preset for smooth movement
        animation_service.robot.apply_preset("Gentle")
        logging.info("Applied Gentle preset for recording preparation")

        # Play sleep animation to move to neutral position
        animation_service.dispatch("play", "sleep")

        # Schedule motor release after sleep animation completes
        def release_after_animation():
            # Wait for sleep animation to finish (~3 seconds)
            time.sleep(3.5)

            if animation_service.robot and animation_service.robot.bus:
                try:
                    # Stop any animation playback first
                    animation_service._current_recording = None
                    animation_service._current_actions = []
                    animation_service._current_frame_index = 0

                    # Set manual override to prevent animation service from sending commands
                    animation_service.manual_control_override = True

                    # Now fully disable torque - motors will be completely free
                    animation_service.robot.bus.disable_torque()
                    logging.info("Motors fully released for recording (torque disabled)")
                except Exception as e:
                    logging.error(f"Error releasing motors: {e}")

        threading.Thread(target=release_after_animation, daemon=True).start()

        return {
            "success": True,
            "message": "Preparing for recording... Motors will be released in 3.5 seconds"
        }
    except Exception as e:
        logging.error(f"Error preparing recording: {e}")
        return {"success": False, "error": str(e)}


@router.post("/start-record")
async def start_recording(request: RecordRequest):
    """Start recording motor positions."""
    global _recording_active, _recording_thread, _recording_name, _recording_data, _recording_start_time

    try:
        if _recording_active:
            return {"success": False, "error": "Recording already in progress"}

        if not request.name or not request.name.strip():
            return {"success": False, "error": "Recording name is required"}

        # Sanitize name
        name = request.name.strip().replace(" ", "_").lower()

        # Check if name already exists (in either user or builtin directory)
        existing_path = get_recording_path(name)
        if existing_path is not None:
            return {"success": False, "error": f"Animation '{name}' already exists"}

        animation_service = get_animation_service()

        if not animation_service:
            return {"success": False, "error": "Animation service not available"}

        if not animation_service.robot:
            return {"success": False, "error": "Robot not connected"}

        # Start recording
        _recording_active = True
        _recording_name = name
        _recording_data = []
        _recording_start_time = time.time()

        def record_loop():
            global _recording_active, _recording_data
            fps = 30
            frame_delay = 1.0 / fps

            while _recording_active:
                try:
                    t0 = time.perf_counter()

                    # Read current positions
                    if animation_service.robot and animation_service.robot.bus:
                        positions = animation_service.robot.bus.sync_read("Present_Position")

                        # Convert to action format
                        frame = {f"{k}.pos": v for k, v in positions.items()}
                        frame["timestamp"] = time.time() - _recording_start_time
                        _recording_data.append(frame)

                    # Maintain frame rate
                    elapsed = time.perf_counter() - t0
                    if elapsed < frame_delay:
                        time.sleep(frame_delay - elapsed)

                except Exception as e:
                    logging.error(f"Error in recording loop: {e}")
                    break

        _recording_thread = threading.Thread(target=record_loop, daemon=True)
        _recording_thread.start()

        return {
            "success": True,
            "name": name,
            "message": f"Recording started for '{name}'"
        }
    except Exception as e:
        logging.error(f"Error starting recording: {e}")
        _recording_active = False
        return {"success": False, "error": str(e)}


@router.post("/stop-record")
async def stop_recording():
    """Stop recording and save to file."""
    global _recording_active, _recording_thread, _recording_name, _recording_data

    try:
        if not _recording_active:
            return {"success": False, "error": "No recording in progress"}

        # Stop recording
        _recording_active = False

        if _recording_thread:
            _recording_thread.join(timeout=2.0)
            _recording_thread = None

        if not _recording_data:
            return {"success": False, "error": "No frames recorded"}

        # Save to user recordings directory (~/.lelamp/recordings/)
        csv_path = save_recording_path(_recording_name)

        # Get fieldnames from first frame
        fieldnames = list(_recording_data[0].keys())

        with open(csv_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(_recording_data)

        logging.info(f"Saved recording to: {csv_path}")

        frame_count = len(_recording_data)
        duration = frame_count / 30.0
        name = _recording_name

        # Clear recording state
        _recording_name = None
        _recording_data = []

        # Re-enable motors with normal preset
        animation_service = get_animation_service()
        if animation_service and animation_service.robot:
            try:
                # Clear manual override so animation service can control motors again
                animation_service.manual_control_override = False

                # Re-configure motors (re-enables torque)
                animation_service.robot.configure()
                animation_service.robot.apply_preset("Normal")

                # Return to idle animation
                animation_service.dispatch("play", animation_service.idle_recording)
                logging.info("Motors re-enabled after recording")
            except Exception as e:
                logging.warning(f"Could not re-enable motors: {e}")

        return {
            "success": True,
            "name": name,
            "frames": frame_count,
            "duration": round(duration, 1),
            "message": f"Saved animation '{name}' ({frame_count} frames, {duration:.1f}s)"
        }
    except Exception as e:
        logging.error(f"Error stopping recording: {e}")
        _recording_active = False
        return {"success": False, "error": str(e)}


@router.post("/cancel-record")
async def cancel_recording():
    """Cancel recording without saving."""
    global _recording_active, _recording_thread, _recording_name, _recording_data

    try:
        _recording_active = False

        if _recording_thread:
            _recording_thread.join(timeout=2.0)
            _recording_thread = None

        _recording_name = None
        _recording_data = []

        # Re-enable motors
        animation_service = get_animation_service()
        if animation_service and animation_service.robot:
            try:
                # Clear manual override so animation service can control motors again
                animation_service.manual_control_override = False

                # Re-configure motors (re-enables torque)
                animation_service.robot.configure()
                animation_service.robot.apply_preset("Normal")
                animation_service.dispatch("play", animation_service.idle_recording)
            except Exception as e:
                logging.warning(f"Could not re-enable motors: {e}")

        return {"success": True, "message": "Recording cancelled"}
    except Exception as e:
        logging.error(f"Error cancelling recording: {e}")
        return {"success": False, "error": str(e)}


@router.get("/recording-status")
async def get_recording_status():
    """Get current recording status."""
    global _recording_active, _recording_name, _recording_data, _recording_start_time

    if not _recording_active:
        return {
            "recording": False,
            "name": None,
            "frames": 0,
            "duration": 0
        }

    frames = len(_recording_data)
    duration = time.time() - _recording_start_time if _recording_start_time else 0

    return {
        "recording": True,
        "name": _recording_name,
        "frames": frames,
        "duration": round(duration, 1)
    }


@router.delete("/{name}")
async def delete_animation(name: str):
    """Delete an animation by name (only user recordings can be deleted)."""
    try:
        # Prevent deleting essential animations
        protected = ["idle", "sleep", "wake_up"]
        if name in protected:
            return {"success": False, "error": f"Cannot delete protected animation '{name}'"}

        # Check if animation exists
        csv_path = get_recording_path(name)
        if csv_path is None:
            return {"success": False, "error": f"Animation '{name}' not found"}

        # Only allow deleting user recordings (not builtin)
        if not is_user_recording(name):
            return {"success": False, "error": f"Cannot delete builtin animation '{name}'"}

        # Delete the recording
        if not delete_recording(name):
            return {"success": False, "error": f"Failed to delete animation '{name}'"}

        # Clear from cache if animation service has it cached
        animation_service = get_animation_service()
        if animation_service and name in animation_service._recording_cache:
            del animation_service._recording_cache[name]

        return {
            "success": True,
            "name": name,
            "message": f"Deleted animation '{name}'"
        }
    except Exception as e:
        logging.error(f"Error deleting animation: {e}")
        return {"success": False, "error": str(e)}
