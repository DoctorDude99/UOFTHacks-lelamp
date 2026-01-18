"""
LeLamp API v1

All v1 endpoints are assembled here into a single router.
"""

from fastapi import APIRouter, Depends

from api.auth import require_auth

router = APIRouter(tags=["v1"])

# Import and include domain routers
from api.v1.setup import router as setup_router
from api.v1.dashboard import router as dashboard_router
from api.v1.agent import router as agent_router
from api.v1.workflows import router as workflows_router
from api.v1.modifiers import router as modifiers_router
from api.v1.system import router as system_router
from api.v1.characters import router as characters_router
from api.v1.spotify import router as spotify_router
from api.v1.auth import router as auth_router

# Auth routes are always public (needed to authenticate)
router.include_router(auth_router, prefix="/auth", tags=["auth"])

# Setup routes are protected (has camera access!)
# Note: require_auth allows access if auth is not yet configured (first boot)
router.include_router(
    setup_router,
    prefix="/setup",
    tags=["setup"],
    dependencies=[Depends(require_auth)]
)

# Protected routes (require authentication)
# Note: require_auth handles local network bypass automatically
router.include_router(
    dashboard_router,
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth)]
)
router.include_router(
    agent_router,
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(require_auth)]
)
router.include_router(
    workflows_router,
    prefix="/workflows",
    tags=["workflows"],
    dependencies=[Depends(require_auth)]
)
router.include_router(
    modifiers_router,
    prefix="/modifiers",
    tags=["modifiers"],
    dependencies=[Depends(require_auth)]
)
router.include_router(
    system_router,
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(require_auth)]
)
router.include_router(
    characters_router,
    prefix="/characters",
    tags=["characters"],
    dependencies=[Depends(require_auth)]
)
router.include_router(
    spotify_router,
    prefix="/spotify",
    tags=["spotify"],
    dependencies=[Depends(require_auth)]
)


@router.get("/health")
async def health_check():
    """API health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}
