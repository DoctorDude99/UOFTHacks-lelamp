"""
Agent control endpoints.

Wake, sleep, and shutdown control for the LeLamp agent.
"""

import subprocess
import asyncio

from fastapi import APIRouter

from api.deps import get_lelamp_agent, get_agent_session, load_config, save_config

router = APIRouter()


@router.post("/wake")
async def wake_up():
    """Wake up LeLamp from sleep mode."""
    try:
        agent = get_lelamp_agent()
        if not agent:
            return {"success": False, "error": "Agent not running"}

        if hasattr(agent, 'wake_up'):
            await agent.wake_up()
            return {"success": True, "message": "LeLamp is waking up"}
        else:
            return {"success": False, "error": "Wake method not available"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/sleep")
async def go_to_sleep():
    """Put LeLamp into sleep mode."""
    try:
        agent = get_lelamp_agent()
        if not agent:
            return {"success": False, "error": "Agent not running"}

        if hasattr(agent, 'go_to_sleep'):
            await agent.go_to_sleep()
            return {"success": True, "message": "LeLamp is going to sleep"}
        else:
            return {"success": False, "error": "Sleep method not available"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/status")
async def get_agent_status():
    """Get current agent status (awake/sleeping)."""
    try:
        agent = get_lelamp_agent()
        if not agent:
            return {"success": True, "running": False, "sleeping": False}

        return {
            "success": True,
            "running": True,
            "sleeping": getattr(agent, 'is_sleeping', False)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/shutdown")
async def shutdown():
    """Shutdown LeLamp gracefully."""
    try:
        agent = get_lelamp_agent()
        if agent and hasattr(agent, 'shutdown'):
            # Give time for response before shutdown
            asyncio.create_task(_delayed_shutdown(agent))
            return {"success": True, "message": "Shutting down..."}
        return {"success": False, "error": "Agent not available"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _delayed_shutdown(agent):
    """Delayed shutdown to allow HTTP response to complete."""
    await asyncio.sleep(1)
    await agent.shutdown()


@router.get("/enabled")
async def get_agent_enabled():
    """Check if agent is enabled in config."""
    try:
        config = load_config()
        enabled = config.get("agent", {}).get("enabled", False)
        return {"success": True, "enabled": enabled}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/enable")
async def enable_agent():
    """Enable the AI agent in config (requires service restart)."""
    try:
        config = load_config()
        config.setdefault("agent", {})
        config["agent"]["enabled"] = True
        save_config(config)
        return {
            "success": True,
            "message": "Agent enabled. Restart the service for changes to take effect.",
            "enabled": True
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/disable")
async def disable_agent():
    """Disable the AI agent in config (requires service restart)."""
    try:
        config = load_config()
        config.setdefault("agent", {})
        config["agent"]["enabled"] = False
        save_config(config)
        return {
            "success": True,
            "message": "Agent disabled. Restart the service for changes to take effect.",
            "enabled": False
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/restart-service")
async def restart_service():
    """Restart the LeLamp systemd service."""
    try:
        # Schedule restart after response
        asyncio.create_task(_delayed_service_restart())
        return {"success": True, "message": "Service restart initiated..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _delayed_service_restart():
    """Delayed service restart to allow HTTP response to complete."""
    await asyncio.sleep(1)
    subprocess.run(["sudo", "systemctl", "restart", "lelamp.service"], check=False)


@router.post("/reboot")
async def reboot_system():
    """Reboot the Raspberry Pi."""
    try:
        asyncio.create_task(_delayed_system_reboot())
        return {"success": True, "message": "System rebooting..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _delayed_system_reboot():
    """Delayed reboot to allow HTTP response to complete."""
    await asyncio.sleep(2)
    subprocess.run(["sudo", "reboot"], check=False)


@router.post("/poweroff")
async def poweroff_system():
    """Power off the Raspberry Pi."""
    try:
        asyncio.create_task(_delayed_system_poweroff())
        return {"success": True, "message": "System powering off..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _delayed_system_poweroff():
    """Delayed poweroff to allow HTTP response to complete."""
    await asyncio.sleep(2)
    subprocess.run(["sudo", "poweroff"], check=False)
