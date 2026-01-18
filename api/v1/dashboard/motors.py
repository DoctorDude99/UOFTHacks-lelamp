"""
Motor control endpoints for dashboard.

Provides real-time motor status and manual control.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

from api.deps import get_animation_service, get_lelamp_agent, load_config
from lelamp.service.motors.motors_service import fix_motor_voltage_limits

router = APIRouter()

# Motor name to ID mapping
MOTOR_NAMES = ["base_yaw", "base_pitch", "elbow_pitch", "wrist_roll", "wrist_pitch"]

# Default motor configs with limits
DEFAULT_MOTOR_CONFIGS = {
    "base_yaw": {"id": 1, "min": -180, "max": 180, "current": 0},
    "base_pitch": {"id": 2, "min": -90, "max": 90, "current": 0},
    "elbow_pitch": {"id": 3, "min": -90, "max": 90, "current": 0},
    "wrist_roll": {"id": 4, "min": -180, "max": 180, "current": 0},
    "wrist_pitch": {"id": 5, "min": -90, "max": 90, "current": 0},
}


class MotorMoveRequest(BaseModel):
    motor: str
    position: float


class ManualControlRequest(BaseModel):
    enabled: bool


@router.get("/")
async def get_motors():
    """Get motor info including current positions and limits."""
    animation = get_animation_service()
    motor_configs = {k: v.copy() for k, v in DEFAULT_MOTOR_CONFIGS.items()}

    if animation and animation.robot:
        try:
            with animation._bus_lock:
                positions = animation.robot.bus.sync_read("Present_Position")
                if positions:
                    for motor_name, pos in positions.items():
                        if motor_name in motor_configs:
                            motor_configs[motor_name]["current"] = round(pos, 1)
        except Exception as e:
            logging.error(f"Error reading motor positions: {e}")

    return motor_configs


@router.get("/positions")
async def get_motor_positions():
    """Get just the current motor positions (for real-time updates)."""
    animation = get_animation_service()
    positions = {}

    if animation and animation.robot:
        try:
            with animation._bus_lock:
                raw_positions = animation.robot.bus.sync_read("Present_Position")
                if raw_positions:
                    for motor_name, pos in raw_positions.items():
                        positions[motor_name] = round(pos, 1)
        except Exception as e:
            logging.error(f"Error reading motor positions: {e}")

    return positions


@router.post("/move")
async def move_motor(request: MotorMoveRequest):
    """Move a specific motor to position."""
    animation = get_animation_service()
    agent = get_lelamp_agent()

    if not animation or not animation.robot:
        return {"success": False, "error": "Robot not connected"}

    # Block motor control when sleeping (unless manual override is active)
    manual_override = getattr(animation, 'manual_control_override', False)
    if not manual_override and agent and agent.is_sleeping:
        return {"success": False, "error": "LeLamp is sleeping - motor control disabled"}

    try:
        action = {f"{request.motor}.pos": request.position}
        with animation._bus_lock:
            animation.robot.send_action(action)
        return {"success": True, "motor": request.motor, "position": request.position}
    except Exception as e:
        logging.error(f"Error moving motor: {e}")
        return {"success": False, "error": str(e)}


@router.post("/manual-control")
async def set_manual_control(request: ManualControlRequest):
    """Enable/disable manual motor control override.

    When enabled:
    - Pauses all AI animations (sets manual_control_override flag)
    - Applies "Normal" preset for stiff position holding (fights gravity)
    - You can move motors via sliders - they'll hold where you set them
    - Blocks animation function calls from the agent

    When disabled:
    - Resumes normal AI animation control
    - Returns to idle animation
    """
    from lelamp.service.theme import get_theme_service, ThemeSound

    animation = get_animation_service()

    if animation:
        animation.manual_control_override = request.enabled

        if request.enabled:
            # Play manual mode theme sound
            theme = get_theme_service()
            if theme:
                theme.play(ThemeSound.MANUAL_MODE)

            # Pause animations
            animation._current_recording = None
            animation._current_actions = []
            animation._current_frame_index = 0

            # Apply stiffer preset so motors hold position against gravity
            if animation.robot:
                try:
                    animation.robot.apply_preset("Normal")
                    logging.info("Applied 'Normal' preset for position holding")
                except Exception as e:
                    logging.warning(f"Could not apply preset: {e}")

            logging.info("Manual control enabled - animations paused, motors holding position")
        else:
            # Resume animations
            animation.manual_control_override = False

            # Restore normal operating preset
            if animation.robot:
                try:
                    from lelamp.globals import CONFIG
                    preset = CONFIG.get("motor_preset", "Normal")
                    animation.robot.apply_preset(preset)
                    logging.info(f"Restored '{preset}' preset")
                except Exception as e:
                    logging.warning(f"Could not restore preset: {e}")

            # Return to idle animation
            animation.dispatch("play", animation.idle_recording)
            logging.info("Manual control disabled - animations resumed")

    logging.info(f"Manual motor control override: {request.enabled}")

    return {"success": True, "enabled": request.enabled}


@router.post("/release")
async def release_motors():
    """Release all motor torque (make motors limp)."""
    animation = get_animation_service()

    manual_override = getattr(animation, 'manual_control_override', False) if animation else False
    if not manual_override:
        return {"success": False, "error": "Manual control must be enabled first"}

    if not animation or not animation.robot:
        return {"success": False, "error": "Robot not connected"}

    try:
        robot = animation.robot
        with animation._bus_lock:
            for motor_name in MOTOR_NAMES:
                motor = getattr(robot.motors, motor_name, None)
                if motor:
                    motor.torque_enable = False

        logging.info("All motor torque released")
        return {"success": True, "message": "Motor torque released"}
    except Exception as e:
        logging.error(f"Error releasing motors: {e}")
        return {"success": False, "error": str(e)}


@router.get("/status")
async def get_motor_status():
    """Get motor service status."""
    animation = get_animation_service()

    return {
        "success": True,
        "connected": animation is not None and animation.robot is not None,
        "manual_control": getattr(animation, 'manual_control_override', False) if animation else False,
        "pushable_mode": animation.is_pushable_mode() if animation else False
    }


class PushableModeRequest(BaseModel):
    enabled: bool


@router.post("/pushable-mode")
async def set_pushable_mode(request: PushableModeRequest):
    """Enable/disable pushable mode.

    When enabled:
    - Pauses all AI animations
    - Makes motors compliant so user can physically move the lamp
    - Lamp holds whatever position you move it to

    When disabled:
    - Resumes normal AI animation control
    - Returns to idle animation
    """
    from lelamp.service.theme import get_theme_service, ThemeSound

    animation = get_animation_service()

    if not animation:
        logging.error("Pushable mode: animation service not available")
        return {"success": False, "error": "Animation service not available"}

    if not animation.robot:
        logging.error("Pushable mode: robot not connected")
        return {"success": False, "error": "Robot not connected"}

    try:
        if request.enabled:
            logging.info("Enabling pushable mode...")
            success = animation.enable_pushable_mode()
            logging.info(f"Pushable mode enable result: {success}")
            if success:
                # Play pushable mode theme sound
                theme = get_theme_service()
                if theme:
                    theme.play(ThemeSound.PUSHABLE)
                return {"success": True, "enabled": True, "message": "Pushable mode enabled - you can now move the lamp by hand"}
            else:
                return {"success": False, "error": "Failed to enable pushable mode"}
        else:
            logging.info("Disabling pushable mode...")
            success = animation.disable_pushable_mode(return_to_idle=True)
            logging.info(f"Pushable mode disable result: {success}")
            if success:
                return {"success": True, "enabled": False, "message": "Pushable mode disabled - animations resumed"}
            else:
                return {"success": False, "error": "Failed to disable pushable mode"}
    except Exception as e:
        logging.error(f"Error setting pushable mode: {e}")
        return {"success": False, "error": str(e)}


class FixVoltageLimitsRequest(BaseModel):
    voltage: str  # "7.4" or "12"


@router.post("/fix-voltage-limits")
async def fix_voltage_limits(request: FixVoltageLimitsRequest):
    """
    Fix motor voltage limits for all connected motors.

    Args:
        voltage: "7.4" for 7.4V servos or "12" for 12V servos

    This will:
    - Scan all motors (IDs 1-5)
    - Set min voltage limit to 4.5V
    - Set max voltage limit to 8.0V (7.4V) or 14.0V (12V)
    - Write to motor EEPROM (persistent)
    """
    config = load_config()
    port = config.get("motors", {}).get("port", "/dev/lelamp")

    # Disconnect robot if connected to avoid conflicts
    animation = get_animation_service()
    robot_was_connected = False

    if animation and animation.robot and animation.robot.is_connected:
        robot_was_connected = True
        logging.info("Temporarily disconnecting robot for voltage fix...")
        try:
            animation.robot.disconnect()
        except Exception as e:
            logging.warning(f"Error disconnecting robot: {e}")

    try:
        result = fix_motor_voltage_limits(port, request.voltage)

        # Reconnect robot if it was connected
        if robot_was_connected and animation and animation.robot:
            logging.info("Reconnecting robot after voltage fix...")
            try:
                animation.robot.connect()
            except Exception as e:
                logging.warning(f"Error reconnecting robot: {e}")
                result["reconnect_warning"] = f"Robot reconnect failed: {e}"

        return result

    except Exception as e:
        logging.error(f"Error fixing voltage limits: {e}")
        return {"success": False, "error": str(e)}
