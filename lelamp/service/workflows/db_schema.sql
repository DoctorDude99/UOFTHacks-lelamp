-- Workflow System Database Schema
-- This schema supports workflow persistence, monitoring, logging, and error tracking

-- ============================================================================
-- Table: workflows
-- Stores metadata about available workflows
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,                -- Unique workflow identifier (e.g., "bedside_alarm")
    name TEXT NOT NULL,                          -- Human-readable name
    description TEXT,                            -- What this workflow does
    author TEXT,                                 -- Who created it
    version TEXT DEFAULT '1.0.0',               -- Workflow version
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    enabled BOOLEAN DEFAULT 1,                   -- Whether workflow is active
    triggers TEXT,                               -- JSON array of trigger types ["alarm_trigger", "voice_command"]
    config TEXT                                  -- JSON config for workflow-specific settings
);

-- ============================================================================
-- Table: workflow_runs
-- Tracks each execution instance of a workflow
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,                    -- Unique run identifier (UUID)
    workflow_id TEXT NOT NULL,                  -- Which workflow is running
    status TEXT NOT NULL,                       -- "running", "completed", "failed", "paused"
    trigger_type TEXT,                          -- How was it triggered? "alarm", "voice", "timer", "manual"
    trigger_data TEXT,                          -- JSON data about the trigger
    current_node_id TEXT,                       -- Current step in the workflow
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds REAL,                      -- How long did it take?
    error_count INTEGER DEFAULT 0,              -- Number of errors during this run

    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
);

-- Index for faster lookups by workflow and status
CREATE INDEX IF NOT EXISTS idx_runs_workflow_status ON workflow_runs(workflow_id, status);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON workflow_runs(started_at DESC);

-- ============================================================================
-- Table: workflow_steps
-- Logs each step/node execution within a workflow run
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_steps (
    step_id TEXT PRIMARY KEY,                   -- Unique step identifier (UUID)
    run_id TEXT NOT NULL,                       -- Which run does this belong to?
    node_id TEXT NOT NULL,                      -- Which node was executed
    step_number INTEGER NOT NULL,               -- Sequential step number (1, 2, 3...)
    intent TEXT,                                -- What was the goal of this step?
    preferred_actions TEXT,                     -- JSON array of suggested tools

    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds REAL,

    status TEXT NOT NULL,                       -- "running", "completed", "failed", "skipped"

    -- What actually happened during this step?
    actions_taken TEXT,                         -- JSON array of tools that were called
    llm_response TEXT,                          -- What did the LLM say/do?
    user_input TEXT,                            -- What did the user say (if applicable)?

    -- State changes
    state_before TEXT,                          -- JSON snapshot of state before step
    state_after TEXT,                           -- JSON snapshot of state after step
    state_updates TEXT,                         -- JSON of what changed

    error_message TEXT,                         -- Error if step failed

    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
);

-- Index for faster step lookups
CREATE INDEX IF NOT EXISTS idx_steps_run ON workflow_steps(run_id, step_number);
CREATE INDEX IF NOT EXISTS idx_steps_node ON workflow_steps(node_id);

-- ============================================================================
-- Table: workflow_errors
-- Categorized error tracking for debugging and monitoring
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_errors (
    error_id TEXT PRIMARY KEY,                  -- Unique error identifier (UUID)
    run_id TEXT NOT NULL,                       -- Which run had the error?
    step_id TEXT,                               -- Which step had the error (if applicable)?

    error_class TEXT NOT NULL,                  -- "System", "LLM", "Unexpected", "Human", "Network", "Vision"
    error_type TEXT NOT NULL,                   -- Specific error type (e.g., "TimeoutError", "InvalidState")
    error_message TEXT NOT NULL,                -- Human-readable error message
    stack_trace TEXT,                           -- Full stack trace for debugging

    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Context for debugging
    context TEXT,                               -- JSON with relevant context (state, inputs, etc.)
    recoverable BOOLEAN DEFAULT 0,              -- Was the workflow able to recover?
    recovery_action TEXT,                       -- What was done to recover?

    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id),
    FOREIGN KEY (step_id) REFERENCES workflow_steps(step_id)
);

-- Index for error analysis
CREATE INDEX IF NOT EXISTS idx_errors_class ON workflow_errors(error_class);
CREATE INDEX IF NOT EXISTS idx_errors_run ON workflow_errors(run_id);
CREATE INDEX IF NOT EXISTS idx_errors_occurred_at ON workflow_errors(occurred_at DESC);

-- ============================================================================
-- Table: workflow_state
-- Current state variables for each workflow run
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_state (
    run_id TEXT NOT NULL,                       -- Which run does this state belong to?
    state_key TEXT NOT NULL,                    -- State variable name
    state_value TEXT,                           -- JSON-encoded value
    state_type TEXT,                            -- "boolean", "integer", "string", "object"

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by_step_id TEXT,                    -- Which step last updated this?

    PRIMARY KEY (run_id, state_key),
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id),
    FOREIGN KEY (updated_by_step_id) REFERENCES workflow_steps(step_id)
);

-- Index for state lookups
CREATE INDEX IF NOT EXISTS idx_state_run ON workflow_state(run_id);

-- ============================================================================
-- Table: workflow_triggers
-- Tracks what can trigger each workflow (for automatic triggering)
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_triggers (
    trigger_id TEXT PRIMARY KEY,                -- Unique trigger identifier
    workflow_id TEXT NOT NULL,                  -- Which workflow to start
    trigger_type TEXT NOT NULL,                 -- "alarm", "timer_complete", "face_detected", "time_of_day"
    trigger_config TEXT,                        -- JSON config for the trigger
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
);

CREATE INDEX IF NOT EXISTS idx_triggers_workflow ON workflow_triggers(workflow_id);
CREATE INDEX IF NOT EXISTS idx_triggers_type ON workflow_triggers(trigger_type, enabled);

-- ============================================================================
-- Table: workflow_active_triggers
-- Tracks triggers for active workflow runs (for autonomous progression)
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_active_triggers (
    active_trigger_id TEXT PRIMARY KEY,         -- Unique active trigger ID
    run_id TEXT NOT NULL,                       -- Which run this trigger belongs to
    workflow_id TEXT NOT NULL,                  -- Which workflow (for quick lookups)

    trigger_type TEXT NOT NULL,                 -- "time_interval", "keyword", "state_change", "user_interaction"
    trigger_config TEXT,                        -- JSON config for the trigger

    -- Timing
    next_check_at TIMESTAMP,                    -- When to next check this trigger
    last_checked_at TIMESTAMP,                  -- When was it last checked
    check_interval_seconds INTEGER,             -- How often to check (for time-based triggers)

    -- State
    enabled BOOLEAN DEFAULT 1,
    triggered_count INTEGER DEFAULT 0,          -- How many times has this fired?

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id),
    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
);

CREATE INDEX IF NOT EXISTS idx_active_triggers_run ON workflow_active_triggers(run_id);
CREATE INDEX IF NOT EXISTS idx_active_triggers_next_check ON workflow_active_triggers(next_check_at, enabled);
CREATE INDEX IF NOT EXISTS idx_active_triggers_type ON workflow_active_triggers(trigger_type, enabled);

-- ============================================================================
-- Table: workflow_stats
-- Aggregated statistics for monitoring and optimization
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_stats (
    workflow_id TEXT NOT NULL,
    date DATE NOT NULL,                         -- Stats for this date

    total_runs INTEGER DEFAULT 0,
    successful_runs INTEGER DEFAULT 0,
    failed_runs INTEGER DEFAULT 0,

    avg_duration_seconds REAL,
    min_duration_seconds REAL,
    max_duration_seconds REAL,

    total_errors INTEGER DEFAULT 0,

    PRIMARY KEY (workflow_id, date),
    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
);

-- ============================================================================
-- Triggers for automatic timestamp updates
-- ============================================================================

-- Update workflows.updated_at when modified
CREATE TRIGGER IF NOT EXISTS update_workflows_timestamp
AFTER UPDATE ON workflows
BEGIN
    UPDATE workflows SET updated_at = CURRENT_TIMESTAMP WHERE workflow_id = NEW.workflow_id;
END;

-- Calculate run duration when completed
CREATE TRIGGER IF NOT EXISTS calculate_run_duration
AFTER UPDATE ON workflow_runs
WHEN NEW.completed_at IS NOT NULL AND OLD.completed_at IS NULL
BEGIN
    UPDATE workflow_runs
    SET duration_seconds = (julianday(NEW.completed_at) - julianday(NEW.started_at)) * 86400
    WHERE run_id = NEW.run_id;
END;

-- Calculate step duration when completed
CREATE TRIGGER IF NOT EXISTS calculate_step_duration
AFTER UPDATE ON workflow_steps
WHEN NEW.completed_at IS NOT NULL AND OLD.completed_at IS NULL
BEGIN
    UPDATE workflow_steps
    SET duration_seconds = (julianday(NEW.completed_at) - julianday(NEW.started_at)) * 86400
    WHERE step_id = NEW.step_id;
END;

-- ============================================================================
-- Views for easy querying
-- ============================================================================

-- Active workflow runs
CREATE VIEW IF NOT EXISTS active_workflow_runs AS
SELECT
    wr.*,
    w.name as workflow_name,
    w.description as workflow_description,
    (julianday('now') - julianday(wr.started_at)) * 86400 as running_duration_seconds
FROM workflow_runs wr
JOIN workflows w ON wr.workflow_id = w.workflow_id
WHERE wr.status = 'running'
ORDER BY wr.started_at DESC;

-- Recent errors
CREATE VIEW IF NOT EXISTS recent_workflow_errors AS
SELECT
    we.*,
    wr.workflow_id,
    w.name as workflow_name,
    ws.node_id
FROM workflow_errors we
JOIN workflow_runs wr ON we.run_id = wr.run_id
JOIN workflows w ON wr.workflow_id = w.workflow_id
LEFT JOIN workflow_steps ws ON we.step_id = ws.step_id
ORDER BY we.occurred_at DESC
LIMIT 100;

-- Workflow performance summary
CREATE VIEW IF NOT EXISTS workflow_performance AS
SELECT
    w.workflow_id,
    w.name,
    COUNT(wr.run_id) as total_runs,
    SUM(CASE WHEN wr.status = 'completed' THEN 1 ELSE 0 END) as successful_runs,
    SUM(CASE WHEN wr.status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
    AVG(wr.duration_seconds) as avg_duration,
    SUM(wr.error_count) as total_errors,
    MAX(wr.started_at) as last_run_at
FROM workflows w
LEFT JOIN workflow_runs wr ON w.workflow_id = wr.workflow_id
GROUP BY w.workflow_id, w.name;
