"""
Agent control API endpoints.

These endpoints control the LeLamp agent:
- Wake/sleep control
- Shutdown
- Character/personality switching
"""

from fastapi import APIRouter

router = APIRouter()

from api.v1.agent.control import router as control_router

router.include_router(control_router, tags=["agent-control"])
