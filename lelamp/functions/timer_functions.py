"""
Timer and alarm function tools for LeLamp

This module contains all timer/alarm-related function tools including:
- Timer management (set, cancel, list)
- Alarm management (set, list, enable, disable, delete)
"""

import logging
from typing import Union
from datetime import datetime, timedelta
from lelamp.service.agent.tools import Tool


class TimerFunctions:
    """Mixin class providing timer and alarm function tools"""

    @Tool.register_tool
    async def set_timer(self, duration_seconds: Union[int, float], label: str = None) -> str:
        """
        Set a countdown timer! Use this when someone asks you to set a timer or remind them
        after a certain duration. When the timer completes, an alert sound will play and you
        should notify them their timer is up.

        Perfect for: cooking timers, workout intervals, meditation sessions, reminders to
        check on something, tea brewing, egg boiling, or any timed activity.

        Examples:
        - "Set a timer for 10 seconds" -> duration_seconds=10
        - "Timer for 5 minutes" -> duration_seconds=300
        - "Set a 1 hour timer for laundry" -> duration_seconds=3600, label="laundry"

        Args:
            duration_seconds: How long the timer should run in seconds
            label: Optional name/description for the timer (e.g., "pasta", "workout")

        Returns:
            Confirmation message with timer ID and details
        """
        from lelamp.globals import alarm_service

        print(f"LeLamp: set_timer called with duration={duration_seconds}s, label={label}")
        try:
            if duration_seconds <= 0:
                return "Error: Timer duration must be positive"

            timer_id = alarm_service.create_timer(duration_seconds, label)

            # Format duration for human readability
            if duration_seconds < 60:
                duration_str = f"{duration_seconds} seconds"
            elif duration_seconds < 3600:
                minutes = duration_seconds / 60
                duration_str = f"{minutes:.1f} minutes"
            else:
                hours = duration_seconds / 3600
                duration_str = f"{hours:.1f} hours"

            label_str = f" ({label})" if label else ""
            return f"Timer set for {duration_str}{label_str}! I'll alert you when it's done. (Timer ID: {timer_id})"
        except Exception as e:
            return f"Error setting timer: {str(e)}"

    @Tool.register_tool
    async def cancel_timer(self, timer_id: int) -> str:
        """
        Cancel an active timer. Use this when someone asks you to stop, cancel, or end
        a timer before it completes.

        Args:
            timer_id: The ID of the timer to cancel (from when it was created)

        Returns:
            Confirmation of cancellation or error if timer not found/active
        """
        from lelamp.globals import alarm_service

        print(f"LeLamp: cancel_timer called with timer_id={timer_id}")
        try:
            success = alarm_service.cancel_timer(timer_id)
            if success:
                return f"Timer {timer_id} has been cancelled."
            else:
                return f"Timer {timer_id} not found or already completed/cancelled."
        except Exception as e:
            return f"Error cancelling timer: {str(e)}"

    @Tool.register_tool
    async def list_timers(self) -> str:
        """
        Check all active timers. Use this when someone asks what timers are running,
        how much time is left, or wants to see their active timers.

        Returns:
            List of active timers with time remaining, or message if no active timers
        """
        from lelamp.globals import alarm_service

        print("LeLamp: list_timers called")
        try:
            active_timers = alarm_service.get_active_timers()

            if not active_timers:
                return "No active timers right now."

            timer_list = []
            for timer in active_timers:
                remaining = timer['remaining_seconds']

                # Format remaining time
                if remaining < 60:
                    time_str = f"{remaining:.0f} seconds"
                elif remaining < 3600:
                    minutes = remaining / 60
                    time_str = f"{minutes:.1f} minutes"
                else:
                    hours = remaining / 3600
                    time_str = f"{hours:.1f} hours"

                label_str = f" - {timer['label']}" if timer['label'] else ""
                timer_list.append(f"Timer {timer['id']}{label_str}: {time_str} remaining")

            return "Active timers:\n" + "\n".join(timer_list)
        except Exception as e:
            return f"Error listing timers: {str(e)}"

    @Tool.register_tool
    async def set_alarm(
        self,
        time_str: str,
        label: str,
        repeat: str = "once"
    ) -> str:
        """
        Set an alarm for a specific time! Use this when someone asks you to set an alarm
        for a particular time (like "7:30am tomorrow" or "Monday at 9am").

        When the alarm goes off, the alarm animation will play, an alert sound, and you'll
        notify them.

        Examples:
        - "Set an alarm for 7:30am tomorrow" -> time_str="7:30am tomorrow", repeat="once"
        - "Wake me up at 6am every weekday" -> time_str="6am", repeat="weekdays"
        - "Alarm for 9pm on Mondays and Fridays" -> time_str="9pm", repeat="mon,fri"

        Args:
            time_str: Time description (e.g., "7:30am", "3:15pm tomorrow", "6am")
            label: Name for the alarm (e.g., "wake up", "meeting", "medication")
            repeat: Repeat pattern - "once", "daily", "weekdays", "weekends", or days like "mon,wed,fri"

        Returns:
            Confirmation message with alarm details
        """
        from lelamp.globals import CONFIG, alarm_service
        from dateutil import parser
        import pytz

        print(f"LeLamp: set_alarm called with time_str={time_str}, label={label}, repeat={repeat}")
        try:
            # Get timezone from config
            location = CONFIG.get("location", {})
            tz_name = location.get("timezone", "UTC")
            tz = pytz.timezone(tz_name)

            # Parse the time string
            try:
                # Try to parse relative times like "tomorrow at 7am"
                trigger_time = parser.parse(time_str, fuzzy=True)

                # If no date was specified, assume today or tomorrow
                now = datetime.now(tz)
                if trigger_time.date() == datetime(1900, 1, 1).date():
                    # Default date from parser, use today
                    trigger_time = trigger_time.replace(
                        year=now.year,
                        month=now.month,
                        day=now.day
                    )
                    # If time has passed today, move to tomorrow
                    if trigger_time.time() < now.time():
                        trigger_time = trigger_time + timedelta(days=1)

                # Make timezone aware
                if trigger_time.tzinfo is None:
                    trigger_time = tz.localize(trigger_time)

            except Exception as e:
                return f"Error parsing time '{time_str}': {str(e)}. Try formats like '7:30am', '3pm tomorrow', etc."

            # Normalize repeat pattern - treat 'once', 'none', 'no', empty as one-time alarm
            repeat_lower = repeat.lower().strip() if repeat else ""
            repeat_pattern = None if repeat_lower in ("once", "none", "no", "") else repeat_lower

            # Check if we're in a workflow context and link alarm to it
            workflow_id = None
            try:
                from lelamp.globals import workflow_service
                if workflow_service and workflow_service.active_workflow:
                    # active_workflow is the workflow name (string)
                    workflow_id = workflow_service.active_workflow
                    print(f"LeLamp: Linking alarm to active workflow: {workflow_id}")
            except Exception as e:
                print(f"LeLamp: Could not link alarm to workflow: {e}")

            # Create the alarm
            alarm_id = alarm_service.create_alarm(trigger_time, label, repeat_pattern, workflow_id)

            # Format response
            time_format = trigger_time.strftime("%I:%M %p on %A, %B %d")
            if repeat_pattern:
                if repeat_pattern == "daily":
                    repeat_str = "every day"
                elif repeat_pattern == "weekdays":
                    repeat_str = "every weekday"
                elif repeat_pattern == "weekends":
                    repeat_str = "every weekend"
                else:
                    repeat_str = f"on {repeat_pattern}"
                return f"Alarm '{label}' set for {time_format}, repeating {repeat_str}. (Alarm ID: {alarm_id})"
            else:
                return f"Alarm '{label}' set for {time_format}. (Alarm ID: {alarm_id})"

        except Exception as e:
            return f"Error setting alarm: {str(e)}"

    @Tool.register_tool
    async def list_alarms(self) -> str:
        """
        List all alarms. Use this when someone asks what alarms are set, wants to see
        their alarms, or asks about a specific alarm.

        Returns:
            List of alarms with their details, or message if no alarms
        """
        from lelamp.globals import alarm_service

        print("LeLamp: list_alarms called")
        try:
            alarms = alarm_service.get_alarms()

            if not alarms:
                return "No alarms set."

            alarm_list = []
            for alarm in alarms:
                trigger_dt = datetime.fromtimestamp(alarm['trigger_time'])
                time_str = trigger_dt.strftime("%I:%M %p")

                repeat = alarm['repeat_pattern']
                if repeat:
                    if repeat == "daily":
                        repeat_str = "daily"
                    elif repeat == "weekdays":
                        repeat_str = "weekdays"
                    elif repeat == "weekends":
                        repeat_str = "weekends"
                    else:
                        repeat_str = repeat
                    time_str += f" ({repeat_str})"
                else:
                    time_str += f" on {trigger_dt.strftime('%A, %B %d')}"

                state_emoji = "✓" if alarm['state'] == 'enabled' else "✗"
                alarm_list.append(
                    f"{state_emoji} Alarm {alarm['id']}: {alarm['label']} at {time_str}"
                )

            return "Your alarms:\n" + "\n".join(alarm_list)
        except Exception as e:
            return f"Error listing alarms: {str(e)}"

    @Tool.register_tool
    async def enable_alarm(self, alarm_id: int) -> str:
        """
        Enable a disabled alarm. Use this when someone asks you to turn on,
        enable, or activate an alarm.

        Args:
            alarm_id: The ID of the alarm to enable

        Returns:
            Confirmation message
        """
        from lelamp.globals import alarm_service

        print(f"LeLamp: enable_alarm called with alarm_id={alarm_id}")
        try:
            success = alarm_service.enable_alarm(alarm_id)
            if success:
                return f"Alarm {alarm_id} has been enabled."
            else:
                return f"Alarm {alarm_id} not found."
        except Exception as e:
            return f"Error enabling alarm: {str(e)}"

    @Tool.register_tool
    async def disable_alarm(self, alarm_id: int) -> str:
        """
        Disable an enabled alarm. Use this when someone asks you to turn off,
        disable, or deactivate an alarm. The alarm is saved but won't trigger.

        Args:
            alarm_id: The ID of the alarm to disable

        Returns:
            Confirmation message
        """
        from lelamp.globals import alarm_service, workflow_service

        print(f"LeLamp: disable_alarm called with alarm_id={alarm_id}")
        try:
            success = alarm_service.disable_alarm(alarm_id)
            if success:
                # Check if there's an active workflow triggered by this alarm
                if workflow_service:
                    self._cancel_alarm_workflows(alarm_id, "disabled")

                return f"Alarm {alarm_id} has been disabled."
            else:
                return f"Alarm {alarm_id} not found."
        except Exception as e:
            return f"Error disabling alarm: {str(e)}"

    @Tool.register_tool
    async def delete_alarm(self, alarm_id: int) -> str:
        """
        Permanently delete an alarm. Use this when someone asks you to remove,
        delete, or get rid of an alarm completely.

        Args:
            alarm_id: The ID of the alarm to delete

        Returns:
            Confirmation message
        """
        from lelamp.globals import alarm_service, workflow_service

        print(f"LeLamp: delete_alarm called with alarm_id={alarm_id}")
        try:
            success = alarm_service.delete_alarm(alarm_id)
            if success:
                # Check if there's an active workflow triggered by this alarm
                if workflow_service:
                    self._cancel_alarm_workflows(alarm_id, "deleted")

                return f"Alarm {alarm_id} has been deleted."
            else:
                return f"Alarm {alarm_id} not found."
        except Exception as e:
            return f"Error deleting alarm: {str(e)}"

    def _cancel_alarm_workflows(self, alarm_id: int, reason: str):
        """
        Cancel any active workflows that were triggered by this alarm.

        Args:
            alarm_id: The alarm ID that triggered workflows
            reason: Why the workflows are being cancelled ("disabled" or "deleted")
        """
        from lelamp.globals import workflow_service
        import json
        import logging

        try:
            if not workflow_service:
                return

            # Get all active workflow runs
            active_runs = workflow_service.db.get_active_runs()

            for run in active_runs:
                run_id = run.get('run_id')
                workflow_id = run.get('workflow_id')
                trigger_type = run.get('trigger_type')
                trigger_data_str = run.get('trigger_data', '{}')

                # Check if this run was triggered by the alarm
                if trigger_type == "alarm_trigger":
                    try:
                        trigger_data = json.loads(trigger_data_str) if isinstance(trigger_data_str, str) else trigger_data_str
                        if trigger_data.get('alarm_id') == alarm_id:
                            logging.info(f"🛑 Cancelling workflow '{workflow_id}' (run {run_id}) because alarm {alarm_id} was {reason}")

                            # Stop the workflow if it's currently active
                            if workflow_service.current_run_id == run_id:
                                from lelamp.service.workflows.db_manager import RunStatus
                                workflow_service.stop_workflow(RunStatus.CANCELLED)
                            else:
                                # Mark as cancelled in database
                                from lelamp.service.workflows.db_manager import RunStatus
                                workflow_service.db.complete_run(run_id, RunStatus.CANCELLED)
                    except Exception as e:
                        logging.error(f"Error checking workflow trigger data: {e}")

        except Exception as e:
            logging.error(f"Error cancelling alarm workflows: {e}")
