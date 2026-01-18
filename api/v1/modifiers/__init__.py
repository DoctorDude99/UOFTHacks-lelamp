"""
Animation modifier API endpoints.

Provides control over animation modifiers like music/dance mode.
"""

from fastapi import APIRouter

router = APIRouter()

from api.v1.modifiers.music import router as music_router
from api.v1.modifiers.dance import router as dance_router

router.include_router(music_router, prefix="/music", tags=["modifiers-music"])
router.include_router(dance_router, prefix="/dance", tags=["modifiers-dance"])
