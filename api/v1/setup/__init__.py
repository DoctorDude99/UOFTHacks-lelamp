"""
Setup Wizard API endpoints.

These endpoints handle the initial configuration of LeLamp:
- Environment variables (API keys)
- Personality/character settings
- Location/timezone
- Setup wizard status tracking

Note: Hardware setup (audio, motors, RGB) is handled by install scripts,
not through this API.
"""

from fastapi import APIRouter

router = APIRouter()

# Import sub-routers
from api.v1.setup.status import router as status_router
from api.v1.setup.environment import router as environment_router
from api.v1.setup.personality import router as personality_router
from api.v1.setup.location import router as location_router
from api.v1.setup.calibration import router as calibration_router
from api.v1.setup.wifi import router as wifi_router
from api.v1.setup.device import router as device_router
from api.v1.setup.ai_backend import router as ai_backend_router
from api.v1.setup.audio import router as audio_router
from api.v1.setup.camera import router as camera_router
from api.v1.setup.rgb import router as rgb_router
from api.v1.setup.livekit import router as livekit_router

# Include all setup sub-routers
router.include_router(status_router, tags=["setup-status"])
router.include_router(environment_router, prefix="/env", tags=["setup-env"])
router.include_router(personality_router, prefix="/personality", tags=["setup-personality"])
router.include_router(location_router, prefix="/location", tags=["setup-location"])
router.include_router(calibration_router, prefix="/calibration", tags=["setup-calibration"])
router.include_router(wifi_router, prefix="/wifi", tags=["setup-wifi"])
router.include_router(device_router, prefix="/device", tags=["setup-device"])
router.include_router(ai_backend_router, prefix="/ai-backend", tags=["setup-ai-backend"])
router.include_router(audio_router, prefix="/audio", tags=["setup-audio"])
router.include_router(camera_router, prefix="/camera", tags=["setup-camera"])
router.include_router(rgb_router, prefix="/rgb", tags=["setup-rgb"])
router.include_router(livekit_router, prefix="/livekit", tags=["setup-livekit"])
