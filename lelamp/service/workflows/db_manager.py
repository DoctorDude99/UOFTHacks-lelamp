import sqlite3
import json
import uuid
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from enum import Enum


class ErrorClass(Enum):
    """Categorization of workflow errors for monitoring"""
    SYSTEM = "System"          # Hardware, OS, resource errors
    LLM = "LLM"               # LLM API errors, generation failures
    UNEXPECTED = "Unexpected"  # Unknown or unhandled exceptions
    HUMAN = "Human"            # User input issues, misunderstandings
    NETWORK = "Network"        # Connection, timeout errors
    VISION = "Vision"          # Camera, vision processing errors
    STATE = "State"            # Invalid state transitions, missing state
    TOOL = "Tool"              # Tool execution failures


class RunStatus(Enum):
    """Status of a workflow run"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class StepStatus(Enum):
    """Status of a workflow step"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowDatabase:
    """
    Database manager for workflow persistence, monitoring, and logging.

    Handles all SQLite operations for the workflow system including:
    - Workflow metadata management
    - Run execution tracking
    - Step-by-step logging
    - Error categorization and tracking
    - State management
    - Performance statistics
    """

    def __init__(self, db_path: str = "lelamp.db"):
        """
        Initialize the workflow database.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._init_database()

    def _init_database(self):
        """Initialize database schema from schema file"""
        try:
            # Read schema from file
            schema_path = Path(__file__).parent / "db_schema.sql"
            with open(schema_path, 'r') as f:
                schema_sql = f.read()

            # Execute schema
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(schema_sql)
                conn.commit()

            self.logger.info("Workflow database initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
            raise

    # ========================================================================
    # Workflow Management
    # ========================================================================

    def register_workflow(
        self,
        workflow_id: str,
        name: str,
        description: str = "",
        author: str = "unknown",
        version: str = "1.0.0",
        triggers: List[str] = None,
        config: Dict = None,
        enabled: bool = True
    ) -> bool:
        """
        Register or update a workflow in the database.

        Args:
            workflow_id: Unique identifier
            name: Human-readable name
            description: What the workflow does
            author: Who created it
            version: Version string
            triggers: List of trigger types
            config: Workflow-specific config
            enabled: Whether workflow is active

        Returns:
            True if successful
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO workflows
                    (workflow_id, name, description, author, version, enabled, triggers, config)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    workflow_id,
                    name,
                    description,
                    author,
                    version,
                    1 if enabled else 0,
                    json.dumps(triggers or []),
                    json.dumps(config or {})
                ))
                conn.commit()

            self.logger.info(f"Registered workflow: {workflow_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error registering workflow {workflow_id}: {e}")
            return False

    def get_workflow(self, workflow_id: str) -> Optional[Dict]:
        """Get workflow metadata"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM workflows WHERE workflow_id = ?",
                    (workflow_id,)
                )
                row = cursor.fetchone()

                if row:
                    return dict(row)
                return None

        except Exception as e:
            self.logger.error(f"Error getting workflow {workflow_id}: {e}")
            return None

    def list_workflows(self, enabled_only: bool = False) -> List[Dict]:
        """List all workflows"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                query = "SELECT * FROM workflows"
                if enabled_only:
                    query += " WHERE enabled = 1"
                query += " ORDER BY name"

                cursor = conn.execute(query)
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error listing workflows: {e}")
            return []

    def enable_workflow(self, workflow_id: str, enabled: bool = True) -> bool:
        """Enable or disable a workflow"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE workflows SET enabled = ? WHERE workflow_id = ?",
                    (1 if enabled else 0, workflow_id)
                )
                conn.commit()
            return True

        except Exception as e:
            self.logger.error(f"Error updating workflow {workflow_id}: {e}")
            return False

    # ========================================================================
    # Workflow Run Management
    # ========================================================================

    def start_run(
        self,
        workflow_id: str,
        trigger_type: str = "manual",
        trigger_data: Dict = None
    ) -> str:
        """
        Start a new workflow run.

        Args:
            workflow_id: Which workflow to run
            trigger_type: How it was triggered
            trigger_data: Additional trigger context

        Returns:
            run_id for the new run
        """
        run_id = str(uuid.uuid4())

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO workflow_runs
                    (run_id, workflow_id, status, trigger_type, trigger_data, current_node_id)
                    VALUES (?, ?, ?, ?, ?, NULL)
                """, (
                    run_id,
                    workflow_id,
                    RunStatus.RUNNING.value,
                    trigger_type,
                    json.dumps(trigger_data or {})
                ))
                conn.commit()

            self.logger.info(f"Started workflow run {run_id} for {workflow_id}")
            return run_id

        except Exception as e:
            self.logger.error(f"Error starting run: {e}")
            raise

    def update_run_node(self, run_id: str, node_id: str):
        """Update the current node for a run"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE workflow_runs SET current_node_id = ? WHERE run_id = ?",
                    (node_id, run_id)
                )
                conn.commit()

        except Exception as e:
            self.logger.error(f"Error updating run node: {e}")

    def complete_run(self, run_id: str, status: RunStatus = RunStatus.COMPLETED):
        """
        Mark a workflow run as completed or failed, then clean up.

        Args:
            run_id: The run to complete
            status: Final status (COMPLETED or FAILED)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Delete associated steps first (foreign key cleanup)
                conn.execute("DELETE FROM workflow_steps WHERE run_id = ?", (run_id,))
                # Delete the run itself
                conn.execute("DELETE FROM workflow_runs WHERE run_id = ?", (run_id,))
                conn.commit()

            self.logger.info(f"Cleaned up workflow run {run_id} (status: {status.value})")

        except Exception as e:
            self.logger.error(f"Error completing/cleaning run: {e}")

    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get run details"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM workflow_runs WHERE run_id = ?",
                    (run_id,)
                )
                row = cursor.fetchone()

                if row:
                    return dict(row)
                return None

        except Exception as e:
            self.logger.error(f"Error getting run {run_id}: {e}")
            return None

    def get_active_runs(self) -> List[Dict]:
        """Get all currently running workflows"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM active_workflow_runs"
                )
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting active runs: {e}")
            return []

    def get_running_workflows_with_trigger(self) -> List[Dict]:
        """Get all running workflows with their trigger data for cleanup purposes"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT run_id, workflow_id, trigger_type, trigger_data, started_at, current_node
                    FROM workflow_runs
                    WHERE status = ?
                """, (RunStatus.RUNNING.value,))
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting running workflows: {e}")
            return []

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running workflow"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    UPDATE workflow_runs
                    SET status = ?, completed_at = ?
                    WHERE run_id = ? AND status = ?
                """, (
                    RunStatus.CANCELLED.value,
                    datetime.now().isoformat(),
                    run_id,
                    RunStatus.RUNNING.value
                ))
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            self.logger.error(f"Error cancelling run {run_id}: {e}")
            return False

    # ========================================================================
    # Step Logging
    # ========================================================================

    def start_step(
        self,
        run_id: str,
        node_id: str,
        step_number: int,
        intent: str = "",
        preferred_actions: List[str] = None,
        state_before: Dict = None
    ) -> str:
        """
        Log the start of a workflow step.

        Args:
            run_id: Parent run
            node_id: Which node is executing
            step_number: Sequential step number
            intent: What this step should accomplish
            preferred_actions: Suggested tools
            state_before: State snapshot before step

        Returns:
            step_id for this step
        """
        step_id = str(uuid.uuid4())

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO workflow_steps
                    (step_id, run_id, node_id, step_number, intent, preferred_actions,
                     status, state_before)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    step_id,
                    run_id,
                    node_id,
                    step_number,
                    intent,
                    json.dumps(preferred_actions or []),
                    StepStatus.RUNNING.value,
                    json.dumps(state_before or {})
                ))
                conn.commit()

            return step_id

        except Exception as e:
            self.logger.error(f"Error starting step: {e}")
            raise

    def complete_step(
        self,
        step_id: str,
        status: StepStatus = StepStatus.COMPLETED,
        actions_taken: List[str] = None,
        llm_response: str = None,
        user_input: str = None,
        state_after: Dict = None,
        state_updates: Dict = None,
        error_message: str = None
    ):
        """
        Mark a step as completed and log what happened.

        Args:
            step_id: The step to complete
            status: Final status
            actions_taken: Tools that were actually called
            llm_response: What the LLM said/did
            user_input: User's input (if any)
            state_after: State after step completed
            state_updates: What changed in state
            error_message: Error if step failed
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE workflow_steps
                    SET status = ?, completed_at = CURRENT_TIMESTAMP,
                        actions_taken = ?, llm_response = ?, user_input = ?,
                        state_after = ?, state_updates = ?, error_message = ?
                    WHERE step_id = ?
                """, (
                    status.value,
                    json.dumps(actions_taken or []),
                    llm_response,
                    user_input,
                    json.dumps(state_after or {}),
                    json.dumps(state_updates or {}),
                    error_message,
                    step_id
                ))
                conn.commit()

        except Exception as e:
            self.logger.error(f"Error completing step: {e}")

    def get_run_steps(self, run_id: str) -> List[Dict]:
        """Get all steps for a run in order"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM workflow_steps
                    WHERE run_id = ?
                    ORDER BY step_number
                """, (run_id,))
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting steps for run {run_id}: {e}")
            return []

    # ========================================================================
    # Error Tracking
    # ========================================================================

    def log_error(
        self,
        run_id: str,
        error_class: ErrorClass,
        error_type: str,
        error_message: str,
        step_id: Optional[str] = None,
        stack_trace: Optional[str] = None,
        context: Optional[Dict] = None,
        recoverable: bool = False,
        recovery_action: Optional[str] = None
    ) -> str:
        """
        Log a categorized error for monitoring and debugging.

        Args:
            run_id: Which run had the error
            error_class: Category of error (System, LLM, etc.)
            error_type: Specific error type
            error_message: Human-readable message
            step_id: Which step had the error (optional)
            stack_trace: Full stack trace
            context: Relevant context for debugging
            recoverable: Was it recoverable?
            recovery_action: What was done to recover

        Returns:
            error_id
        """
        error_id = str(uuid.uuid4())

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO workflow_errors
                    (error_id, run_id, step_id, error_class, error_type, error_message,
                     stack_trace, context, recoverable, recovery_action)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    error_id,
                    run_id,
                    step_id,
                    error_class.value,
                    error_type,
                    error_message,
                    stack_trace,
                    json.dumps(context or {}),
                    1 if recoverable else 0,
                    recovery_action
                ))

                # Increment error count on the run
                conn.execute("""
                    UPDATE workflow_runs
                    SET error_count = error_count + 1
                    WHERE run_id = ?
                """, (run_id,))

                conn.commit()

            self.logger.warning(f"Logged {error_class.value} error in run {run_id}: {error_message}")
            return error_id

        except Exception as e:
            self.logger.error(f"Error logging error (meta!): {e}")
            return ""

    def get_recent_errors(self, limit: int = 100) -> List[Dict]:
        """Get recent errors for monitoring"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM recent_workflow_errors LIMIT ?",
                    (limit,)
                )
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting recent errors: {e}")
            return []

    # ========================================================================
    # State Management
    # ========================================================================

    def update_state(
        self,
        run_id: str,
        state_key: str,
        state_value: Any,
        state_type: str,
        updated_by_step_id: Optional[str] = None
    ):
        """Update a state variable for a run"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO workflow_state
                    (run_id, state_key, state_value, state_type, updated_by_step_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    run_id,
                    state_key,
                    json.dumps(state_value),
                    state_type,
                    updated_by_step_id
                ))
                conn.commit()

        except Exception as e:
            self.logger.error(f"Error updating state: {e}")

    def get_run_state(self, run_id: str) -> Dict:
        """Get all state variables for a run"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM workflow_state WHERE run_id = ?",
                    (run_id,)
                )

                state = {}
                for row in cursor.fetchall():
                    state[row['state_key']] = json.loads(row['state_value'])

                return state

        except Exception as e:
            self.logger.error(f"Error getting state for run {run_id}: {e}")
            return {}

    # ========================================================================
    # Monitoring & Stats
    # ========================================================================

    def get_workflow_performance(self) -> List[Dict]:
        """Get performance summary for all workflows"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM workflow_performance")
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting performance stats: {e}")
            return []

    def get_workflow_history(
        self,
        workflow_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """Get recent run history for a workflow"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM workflow_runs
                    WHERE workflow_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                """, (workflow_id, limit))
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting history for {workflow_id}: {e}")
            return []
