"""
LeLamp Hub Server

Central server for device registration, telemetry collection, and user management.

Features:
- Device registration with hardware serial numbers
- Telemetry data collection (metrics, conversations, audio)
- Clerk authentication for user accounts
- Google Cloud Storage for media files

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8000
    # or
    python main.py
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import devices, telemetry, users

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup
    logger.info("LeLamp Hub Server starting...")
    logger.info(f"Database: {settings.DATABASE_URL}")

    # Initialize database
    from app.models import init_db
    init_db()

    # Create upload directories
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    logger.info("Hub server ready")
    yield

    # Shutdown
    logger.info("Hub server shutting down...")


# Create FastAPI app
app = FastAPI(
    title="LeLamp Hub",
    description="Central server for LeLamp device management and telemetry",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(devices.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(telemetry.router, prefix="/api/v1/telemetry", tags=["telemetry"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])


@app.get("/")
async def root():
    """Root endpoint with server info."""
    return {
        "name": "LeLamp Hub",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/v1/stats")
async def get_stats():
    """Get hub statistics."""
    from app.models import get_db, Device, SystemMetric, ConversationTurn
    from sqlalchemy import func

    db = next(get_db())
    try:
        device_count = db.query(func.count(Device.serial)).scalar()
        metric_count = db.query(func.count(SystemMetric.id)).scalar()
        turn_count = db.query(func.count(ConversationTurn.id)).scalar()

        return {
            "devices_registered": device_count or 0,
            "metrics_collected": metric_count or 0,
            "conversation_turns": turn_count or 0
        }
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True
    )
