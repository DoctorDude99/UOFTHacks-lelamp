"""
Workflow management function tools for LeLamp

This module contains all workflow-related function tools including:
- Getting available workflows
- Starting workflows
- Managing workflow execution (steps, status)
"""

import logging
from typing import Optional, Dict
from lelamp.service.agent.tools import Tool


class WorkflowFunctions:
    """Mixin class providing workflow management function tools"""

    @Tool.register_tool
    async def get_available_workflows(self) -> str:
        """
        Discover what workflows you can execute! Get your repertoire of multi-step workflows.
        Use this when someone asks you about your capabilities or when they ask you to execute
        a workflow. Each workflow is a user-defined sequence of steps - like waking up the user,
        running a focus session, or executing a bedside alarm routine.

        Returns:
            List of available workflow names you can execute.
        """
        print("LeLamp: get_available_workflows function called")
        try:
            workflows = self.workflow_service.get_available_workflows()

            if workflows:
                result = f"Available workflows: {', '.join(workflows)}"
                return result
            else:
                result = "No workflows found."
                return result
        except Exception as e:
            result = f"Error getting workflows: {str(e)}"
            return result

    @Tool.register_tool
    async def list_enabled_workflows(self) -> str:
        """
        Get list of enabled workflows with their current status and metadata. Use this
        to see which workflows are active, their descriptions, and recent run history.
        Great for understanding what workflows are available and what they do.

        Returns:
            Detailed information about enabled workflows including status and descriptions.
        """
        print("LeLamp: list_enabled_workflows function called")
        try:
            workflows = self.workflow_service.list_enabled_workflows()

            if not workflows:
                return "No enabled workflows found."

            result_lines = ["Enabled workflows:"]
            for wf in workflows:
                name = wf.get('name', wf.get('workflow_id', 'Unknown'))
                desc = wf.get('description', 'No description')
                enabled = "✓" if wf.get('enabled') else "✗"
                result_lines.append(f"{enabled} {name}: {desc}")

            return "\n".join(result_lines)

        except Exception as e:
            return f"Error listing workflows: {str(e)}"

    @Tool.register_tool
    async def start_workflow(self, workflow_name: str) -> str:
        """
        Start a workflow execution! This begins a multi-step workflow that will guide you
        through a series of actions to accomplish a complex task. After starting, you MUST
        call get_next_step() to see what to do first.

        Examples:
        - start_workflow("bedside_alarm") - Start the smart alarm clock routine
        - start_workflow("wake_up") - Start the wake-up routine with calendar
        - start_workflow("focus_session") - Start a focused work session

        Args:
            workflow_name: Name of the workflow to start (use get_available_workflows first)

        Returns:
            Confirmation that workflow started and instruction to call get_next_step()
        """
        print(f"LeLamp: start_workflow function called with workflow_name: {workflow_name}")
        try:
            run_id = self.workflow_service.start_workflow(
                workflow_name=workflow_name,
                trigger_type="voice_command"
            )
            return f"Started workflow '{workflow_name}' (run ID: {run_id}). Now call get_next_step() to see what to do first!"
        except Exception as e:
            result = f"Error starting workflow {workflow_name}: {str(e)}"
            return result

    @Tool.register_tool
    async def get_next_step(self) -> str:
        """
        Get the current step in the active workflow with full context. This tells you:
        - What you should do in this step (the intent)
        - What tools you should use (preferred actions)
        - What state variables you can update

        Call this after starting a workflow or completing a step to see what's next.
        After reading the step, execute the intent and call the preferred actions.
        Then call complete_step() to advance.

        Returns:
            Your next instruction to fulfill, including suggested tools and available state variables.
        """
        print("LeLamp: get_next_step function called")
        try:
            if self.workflow_service.active_workflow is None:
                return "Error: No active workflow. Call start_workflow first."

            next_step = self.workflow_service.get_next_step()
            return next_step

        except Exception as e:
            result = f"Error getting next step: {str(e)}"
            return result

    @Tool.register_tool
    async def complete_step(self) -> str:
        """
        Complete the current workflow step and advance to the next one.

        After completing a step, the workflow will automatically advance to the next node
        based on conditional logic (if any). You'll get information about the next step
        in the response.

        Returns:
            Information about the next step or workflow completion message.
        """
        print("LeLamp: complete_step function called")
        try:
            if self.workflow_service.active_workflow is None:
                return "Error: No active workflow."

            result = self.workflow_service.complete_step(state_updates=None)
            return result

        except Exception as e:
            result = f"Error completing step: {str(e)}"
            return result

    @Tool.register_tool
    async def complete_step_with_state(self, state_updates: str) -> str:
        """
        Complete the current workflow step and update state variables.
        Use this when you need to save information from the current step.

        After completing a step, the workflow will automatically advance to the next node
        based on conditional logic (if any).

        Args:
            state_updates: JSON string of state updates, e.g. '{"user_awake": true, "attempt_count": 1}'

        Returns:
            Information about the next step or workflow completion message.
        """
        print(f"LeLamp: complete_step_with_state function called with state_updates: {state_updates}")
        try:
            if self.workflow_service.active_workflow is None:
                return "Error: No active workflow."

            # Parse the JSON string
            import json
            try:
                updates = json.loads(state_updates) if state_updates else None
            except json.JSONDecodeError:
                return f"Error: Invalid JSON in state_updates: {state_updates}"

            result = self.workflow_service.complete_step(state_updates=updates)
            return result

        except Exception as e:
            result = f"Error completing step: {str(e)}"
            return result

    @Tool.register_tool
    async def get_workflow_status(self, workflow_name: str = None) -> str:
        """
        Get detailed status and history of a specific workflow or the currently active one.
        Shows metadata, current run state, recent history, and step count.

        Use this to check:
        - Is a workflow currently running?
        - What's the current step?
        - What's the workflow's recent history?
        - Performance stats

        Args:
            workflow_name: Optional workflow name (defaults to currently active workflow)

        Returns:
            Status information including current state, history, and metadata
        """
        print(f"LeLamp: get_workflow_status function called with workflow_name: {workflow_name}")
        try:
            status = self.workflow_service.get_workflow_status(workflow_name)

            if "error" in status:
                return status["error"]

            # Format the status nicely
            result_lines = []

            # Metadata
            meta = status.get("metadata", {})
            result_lines.append(f"Workflow: {meta.get('name', 'Unknown')}")
            result_lines.append(f"Description: {meta.get('description', 'N/A')}")
            result_lines.append(f"Enabled: {'Yes' if meta.get('enabled') else 'No'}")

            # Current run
            current = status.get("current_run")
            if current:
                result_lines.append(f"\nCurrently active:")
                result_lines.append(f"  Run ID: {current.get('run_id')}")
                result_lines.append(f"  Current step: {current.get('current_node')}")
                result_lines.append(f"  Steps completed: {current.get('step_count')}")
            else:
                result_lines.append("\nNo active run")

            # Recent history
            history = status.get("recent_history", [])
            if history:
                result_lines.append(f"\nRecent runs: {len(history)}")
                for run in history[:3]:  # Show last 3
                    status_emoji = "✓" if run.get('status') == 'completed' else "✗"
                    result_lines.append(f"  {status_emoji} {run.get('started_at', 'Unknown')}")

            return "\n".join(result_lines)

        except Exception as e:
            return f"Error getting workflow status: {str(e)}"
