"""
Callback service for centralized event handling.

Handles timer, alarm, and workflow callbacks with support for
workflow-specific custom callbacks.
"""

import logging
import json
import os
import time
from typing import Optional, Callable, Dict, Any

import lelamp.globals as g
from lelamp.service.theme import ThemeSound, get_theme_service

logger = logging.getLogger(__name__)

# Global callback service instance
_callback_service: Optional["CallbackService"] = None


def get_callback_service() -> Optional["CallbackService"]:
    """Get the global callback service instance."""
    return _callback_service


def init_callback_service(agent) -> "CallbackService":
    """Initialize the global callback service with an agent."""
    global _callback_service
    _callback_service = CallbackService(agent)
    return _callback_service


class CallbackService:
    """
    Centralized callback handling for timers, alarms, and workflows.

    Supports:
    - Generic callbacks for standard behavior
    - Workflow-specific callbacks loaded from workflow folders
    - Custom callback registration
    """

    def __init__(self, agent):
        """
        Initialize callback service.

        Args:
            agent: LeLamp agent instance with services and session
        """
        self.agent = agent
        self._custom_callbacks: Dict[str, Callable] = {}

        # Register with alarm service
        self._register_alarm_callbacks()

        logger.info("Callback service initialized")

    def _register_alarm_callbacks(self):
        """Register callbacks with alarm service."""
        alarm_service = g.alarm_service
        if alarm_service:
            alarm_service.on_timer_countdown = self.on_timer_countdown
            alarm_service.on_timer_complete = self.on_timer_complete
            alarm_service.on_alarm_complete = self.on_alarm_complete
            alarm_service.on_alarm_deleted = self.on_alarm_deleted
            alarm_service.on_timer_deleted = self.on_timer_deleted
            logger.info("Registered callbacks with alarm service")

    def register_callback(self, name: str, callback: Callable):
        """
        Register a custom callback.

        Args:
            name: Callback identifier (e.g., "workflow:bedside_alarm:snooze")
            callback: Callable to invoke
        """
        self._custom_callbacks[name] = callback
        logger.debug(f"Registered custom callback: {name}")

    def unregister_callback(self, name: str):
        """Remove a custom callback."""
        self._custom_callbacks.pop(name, None)

    # =========================================================================
    # Timer Callbacks
    # =========================================================================

    def on_timer_countdown(self, timer_data: dict, seconds: int):
        """Callback when timer enters countdown phase (5 seconds left)."""
        try:
            # Wake from sleep if needed
            if self.agent.is_sleeping:
                self._wake_agent()

            # Play animation
            if self.agent.animation_service:
                self.agent.animation_service.dispatch("play", "timer_up")

            # TTS countdown
            if self.agent.agent_session and self.agent.event_loop:
                def _countdown():
                    self.agent.agent_session.generate_reply(
                        instructions="Count down from 5 to 1 with dramatic pauses"
                    )
                self.agent.event_loop.call_soon_threadsafe(_countdown)

            logger.info(f"Timer countdown: {seconds}s remaining")

        except Exception as e:
            logger.error(f"Timer countdown error: {e}")

    def on_timer_complete(self, timer_data: dict):
        """Callback when a timer completes."""
        try:
            label = timer_data.get("label", "")

            # Check for workflow-specific timer handling
            if self._handle_workflow_timer(timer_data):
                return

            # Check for snooze timer (bedside alarm specific)
            if "bedside_alarm_snooze" in label.lower():
                self._handle_snooze_complete(timer_data)
                return

            # Generic timer completion
            self._play_alert()

            message = f"Your {label} timer is up!" if label else "Your timer is up!"
            self._notify_agent(message)

            logger.info(f"Timer complete: {label}")

        except Exception as e:
            logger.error(f"Timer complete error: {e}")

    def _handle_workflow_timer(self, timer_data: dict) -> bool:
        """
        Check if timer has workflow-specific handling.

        Returns True if handled by workflow callback.
        """
        label = timer_data.get("label", "")

        # Check for custom callback registered for this timer type
        for callback_name, callback in self._custom_callbacks.items():
            if callback_name.startswith("timer:") and callback_name.split(":")[1] in label.lower():
                try:
                    callback(timer_data)
                    return True
                except Exception as e:
                    logger.error(f"Custom timer callback error: {e}")

        return False

    def _handle_snooze_complete(self, timer_data: dict):
        """Handle bedside alarm snooze timer completion."""
        logger.info("Snooze timer completed - re-triggering alarm workflow")

        # Visual/audio alert
        if self.agent.rgb_service:
            self.agent.rgb_service.dispatch("animation", {
                "name": "alarm",
                "color": (255, 80, 0)
            })

        self._play_alert_loud()

        # Re-trigger workflow
        workflow_service = self.agent.workflow_service
        if workflow_service and self.agent.agent_session and self.agent.event_loop:
            workflow_service.start_workflow(
                workflow_name="bedside_alarm",
                trigger_type="snooze_trigger",
                trigger_data={
                    "snooze_timer": True,
                    "timer_label": timer_data.get("label")
                }
            )

            def _start():
                self.agent.agent_session.generate_reply(
                    instructions="SNOOZE TIME IS UP! Call get_next_step() NOW to check if user is awake!"
                )
            self.agent.event_loop.call_soon_threadsafe(_start)

    # =========================================================================
    # Alarm Callbacks
    # =========================================================================

    def on_alarm_complete(self, alarm_data: dict):
        """Callback when an alarm triggers."""
        logger.info(f"Alarm triggered: {alarm_data.get('label')}")

        try:
            # Wake from sleep
            if self.agent.is_sleeping:
                self._wake_agent()

            # Visual alarm
            if self.agent.rgb_service:
                self.agent.rgb_service.dispatch("animation", {
                    "name": "alarm",
                    "color": (255, 80, 0)
                })

            # Audio alarm (loud)
            self._play_alert_loud()

            # Try to trigger linked workflow
            workflow_triggered = self._try_trigger_alarm_workflow(alarm_data)

            # Default behavior if no workflow
            if not workflow_triggered:
                if self.agent.animation_service:
                    self.agent.animation_service.dispatch("play", "alarm")

                label = alarm_data.get("label", "Alarm")
                self._notify_agent(f"Your {label} alarm is going off!")

        except Exception as e:
            logger.error(f"Alarm complete error: {e}")

    def _try_trigger_alarm_workflow(self, alarm_data: dict) -> bool:
        """Try to trigger a workflow from alarm. Returns True if triggered."""
        workflow_service = self.agent.workflow_service
        if not workflow_service:
            return False

        alarm_workflow_id = alarm_data.get("workflow_id")

        # Check explicit workflow link
        if alarm_workflow_id:
            enabled = workflow_service.list_enabled_workflows()
            if any(wf.get('workflow_id') == alarm_workflow_id for wf in enabled):
                return self._start_alarm_workflow(alarm_workflow_id, alarm_data)

        # Default to bedside_alarm if no explicit link
        enabled = workflow_service.list_enabled_workflows()
        for wf in enabled:
            triggers_str = wf.get('triggers', '[]')
            triggers = json.loads(triggers_str) if isinstance(triggers_str, str) else triggers_str

            if 'alarm_trigger' in triggers and wf.get('workflow_id') == 'bedside_alarm':
                return self._start_alarm_workflow('bedside_alarm', alarm_data)

        return False

    def _start_alarm_workflow(self, workflow_id: str, alarm_data: dict) -> bool:
        """Start a workflow from alarm trigger."""
        workflow_service = self.agent.workflow_service

        workflow_service.start_workflow(
            workflow_name=workflow_id,
            trigger_type="alarm_trigger",
            trigger_data={
                "alarm_id": alarm_data.get("id"),
                "alarm_label": alarm_data.get("label"),
                "trigger_time": alarm_data.get("trigger_time")
            }
        )

        if self.agent.agent_session and self.agent.event_loop:
            first_step = workflow_service.get_next_step()

            def _start():
                self.agent.agent_session.generate_reply(
                    instructions=f"ALARM TRIGGERED! Workflow '{workflow_id}' started.\n\n{first_step}\n\nExecute NOW!"
                )
            self.agent.event_loop.call_soon_threadsafe(_start)

        logger.info(f"Started alarm workflow: {workflow_id}")
        return True

    def on_alarm_deleted(self, alarm_data: dict):
        """Callback when an alarm is deleted."""
        alarm_id = alarm_data.get("id")
        logger.info(f"Alarm {alarm_id} deleted")

        if self.agent.workflow_service:
            self.agent.workflow_service.cancel_workflows_for_alarm(alarm_id)

    def on_timer_deleted(self, timer_data: dict):
        """Callback when a timer is deleted."""
        timer_id = timer_data.get("id")
        logger.info(f"Timer {timer_id} deleted")

        if self.agent.workflow_service:
            self.agent.workflow_service.cancel_workflows_for_timer(timer_id)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _wake_agent(self):
        """Wake agent from sleep mode."""
        self.agent.is_sleeping = False

        config = self.agent.config
        self.agent._set_system_volume(config.get("volume", 100))

        if self.agent.animation_service:
            self.agent.animation_service.set_sleep_mode(False)

        if self.agent.rgb_service:
            self.agent.rgb_service.set_sleep_mode(False)
            rgb_config = config.get("rgb", {})
            self.agent.rgb_service.dispatch("animation", {
                "name": rgb_config.get("default_animation", "aura_glow"),
                "color": tuple(rgb_config.get("default_color", [255, 255, 255]))
            })

        # Reconfigure motors
        if self.agent.animation_service and self.agent.animation_service.robot:
            try:
                self.agent.animation_service.robot.configure()
            except Exception as e:
                logger.error(f"Motor reconfigure error: {e}")

        logger.info("Agent woken from sleep")

    def _play_alert(self):
        """Play alert sound at normal volume."""
        theme = get_theme_service()
        if theme:
            theme.play(ThemeSound.ALERT)

    def _play_alert_loud(self):
        """Play alert sound at 100% volume, then restore."""
        config = self.agent.config
        config_volume = config.get("volume", 80)

        self.agent._set_system_volume(100)
        self._play_alert()
        time.sleep(1.5)
        self.agent._set_system_volume(config_volume)

    def _notify_agent(self, message: str):
        """Have agent speak a notification message."""
        if self.agent.agent_session and self.agent.event_loop:
            def _notify():
                self.agent.agent_session.generate_reply(
                    instructions=f"Notify the user: {message}"
                )
            self.agent.event_loop.call_soon_threadsafe(_notify)
