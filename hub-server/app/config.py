"""
Hub Server Configuration

Environment variables:
- DATABASE_URL: SQLite or PostgreSQL connection string
- CLERK_SECRET_KEY: Clerk API secret key
- GCS_BUCKET: Google Cloud Storage bucket name
- GCS_CREDENTIALS: Path to GCS service account JSON
- UPLOAD_DIR: Local directory for file uploads
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Hub server settings."""

    # Database
    DATABASE_URL: str = "sqlite:///./hub.db"

    # Clerk Authentication (optional)
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""

    # Google Cloud Storage (optional)
    GCS_BUCKET: str = ""
    GCS_CREDENTIALS: str = ""  # Path to service account JSON

    # File storage
    UPLOAD_DIR: str = "./uploads"

    # Security
    API_KEY_LENGTH: int = 32
    DEVICE_API_KEY_PREFIX: str = "llhub_"

    # Rate limiting
    MAX_METRICS_PER_BATCH: int = 1000
    MAX_CONVERSATIONS_PER_BATCH: int = 100

    # Server
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()


def get_database_url() -> str:
    """Get database URL, handling SQLite path properly."""
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///./"):
        # Convert relative path to absolute
        db_path = Path(url.replace("sqlite:///./", "")).absolute()
        return f"sqlite:///{db_path}"
    return url
