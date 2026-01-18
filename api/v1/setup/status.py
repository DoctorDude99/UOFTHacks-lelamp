"""
Setup wizard status endpoints.

Tracks the progress of the setup wizard and manages step completion.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Optional

from api.deps import load_config, save_config

router = APIRouter()


class StepUpdate(BaseModel):
    step: str


class StepComplete(BaseModel):
    step: str


class StepSkip(BaseModel):
    step: str
    disable_feature: str = None  # Optional feature to disable (e.g., "motors", "wifi")


@router.get("/status")
async def get_setup_status():
    """Get current setup wizard status and progress."""
    try:
        config = load_config()
        setup = config.get('setup', {})
        return {
            "success": True,
            "first_boot": setup.get('first_boot', False),
            "setup_complete": setup.get('setup_complete', False),
            "current_step": setup.get('current_step', 'welcome'),
            "steps_completed": setup.get('steps_completed', {}),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/step")
async def update_setup_step(data: StepUpdate):
    """Update current setup step."""
    try:
        config = load_config()
        config.setdefault('setup', {})
        config['setup']['current_step'] = data.step
        save_config(config)
        return {"success": True, "step": data.step}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/complete-step")
async def complete_setup_step(data: StepComplete):
    """Mark a setup step as completed."""
    try:
        if not data.step:
            return {"success": False, "error": "No step specified"}

        config = load_config()
        config.setdefault('setup', {})
        config['setup'].setdefault('steps_completed', {})
        config['setup']['steps_completed'][data.step] = True
        save_config(config)

        return {"success": True, "step": data.step, "completed": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/finish")
async def finish_setup():
    """Mark setup as complete."""
    try:
        config = load_config()
        config.setdefault('setup', {})
        config['setup']['setup_complete'] = True
        config['setup']['first_boot'] = False
        config['setup']['current_step'] = 'complete'
        save_config(config)

        return {"success": True, "message": "Setup complete!"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/restart")
async def restart_setup():
    """Restart setup wizard from beginning."""
    try:
        config = load_config()
        config['setup'] = {
            'first_boot': False,
            'setup_complete': False,
            'current_step': 'welcome',
            'steps_completed': {
                'environment': False,
                'location': False,
                'personality': False
            },
        }
        save_config(config)

        return {"success": True, "message": "Setup wizard restarted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/skip-step")
async def skip_setup_step(data: StepSkip):
    """
    Skip a setup step and optionally disable a related feature.

    For example, skipping motor calibration can disable motors.enabled,
    skipping WiFi setup can mark wifi as using local-only mode.
    """
    try:
        if not data.step:
            return {"success": False, "error": "No step specified"}

        config = load_config()
        config.setdefault('setup', {})
        config['setup'].setdefault('steps_completed', {})
        config['setup'].setdefault('steps_skipped', {})

        # Mark step as skipped (not completed)
        config['setup']['steps_skipped'][data.step] = True
        config['setup']['steps_completed'][data.step] = True  # Allow progression

        # Handle feature disabling based on skip
        message = f"Skipped {data.step}"

        if data.disable_feature:
            feature = data.disable_feature.lower()

            if feature == "motors":
                config.setdefault('motors', {})
                config['motors']['enabled'] = False
                message += " - motors disabled"

            elif feature == "wifi":
                config.setdefault('wifi', {})
                config['wifi']['enabled'] = False
                config['wifi']['configured'] = False
                message += " - WiFi setup skipped (local-only mode)"

            elif feature == "agent":
                config.setdefault('agent', {})
                config['agent']['enabled'] = False
                message += " - AI agent disabled"

            elif feature == "face_tracking":
                config.setdefault('face_tracking', {})
                config['face_tracking']['enabled'] = False
                message += " - face tracking disabled"

            elif feature == "rgb":
                config.setdefault('rgb', {})
                config['rgb']['enabled'] = False
                message += " - RGB lights disabled"

        save_config(config)

        return {
            "success": True,
            "step": data.step,
            "skipped": True,
            "disabled_feature": data.disable_feature,
            "message": message
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
