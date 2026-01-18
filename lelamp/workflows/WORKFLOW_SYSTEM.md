# LeLamp Workflow System - Complete Documentation

## 🎯 Overview

The LeLamp Workflow System is a comprehensive, enterprise-grade agentic workflow platform that enables LeLamp to execute complex, multi-step tasks with full monitoring, error handling, and state persistence.

### Key Features

✅ **Graph-Based Execution** - Define workflows as directed graphs with conditional branching
✅ **Dynamic Tool Loading** - Workflows can register custom tools on-demand
✅ **SQLite Persistence** - All runs, steps, states, and errors logged to database
✅ **Categorized Error Tracking** - Errors classified by type (System, LLM, Vision, etc.)
✅ **State Management** - Track and persist state variables across workflow execution
✅ **Performance Monitoring** - Built-in statistics and performance metrics
✅ **Voice + Event Triggers** - Workflows can be triggered by voice or events (alarms, timers, etc.)
✅ **LLM + User Input** - Workflows can incorporate LLM reasoning and user responses
✅ **Visual Debugging** - Complete audit trail of every step, action, and state change

---

## 📁 Architecture

### Directory Structure

```
lelamp/
├── service/
│   └── workflows/
│       ├── __init__.py
│       ├── workflow.py                # Data structures (Node, Edge, Workflow)
│       ├── workflow_service.py        # Main execution engine
│       ├── db_manager.py              # Database persistence layer
│       └── db_schema.sql              # SQLite schema
└── workflows/
    ├── README.md
    ├── WORKFLOW_SYSTEM.md             # This file
    ├── bedside_alarm/
    │   ├── workflow.json              # Workflow graph definition
    │   └── tools.py                   # Custom workflow tools
    ├── wake_up/
    │   ├── workflow.json
    │   └── tools.py
    └── focus_session/
        ├── workflow.json
        └── tools.py
```

### Core Components

#### 1. **WorkflowService** (lelamp/service/workflows/workflow_service.py)
The main execution engine that:
- Loads and validates workflow graphs
- Manages workflow execution (start, stop, step-by-step)
- Dynamically loads/unloads workflow-specific tools
- Handles state transitions and conditional routing
- Integrates with database for persistence

#### 2. **WorkflowDatabase** (lelamp/service/workflows/db_manager.py)
The persistence layer that:
- Stores workflow metadata, runs, steps, and errors
- Tracks state changes with full history
- Provides monitoring queries and views
- Categorizes errors for debugging
- Generates performance statistics

#### 3. **Workflow Data Structures** (lelamp/service/workflows/workflow.py)
- `Workflow`: Complete workflow definition
- `Node`: Individual step with intent and preferred actions
- `Edge`: Transition between nodes (normal or conditional)
- `StateVariable`: Typed state variables with defaults

#### 4. **Database Schema** (lelamp/service/workflows/db_schema.sql)
- `workflows`: Workflow metadata and configuration
- `workflow_runs`: Execution instances
- `workflow_steps`: Step-by-step execution log
- `workflow_errors`: Categorized error tracking
- `workflow_state`: Current state variables
- `workflow_triggers`: Automatic trigger configuration
- `workflow_stats`: Aggregated statistics

---

## 🚀 Creating a Workflow

### Step 1: Create Workflow Directory

```bash
mkdir lelamp/workflows/my_workflow
```

### Step 2: Define workflow.json

```json
{
  "id": "my_workflow",
  "name": "My Workflow Name",
  "description": "What this workflow does",
  "author": "your_name",
  "createdAt": "2025-11-27T00:00:00Z",
  "triggers": ["voice_command", "alarm_trigger"],
  "state_schema": {
    "step_completed": { "type": "boolean", "default": false },
    "attempt_count": { "type": "integer", "default": 0 },
    "user_data": { "type": "object", "default": {} }
  },
  "nodes": [
    {
      "id": "step_1",
      "intent": "What the agent should do in this step",
      "preferred_actions": ["tool_name_to_call"]
    },
    {
      "id": "step_2",
      "intent": "Next step instructions",
      "preferred_actions": []
    }
  ],
  "edges": [
    {
      "id": "start",
      "source": "START",
      "target": "step_1",
      "type": "normal"
    },
    {
      "id": "e1",
      "source": "step_1",
      "target": {
        "true": "step_2",
        "false": "step_1"
      },
      "state_key": "step_completed",
      "type": "condition"
    },
    {
      "id": "e2",
      "source": "step_2",
      "target": "END",
      "type": "normal"
    }
  ]
}
```

### Step 3: Create Workflow Tools (tools.py)

```python
from livekit.agents import function_tool

@function_tool
async def my_custom_tool(self, param: str) -> str:
    """
    Tool description for the LLM to understand when to use it.

    Args:
        param: Parameter description

    Returns:
        What the tool returns
    """
    print(f"LeLamp: my_custom_tool called with {param}")

    # Access agent services
    # self.animation_service
    # self.rgb_service
    # self.vision_service
    # etc.

    return f"Tool executed with {param}"
```

**Important Tool Notes:**
- All tools must be `async` functions
- Use `@function_tool` decorator from `livekit.agents`
- First parameter must be `self` (references the LeLamp agent)
- Tools have access to ALL agent properties and services
- Tools are auto-loaded when workflow starts
- Tools are auto-unloaded when workflow completes

---

## 🎮 Using Workflows

### Starting a Workflow (Voice Command)

**User:** "Start the bedside alarm workflow"

**Agent internally calls:**
```python
run_id = await agent.start_workflow("bedside_alarm")
```

### Starting a Workflow (Event Trigger)

```python
# When alarm goes off
if alarm_triggered:
    workflow_service.start_workflow(
        workflow_name="bedside_alarm",
        trigger_type="alarm_trigger",
        trigger_data={"alarm_id": alarm_id, "time": current_time}
    )
```

### Executing Workflow Steps

The workflow executes in a loop:

1. **Get Next Step**
   ```python
   step_info = await agent.get_next_step()
   # Returns: Node intent, required actions, state variables
   ```

2. **Agent Executes Step**
   - LLM reads the intent
   - LLM decides what to do (may call preferred tools)
   - Agent performs actions

3. **Complete Step**
   ```python
   result = await agent.complete_step(
       state_updates={"step_completed": True, "attempt_count": 1}
   )
   # Workflow advances to next node based on conditional edges
   ```

4. **Repeat until workflow reaches END node**

---

## 📊 State Management

### Defining State Variables

```json
"state_schema": {
  "user_awake": { "type": "boolean", "default": false },
  "attempt_count": { "type": "integer", "default": 0 },
  "user_name": { "type": "string", "default": "" },
  "calendar_data": { "type": "object", "default": {} }
}
```

### Updating State

```python
# In complete_step
await agent.complete_step(state_updates={
    "user_awake": True,
    "attempt_count": 2,
    "user_name": "Alice"
})
```

### Conditional Routing Based on State

```json
{
  "id": "branch_edge",
  "source": "check_awake",
  "target": {
    "true": "say_good_morning",
    "false": "try_again"
  },
  "state_key": "user_awake",
  "type": "condition"
}
```

**How it works:**
- If `user_awake == true` → go to "say_good_morning"
- If `user_awake == false` → go to "try_again"

---

## 🔍 Monitoring & Debugging

### Error Classification

All errors are categorized for easier debugging:

| Error Class | Description | Examples |
|-------------|-------------|----------|
| **System** | Hardware, OS, resource errors | Motor failure, file not found, out of memory |
| **LLM** | LLM API errors, generation failures | API timeout, rate limit, invalid response |
| **Vision** | Camera, vision processing errors | Camera disconnected, face detection failed |
| **Network** | Connection, timeout errors | WiFi down, API unreachable |
| **State** | Invalid state transitions | Missing state variable, invalid state value |
| **Tool** | Tool execution failures | Tool exception, invalid parameters |
| **Human** | User input issues | User didn't respond, unclear input |
| **Unexpected** | Unknown/unhandled exceptions | Any uncaught exception |

### Database Queries for Monitoring

```python
# Get all active workflows
active_runs = workflow_service.db.get_active_runs()

# Get workflow performance stats
stats = workflow_service.db.get_workflow_performance()

# Get recent errors
errors = workflow_service.db.get_recent_errors(limit=50)

# Get detailed run information
run_details = workflow_service.get_run_details(run_id)

# Get workflow status
status = workflow_service.get_workflow_status("bedside_alarm")
```

### Audit Trail

Every workflow run stores:
- **Run metadata**: Trigger type, start/end time, duration, status
- **Step-by-step log**: Each node execution, actions taken, LLM responses
- **State history**: Before/after snapshots, what changed, when
- **Errors**: Full stack traces, context, recovery actions
- **Performance metrics**: Duration per step, total errors, success rate

---

## 🎨 Example: Bedside Alarm Workflow

### Workflow Graph

```
START → wait_for_alarm → ring_alarm → good_morning → wait_1min → check_sleeping
                                                                      ├─ [awake] → weather_news → END
                                                                      └─ [sleeping] → wake_up → wait_response
                                                                            ├─ [snooze] → set_timer → go_sleep → snooze_wakeup → check_phone
                                                                            │                                                         ├─ [phone] → scold → alarm → weather_news → END
                                                                            │                                                         └─ [no phone] → weather_news → END
                                                                            └─ [no snooze] → weather_news → END
```

### Key Features

✅ Vision-based sleeping detection
✅ Snooze with 5-minute timer
✅ Phone usage detection after snooze
✅ Adaptive responses based on user behavior
✅ Integration with weather/news APIs
✅ Sleep mode during snooze period

### State Variables

- `alarm_triggered`: Has the alarm gone off?
- `user_awake`: Is the user awake (vision check)?
- `user_said_snooze`: Did user ask to snooze?
- `playing_on_phone`: Is user on their phone (vision check)?
- `snoozed_once`: Have we snoozed already?

### Custom Tools

- `play_alarm_sound()`: Play wake-up sound
- `wait_seconds(duration)`: Wait for N seconds
- `check_user_sleeping_vision()`: Vision-based sleep detection
- `check_user_phone_vision()`: Vision-based phone usage detection

---

## 🔧 Agent Integration

### Required Agent Tools

Add these tools to your `LeLamp` agent class in `main.py`:

```python
@function_tool
async def get_available_workflows(self) -> str:
    """Get list of all available workflows"""
    workflows = self.workflow_service.get_available_workflows()
    return f"Available workflows: {', '.join(workflows)}"

@function_tool
async def list_enabled_workflows(self) -> str:
    """Get list of enabled workflows with their current status"""
    workflows = self.workflow_service.list_enabled_workflows()
    # Format and return workflow status
    ...

@function_tool
async def start_workflow(self, workflow_name: str) -> str:
    """Start a workflow execution"""
    run_id = self.workflow_service.start_workflow(
        workflow_name=workflow_name,
        trigger_type="voice_command"
    )
    return f"Started workflow '{workflow_name}' (run_id: {run_id})"

@function_tool
async def get_next_step(self) -> str:
    """Get the current step in the active workflow"""
    return self.workflow_service.get_next_step()

@function_tool
async def complete_step(
    self,
    state_updates: Optional[Dict[str, Any]] = None
) -> str:
    """Complete the current step and advance to next"""
    return self.workflow_service.complete_step(state_updates=state_updates)

@function_tool
async def get_workflow_status(self, workflow_name: str = None) -> str:
    """Get status and history of a workflow"""
    status = self.workflow_service.get_workflow_status(workflow_name)
    # Format and return status info
    ...
```

### Service Initialization

```python
# In LeLamp.__init__()
self.workflow_service = WorkflowService(db_path="lelamp.db")
self.workflow_service.set_agent(self)

# Sync all workflows to database
self.workflow_service.sync_workflows_to_db()

# Optionally preload workflow tools
# self.workflow_service.preload_workflow_tools(["bedside_alarm", "wake_up"])
```

---

## 📝 Agent Instructions

Add this to your agent's instructions:

```
You can execute complex multi-step workflows! Workflows are like mini-programs
that guide you through a series of steps to accomplish a task.

Available workflow tools:
- get_available_workflows(): See what workflows exist
- list_enabled_workflows(): See active workflows and their status
- start_workflow(name): Begin a workflow
- get_next_step(): See what to do next in the active workflow
- complete_step(state_updates): Mark current step done and advance
- get_workflow_status(name): Check workflow history and stats

When executing a workflow:
1. Call start_workflow("workflow_name") to begin
2. Call get_next_step() to see the current step's intent and required actions
3. Execute the step (follow the intent, call the preferred_actions tools)
4. Call complete_step(state_updates={...}) to advance to the next step
5. Repeat steps 2-4 until the workflow is complete

Workflows have STATE that you can update. When completing a step, you can
update state variables like: complete_step(state_updates={"user_awake": true})

The workflow will automatically route to different nodes based on state!
```

---

## 🚨 Error Handling

### Automatic Error Logging

All errors during workflow execution are automatically logged with:
- Error classification (System, LLM, Vision, etc.)
- Full stack trace
- Context (current state, step, inputs)
- Timestamp
- Run and step IDs for tracing

### Error Recovery

```python
try:
    # Workflow step execution
    result = await tool()
except VisionError as e:
    # Log error
    workflow_service.db.log_error(
        run_id=current_run_id,
        step_id=current_step_id,
        error_class=ErrorClass.VISION,
        error_type="VisionProcessingError",
        error_message=str(e),
        stack_trace=traceback.format_exc(),
        recoverable=True,
        recovery_action="Defaulting to non-vision fallback"
    )

    # Recover gracefully
    result = fallback_behavior()
```

---

## 📈 Performance Monitoring

### Built-in Stats

The database automatically tracks:
- Total runs per workflow
- Success vs failure rates
- Average/min/max duration
- Total errors
- Last run timestamp

### Query Performance

```sql
-- Get workflow performance summary
SELECT * FROM workflow_performance;

-- Get recent errors by class
SELECT error_class, COUNT(*) as count
FROM workflow_errors
WHERE occurred_at > datetime('now', '-7 days')
GROUP BY error_class;

-- Get slowest workflow steps
SELECT node_id, AVG(duration_seconds) as avg_duration
FROM workflow_steps
GROUP BY node_id
ORDER BY avg_duration DESC
LIMIT 10;
```

---

## 🔮 Future Enhancements

- [ ] Visual workflow editor (drag-and-drop nodes/edges)
- [ ] Real-time workflow monitoring dashboard
- [ ] Workflow versioning and rollback
- [ ] Community workflow marketplace
- [ ] A/B testing different workflow paths
- [ ] Machine learning for optimal routing
- [ ] Parallel step execution
- [ ] Workflow composition (sub-workflows)
- [ ] External API integrations (IFTTT, Zapier)
- [ ] Natural language workflow generation

---

## 📚 Additional Resources

- **Example Workflows**: See `wake_up/`, `focus_session/`, `bedside_alarm/`
- **Database Schema**: `lelamp/service/workflows/db_schema.sql`
- **Error Classes**: `lelamp/service/workflows/db_manager.py`
- **Workflow Service**: `lelamp/service/workflows/workflow_service.py`

---

Built with ❤️ by the Human Computer Lab team
