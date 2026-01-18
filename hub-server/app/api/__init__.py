"""
Hub Server API routers.

Routes:
- /api/v1/devices - Device registration and management
- /api/v1/telemetry - Telemetry data upload
- /api/v1/users - User authentication and device linking
"""

from app.api import devices, telemetry, users

__all__ = ["devices", "telemetry", "users"]
