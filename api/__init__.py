"""
LeLamp API - Clean, modular REST API

Structure:
    api/
    ├── __init__.py          # This file - app factory
    ├── deps.py              # Dependency injection
    └── v1/
        ├── setup/           # Setup wizard endpoints
        ├── dashboard/       # Dashboard/monitoring endpoints
        ├── agent/           # Agent control (wake/sleep)
        ├── spotify/         # Spotify OAuth and playback
        └── ...

Usage:
    from api import create_api
    app = create_api()
"""

import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv

import lelamp.globals as g
from lelamp.user_data import get_env_path


def create_api(
    title: str = "LeLamp API",
    version: str = "1.0.0",
    vision_service=None,
) -> FastAPI:
    """
    Factory function to create the FastAPI application.

    Args:
        title: API title
        version: API version
        vision_service: Optional vision service instance for video streaming

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title=title,
        version=version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Share vision service with globals
    if vision_service is not None:
        g.vision_service = vision_service

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    from api.v1 import router as v1_router
    app.include_router(v1_router, prefix="/api/v1")

    # Include WebSocket handlers
    from api.websocket import router as ws_router
    app.include_router(ws_router, prefix="/ws", tags=["websocket"])

    # Include video streaming
    from lelamp.service.webui.video import router as video_router
    app.include_router(video_router, tags=["video"])

    # Health check endpoint
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "version": version}

    # Paths
    base_dir = Path(__file__).parent.parent
    dist_dir = base_dir / "frontend" / "dist"
    assets_dir = base_dir / "assets"

    # Mount assets
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Mount dist-assets for React bundles
    dist_assets = dist_dir / "dist-assets"
    if dist_assets.exists():
        app.mount("/dist-assets", StaticFiles(directory=dist_assets), name="dist-assets")

    # Serve static files from dist root (favicon, lelamp.svg, etc.)
    @app.get("/lelamp.svg")
    async def serve_lelamp_svg():
        svg_path = dist_dir / "lelamp.svg"
        if svg_path.exists():
            return FileResponse(svg_path, media_type="image/svg+xml")
        return FileResponse(assets_dir / "images" / "lelamp.svg", media_type="image/svg+xml")

    @app.get("/vite.svg")
    async def serve_vite_svg():
        return FileResponse(dist_dir / "vite.svg", media_type="image/svg+xml")

    # Root route - redirect to dashboard or setup
    @app.get("/")
    async def root():
        """Redirect to dashboard or setup based on config."""
        env_path = get_env_path()
        if env_path.exists():
            load_dotenv(env_path, override=True)
        else:
            load_dotenv(override=True)

        cfg = g.CONFIG or {}
        setup = cfg.get("setup", {})

        if not setup.get("setup_complete", False):
            return RedirectResponse(url="/setup", status_code=302)

        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not openai_key or len(openai_key) < 20:
            return RedirectResponse(url="/setup", status_code=302)

        if g.calibration_required:
            return RedirectResponse(url="/setup", status_code=302)

        return RedirectResponse(url="/dashboard", status_code=302)

    # Serve React SPA for frontend routes
    @app.get("/setup")
    @app.get("/dashboard")
    @app.get("/settings")
    async def serve_spa():
        """Serve the React SPA."""
        if dist_dir.exists() and (dist_dir / "index.html").exists():
            return FileResponse(dist_dir / "index.html")
        return HTMLResponse(
            content="<h1>LeLamp</h1><p>Frontend not built. Run: cd frontend && npm run build</p>"
        )

    # API docs redirect
    @app.get("/api/v1/docs")
    async def api_docs_redirect():
        """Redirect to main API documentation."""
        return RedirectResponse(url="/api/docs", status_code=302)

    return app


# Convenience export
__all__ = ["create_api"]
