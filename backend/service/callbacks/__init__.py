"""
Callback service for handling alarm, timer, and workflow callbacks.

This service provides:
- Generic callbacks for timers and alarms
- Workflow-specific callback routing
- A registry for custom callbacks
"""

from .callback_service import CallbackService, get_callback_service, init_callback_service

__all__ = ["CallbackService", "get_callback_service", "init_callback_service"]
