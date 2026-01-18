import json
import os
import logging
import traceback as tb
import importlib.util
import inspect
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime

from lelamp.service.workflows.workflow import Edge, EdgeType, Workflow
from lelamp.service.workflows.db_manager import (
    WorkflowDatabase,
    ErrorClass,
    RunStatus,
    StepStatus
)


class WorkflowService:
    """
    Enhanced workflow service with comprehensive monitoring, logging, and persistence.

    Features:
    - Graph-based workflow execution
    - Dynamic tool loading/unloading
    - SQLite persistence for all runs, steps, and state
    - Categorized error tracking
    - Performance monitoring
    - State management with history
    """

    def __init__(self, db_path: str = "lelamp.db"):
        # Core workflow state
        self.active_workflow = None
        self.state = None
        self.workflow_graph: Workflow = None
        self.workflow_data: Optional[Dict] = None  # Store raw workflow JSON
        self.trigger_type: Optional[str] = None  # Store how workflow was triggered
        self.current_node = None
        self.workflow_complete = False
        self.workflows_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "workflows"
        )

        # Tool management
        self.workflow_tools: Dict[str, Callable] = {}
        self.agent_instance = None

        # Persistence & monitoring
        self.db = WorkflowDatabase(db_path)
        self.current_run_id: Optional[str] = None
        self.current_step_id: Optional[str] = None
        self.step_counter: int = 0

        # Logging
        self.logger = logging.getLogger(__name__)
        self.logger.info("WorkflowService initialized with database persistence")

    def set_agent(self, agent):
        """Set the agent instance for dynamic tool registration"""
        self.agent_instance = agent
        self.logger.info("Agent instance set for workflow service")

    # ========================================================================
    # Workflow Discovery & Management
    # ========================================================================

    def get_available_workflows(self) -> List[str]:
        """Get list of workflow names available (looks for folders with workflow.json)"""
        if not os.path.exists(self.workflows_dir):
            return []

        workflow_names = []

        for item in os.listdir(self.workflows_dir):
            item_path = os.path.join(self.workflows_dir, item)
            if os.path.isdir(item_path):
                workflow_json = os.path.join(item_path, "workflow.json")
                if os.path.exists(workflow_json):
                    workflow_names.append(item)

        return sorted(workflow_names)

    def register_workflow_in_db(self, workflow_name: str) -> bool:
        """Register a workflow's metadata in the database"""
        try:
            workflow_path = os.path.join(self.workflows_dir, workflow_name, "workflow.json")
            with open(workflow_path, "r") as f:
                workflow_data = json.load(f)

            return self.db.register_workflow(
                workflow_id=workflow_name,
                name=workflow_data.get("name", workflow_name),
                description=workflow_data.get("description", ""),
                author=workflow_data.get("author", "unknown"),
                version=workflow_data.get("version", "1.0.0"),
                triggers=workflow_data.get("triggers", []),
                config={}
            )

        except Exception as e:
            self.logger.error(f"Error registering workflow {workflow_name}: {e}")
            return False

    def sync_workflows_to_db(self):
        """Sync all available workflows to database"""
        workflows = self.get_available_workflows()
        self.logger.info(f"Syncing {len(workflows)} workflows to database")

        for workflow_name in workflows:
            self.register_workflow_in_db(workflow_name)

    def list_enabled_workflows(self) -> List[Dict]:
        """Get list of enabled workflows with their status"""
        return self.db.list_workflows(enabled_only=True)

    # ========================================================================
    # Tool Management
    # ========================================================================

    def preload_workflow_tools(self, workflow_names: List[str] = None):
        """
        Preload tools from specified workflows before session starts.
        Ensures tools are available when LiveKit scans for them.

        Args:
            workflow_names: List of workflow names to load tools from. If None, loads all.
        """
        if not self.agent_instance:
            self.logger.warning("No agent instance set. Cannot preload tools.")
            return

        available_workflows = self.get_available_workflows()

        if workflow_names is None:
            workflow_names = available_workflows
            self.logger.info(f"Preloading tools from all workflows: {workflow_names}")
        else:
            # Validate
            invalid = [w for w in workflow_names if w not in available_workflows]
            if invalid:
                self.logger.warning(f"Invalid workflow names: {invalid}")
            workflow_names = [w for w in workflow_names if w in available_workflows]

            if not workflow_names:
                self.logger.warning("No valid workflows to preload")
                return

            self.logger.info(f"Preloading tools from: {workflow_names}")

        total_tools = 0
        for workflow_name in workflow_names:
            tool_count = self._load_workflow_tools(workflow_name, preload_only=True)
            total_tools += tool_count

        self.logger.info(f"✓ Preloaded {total_tools} tools from {len(workflow_names)} workflow(s)")

    def _load_workflow_tools(self, workflow_name: str, preload_only: bool = False) -> int:
        """
        Dynamically load and register tools from workflow's tools.py

        Returns:
            Number of tools loaded
        """
        tools_path = os.path.join(self.workflows_dir, workflow_name, "tools.py")

        if not os.path.exists(tools_path):
            self.logger.info(f"No tools.py found for workflow '{workflow_name}'")
            return 0

        try:
            # Import the tools module
            spec = importlib.util.spec_from_file_location(
                f"workflow_tools_{workflow_name}", tools_path
            )
            if not spec or not spec.loader:
                return 0

            tools_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tools_module)

            # Find and register async functions as tools
            tool_count = 0
            for attr_name in dir(tools_module):
                if attr_name.startswith("_"):
                    continue

                attr = getattr(tools_module, attr_name)

                if callable(attr) and inspect.iscoroutinefunction(attr):
                    if self.agent_instance:
                        from livekit.agents import function_tool
                        import functools

                        # Unwrap if already decorated
                        unwrapped_func = getattr(attr, "__wrapped__", attr)

                        # FIX: Use a factory to properly capture each function in closure
                        def make_tool_wrapper(func):
                            @functools.wraps(func)
                            async def tool_method(self_instance, *args, **kwargs):
                                return await func(self_instance, *args, **kwargs)
                            return tool_method

                        # Create wrapper with proper closure
                        tool_method = make_tool_wrapper(unwrapped_func)

                        # Copy attributes
                        tool_method.__name__ = unwrapped_func.__name__
                        tool_method.__qualname__ = f"{self.agent_instance.__class__.__name__}.{unwrapped_func.__name__}"
                        tool_method.__doc__ = unwrapped_func.__doc__
                        tool_method.__annotations__ = getattr(unwrapped_func, "__annotations__", {})

                        # Apply decorator
                        decorated_func = function_tool(tool_method)

                        # Store for cleanup
                        self.workflow_tools[attr_name] = attr

                        # Add to class
                        agent_class = self.agent_instance.__class__
                        setattr(agent_class, attr_name, decorated_func)

                        # Add to _tools list
                        bound_method = getattr(self.agent_instance, attr_name)
                        if hasattr(self.agent_instance, "_tools"):
                            existing_names = [t.__name__ for t in self.agent_instance._tools]
                            if attr_name not in existing_names:
                                self.agent_instance._tools.append(bound_method)
                                self.logger.debug(f"✓ Added {attr_name} to agent._tools")

                        tool_count += 1
                        self.logger.info(f"✓ Registered workflow tool: {attr_name}")

            mode = "Preloaded" if preload_only else "Loaded"
            self.logger.info(f"{mode} {tool_count} tools for workflow '{workflow_name}'")
            return tool_count

        except Exception as e:
            self.logger.error(f"Error loading tools for '{workflow_name}': {e}")
            self.logger.error(tb.format_exc())
            return 0

    def _unload_workflow_tools(self):
        """Unregister workflow-specific tools from the agent class"""
        if self.agent_instance:
            for tool_name in self.workflow_tools.keys():
                if hasattr(self.agent_instance.__class__, tool_name):
                    delattr(self.agent_instance.__class__, tool_name)
                    self.logger.info(f"✗ Unregistered workflow tool: {tool_name}")

        self.workflow_tools.clear()

    # ========================================================================
    # Workflow Execution
    # ========================================================================

    def start_workflow(
        self,
        workflow_name: str,
        trigger_type: str = "voice_command",
        trigger_data: Dict = None
    ) -> str:
        """
        Start a new workflow execution.

        Args:
            workflow_name: Name of the workflow to start
            trigger_type: How it was triggered (voice_command, alarm_trigger, etc.)
            trigger_data: Additional context about the trigger

        Returns:
            run_id for this execution
        """
        try:
            # Load workflow.json
            workflow_path = os.path.join(self.workflows_dir, workflow_name, "workflow.json")
            with open(workflow_path, "r") as f:
                workflow_data = json.load(f)

            self.workflow_graph = Workflow.from_json(workflow_data)
            self.workflow_data = workflow_data  # Store raw JSON for entry_points
            self.trigger_type = trigger_type  # Store trigger type for entry point logic
            self.active_workflow = workflow_name

            # Initialize state from schema
            self.state = {
                key: var.default
                for key, var in self.workflow_graph.state_schema.items()
            }

            self.current_node = None
            self.workflow_complete = False
            self.step_counter = 0

            # Start database run tracking
            self.current_run_id = self.db.start_run(
                workflow_id=workflow_name,
                trigger_type=trigger_type,
                trigger_data=trigger_data
            )

            self.logger.info(f"Started workflow '{workflow_name}' (run_id: {self.current_run_id})")

            # Load workflow-specific tools
            self._load_workflow_tools(workflow_name)

            return self.current_run_id

        except Exception as e:
            self.logger.error(f"Error starting workflow {workflow_name}: {e}")
            self.logger.error(tb.format_exc())

            # Log error to database if we have a run_id
            if self.current_run_id:
                self.db.log_error(
                    run_id=self.current_run_id,
                    error_class=ErrorClass.SYSTEM,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    stack_trace=tb.format_exc(),
                    context={"workflow_name": workflow_name}
                )

            raise

    def cancel_workflow(self, run_id: str) -> bool:
        """Cancel a specific workflow run by ID.

        Args:
            run_id: The run ID to cancel

        Returns:
            True if cancelled successfully
        """
        try:
            # If this is the currently active workflow, stop it
            if self.current_run_id == run_id:
                self.stop_workflow(RunStatus.CANCELLED)
                return True

            # Otherwise just cancel in database
            result = self.db.cancel_run(run_id)
            if result:
                self.logger.info(f"Cancelled workflow run {run_id}")
            return result

        except Exception as e:
            self.logger.error(f"Error cancelling workflow {run_id}: {e}")
            return False

    def cancel_workflows_for_alarm(self, alarm_id: int) -> int:
        """Cancel all running workflows triggered by a specific alarm.

        Args:
            alarm_id: The alarm ID whose workflows should be cancelled

        Returns:
            Number of workflows cancelled
        """
        cancelled = 0
        try:
            running_workflows = self.db.get_running_workflows_with_trigger()
            for wf in running_workflows:
                trigger_data = wf.get("trigger_data", "{}")
                if isinstance(trigger_data, str):
                    try:
                        trigger_data = json.loads(trigger_data)
                    except:
                        trigger_data = {}

                # Check if this workflow was triggered by the deleted alarm
                if trigger_data.get("alarm_id") == alarm_id:
                    run_id = wf.get("run_id")
                    workflow_id = wf.get("workflow_id")
                    self.logger.info(f"🗑️ Cancelling workflow run {run_id} ({workflow_id}) - associated alarm {alarm_id} was deleted")
                    if self.cancel_workflow(run_id):
                        cancelled += 1

        except Exception as e:
            self.logger.error(f"Error cancelling workflows for alarm {alarm_id}: {e}")

        return cancelled

    def cancel_workflows_for_timer(self, timer_id: int) -> int:
        """Cancel all running workflows triggered by a specific timer.

        Args:
            timer_id: The timer ID whose workflows should be cancelled

        Returns:
            Number of workflows cancelled
        """
        cancelled = 0
        try:
            running_workflows = self.db.get_running_workflows_with_trigger()
            for wf in running_workflows:
                trigger_data = wf.get("trigger_data", "{}")
                if isinstance(trigger_data, str):
                    try:
                        trigger_data = json.loads(trigger_data)
                    except:
                        trigger_data = {}

                # Check if this workflow was triggered by the deleted timer
                if trigger_data.get("timer_id") == timer_id:
                    run_id = wf.get("run_id")
                    workflow_id = wf.get("workflow_id")
                    self.logger.info(f"🗑️ Cancelling workflow run {run_id} ({workflow_id}) - associated timer {timer_id} was deleted")
                    if self.cancel_workflow(run_id):
                        cancelled += 1

        except Exception as e:
            self.logger.error(f"Error cancelling workflows for timer {timer_id}: {e}")

        return cancelled

    def stop_workflow(self, status: RunStatus = RunStatus.COMPLETED):
        """Stop the current workflow and persist final state"""
        if not self.active_workflow:
            return

        try:
            # Mark run as complete in database
            if self.current_run_id:
                self.db.complete_run(self.current_run_id, status)

            # Unload tools
            self._unload_workflow_tools()

            self.logger.info(f"Stopped workflow '{self.active_workflow}' with status {status.value}")

            # Reset state
            self.active_workflow = None
            self.state = None
            self.workflow_graph = None
            self.current_node = None
            self.workflow_complete = False
            self.current_run_id = None
            self.current_step_id = None
            self.step_counter = 0

        except Exception as e:
            self.logger.error(f"Error stopping workflow: {e}")

    # ========================================================================
    # Step Execution
    # ========================================================================

    def get_next_step(self) -> str:
        """
        Get the current step with full context.

        Returns:
            Formatted string with step instructions, required actions, and state info
        """
        if self.workflow_graph is None:
            return "Error: No workflow graph found. Please select a workflow first."

        if self.workflow_complete:
            return "Workflow is complete. There are no more steps."

        try:
            # If no current node, determine starting point
            if self.current_node is None:
                # Check if workflow defines entry_points for different triggers
                starting_node_id = None

                if self.workflow_data and "entry_points" in self.workflow_data:
                    entry_points = self.workflow_data["entry_points"]
                    if self.trigger_type and self.trigger_type in entry_points:
                        # Use trigger-specific entry point
                        starting_node_id = entry_points[self.trigger_type]
                        self.logger.info(f"Using entry point '{starting_node_id}' for trigger '{self.trigger_type}'")

                # Fallback to START edge if no entry point found
                if not starting_node_id:
                    starting_edge = self.workflow_graph.edges.get("START")
                    if not starting_edge:
                        return "Error: No starting edge found in workflow graph."
                    starting_node_id = starting_edge.target

                self.current_node = self.workflow_graph.nodes[starting_node_id]

                # Update run's current node
                if self.current_run_id:
                    self.db.update_run_node(self.current_run_id, starting_node_id)

                self.logger.info(f"Starting workflow at node: {starting_node_id}")

            # Start step tracking in database
            if self.current_run_id:
                self.step_counter += 1
                self.current_step_id = self.db.start_step(
                    run_id=self.current_run_id,
                    node_id=self.current_node.id,
                    step_number=self.step_counter,
                    intent=self.current_node.intent,
                    preferred_actions=self.current_node.preferred_actions,
                    state_before=self.state
                )

            # Build step information for the agent
            step_info = f"═══ CURRENT STEP ═══\n"
            step_info += f"Node ID: {self.current_node.id}\n"
            step_info += f"Intent: {self.current_node.intent}\n"

            if self.current_node.preferred_actions:
                step_info += f"\n⚠️ REQUIRED ACTIONS:\n"
                for action in self.current_node.preferred_actions:
                    step_info += f"  • You MUST call: {action}\n"

            # Show state
            if self.workflow_graph.state_schema:
                step_info += f"\nState variables (update via complete_step if needed):\n"
                for key, var in self.workflow_graph.state_schema.items():
                    current_value = self.state.get(key)
                    step_info += f"  • {key}: {current_value} (type: {var.type})\n"

            step_info += "═══════════════════\n"

            self.logger.debug(f"get_next_step: {self.current_node.id}")
            return step_info

        except Exception as e:
            self.logger.error(f"Error in get_next_step: {e}")
            self.logger.error(tb.format_exc())

            # Log error
            if self.current_run_id:
                self.db.log_error(
                    run_id=self.current_run_id,
                    error_class=ErrorClass.SYSTEM,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    stack_trace=tb.format_exc()
                )

            return f"Error getting next step: {str(e)}"

    def complete_step(
        self,
        state_updates: Optional[Dict] = None,
        llm_response: Optional[str] = None,
        user_input: Optional[str] = None
    ) -> str:
        """
        Complete the current step and advance to the next node.

        Args:
            state_updates: Dict of state variable updates
            llm_response: What the LLM said/did (for logging)
            user_input: User's input (for logging)

        Returns:
            Info about the next step or workflow completion message
        """
        if not self.workflow_graph or not self.current_node:
            return "Error: No active workflow or current node"

        if self.workflow_complete:
            return "Workflow already complete"

        try:
            self.logger.info(f"Completing step: {self.current_node.id}")

            state_before = self.state.copy()

            # Apply state updates
            if state_updates:
                for key, value in state_updates.items():
                    if key not in self.workflow_graph.state_schema:
                        error_msg = f"Error: State variable '{key}' not in schema. Available: {list(self.workflow_graph.state_schema.keys())}"
                        self.logger.error(error_msg)
                        return error_msg

                    self.state[key] = value
                    self.logger.info(f"✓ Updated state: {key} = {value}")

                    # Persist state update
                    if self.current_run_id:
                        self.db.update_state(
                            run_id=self.current_run_id,
                            state_key=key,
                            state_value=value,
                            state_type=self.workflow_graph.state_schema[key].type,
                            updated_by_step_id=self.current_step_id
                        )

            # Complete step in database
            if self.current_step_id:
                self.db.complete_step(
                    step_id=self.current_step_id,
                    status=StepStatus.COMPLETED,
                    llm_response=llm_response,
                    user_input=user_input,
                    state_after=self.state,
                    state_updates=state_updates
                )

            # Get outgoing edge
            edge = self.workflow_graph.edges.get(self.current_node.id)

            if not edge:
                # No outgoing edge = workflow complete
                self.workflow_complete = True
                self.stop_workflow(RunStatus.COMPLETED)
                return "Workflow complete! No more steps."

            # Resolve next node based on edge type
            next_node_id = self._resolve_edge_target(edge)

            if next_node_id == "END":
                self.workflow_complete = True
                self.stop_workflow(RunStatus.COMPLETED)
                return "Workflow complete! Reached END state."

            # Move to next node
            prev_node_id = self.current_node.id
            self.current_node = self.workflow_graph.nodes[next_node_id]

            # Update run's current node
            if self.current_run_id:
                self.db.update_run_node(self.current_run_id, next_node_id)

            self.logger.info(f"✓ Transitioned: {prev_node_id} → {next_node_id}")

            # Return next step info
            next_step_info = f"✓ Advanced from '{prev_node_id}' to '{next_node_id}'\n\n"
            next_step_info += f"═══ NEXT STEP ═══\n"
            next_step_info += f"Node ID: {self.current_node.id}\n"
            next_step_info += f"Intent: {self.current_node.intent}\n"

            if self.current_node.preferred_actions:
                next_step_info += f"\n⚠️ REQUIRED ACTIONS:\n"
                for action in self.current_node.preferred_actions:
                    next_step_info += f"  • You MUST call: {action}\n"

            next_step_info += "═══════════════════"

            return next_step_info

        except Exception as e:
            self.logger.error(f"Error completing step: {e}")
            self.logger.error(tb.format_exc())

            # Log error
            if self.current_run_id:
                self.db.log_error(
                    run_id=self.current_run_id,
                    step_id=self.current_step_id,
                    error_class=ErrorClass.SYSTEM,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    stack_trace=tb.format_exc(),
                    context={"state": self.state}
                )

            return f"Error completing step: {str(e)}"

    def _resolve_edge_target(self, edge: Edge) -> str:
        """Resolve the target node ID based on edge type and current state"""
        if edge.type == EdgeType.NORMAL:
            return edge.target

        # Conditional edge
        if not isinstance(edge.target, dict):
            raise ValueError(f"Conditional edge {edge.id} target must be a dict")

        if not edge.state_key:
            raise ValueError(f"Conditional edge {edge.id} missing state_key")

        # Get state value
        state_value = self.state.get(edge.state_key)

        # Convert to target key
        target_key = (
            "true" if state_value is True
            else "false" if state_value is False
            else str(state_value)
        )

        if target_key not in edge.target:
            raise ValueError(
                f"Edge {edge.id}: state '{edge.state_key}'={state_value} -> '{target_key}' "
                f"not in targets {list(edge.target.keys())}"
            )

        return edge.target[target_key]

    # ========================================================================
    # Monitoring & History
    # ========================================================================

    def get_workflow_status(self, workflow_id: str = None) -> Dict:
        """Get status of a specific workflow or the currently active one"""
        if workflow_id is None:
            workflow_id = self.active_workflow

        if not workflow_id:
            return {"error": "No workflow specified or active"}

        try:
            # Get metadata
            metadata = self.db.get_workflow(workflow_id)
            if not metadata:
                return {"error": f"Workflow '{workflow_id}' not found"}

            # Get recent runs
            history = self.db.get_workflow_history(workflow_id, limit=10)

            # Get current run if active
            current_run = None
            if self.current_run_id and self.active_workflow == workflow_id:
                current_run = {
                    "run_id": self.current_run_id,
                    "current_node": self.current_node.id if self.current_node else None,
                    "step_count": self.step_counter,
                    "state": self.state
                }

            return {
                "metadata": metadata,
                "current_run": current_run,
                "recent_history": history,
                "is_active": self.active_workflow == workflow_id
            }

        except Exception as e:
            self.logger.error(f"Error getting workflow status: {e}")
            return {"error": str(e)}

    def get_run_details(self, run_id: str) -> Dict:
        """Get detailed information about a specific run"""
        try:
            run = self.db.get_run(run_id)
            if not run:
                return {"error": f"Run '{run_id}' not found"}

            steps = self.db.get_run_steps(run_id)
            state = self.db.get_run_state(run_id)

            return {
                "run": run,
                "steps": steps,
                "state": state
            }

        except Exception as e:
            self.logger.error(f"Error getting run details: {e}")
            return {"error": str(e)}
