"""
Dashboard API endpoints.

These endpoints power the main LeLamp dashboard:
- System status
- Motor status and control
- Vision/tracking status
- Settings management
"""

from fastapi import APIRouter

router = APIRouter()

# Import sub-routers
from api.v1.dashboard.status import router as status_router
from api.v1.dashboard.settings import router as settings_router
from api.v1.dashboard.tracking import router as tracking_router
from api.v1.dashboard.motors import router as motors_router
from api.v1.dashboard.services import router as services_router
from api.v1.dashboard.theme import router as theme_router
from api.v1.dashboard.animations import router as animations_router

router.include_router(status_router, tags=["dashboard-status"])
router.include_router(settings_router, prefix="/settings", tags=["dashboard-settings"])
router.include_router(tracking_router, prefix="/tracking", tags=["dashboard-tracking"])
router.include_router(motors_router, prefix="/motors", tags=["dashboard-motors"])
router.include_router(services_router, prefix="/services", tags=["dashboard-services"])
router.include_router(theme_router, prefix="/theme", tags=["dashboard-theme"])
router.include_router(animations_router, prefix="/animations", tags=["dashboard-animations"])
