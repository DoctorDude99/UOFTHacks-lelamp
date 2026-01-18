# Workflow System

This directory contains workflow definitions for LeLamp. Each workflow is organized in its own folder with specific files.

## Folder Structure

```
workflows/
├── README.md
├── wake_up/
│   ├── workflow.json       # Workflow graph definition
│   └── tools.py           # Workflow-specific tools
├── focus_session/
│   ├── workflow.json
│   └── tools.py
└── dancing/
    ├── workflow.json
    └── tools.py
```

## Creating a New Workflow

### 1. Create Workflow Folder

Create a new folder with your workflow name (e.g., `my_workflow/`)

### 2. Define workflow.json

Create a `workflow.json` file with the workflow graph:

```json
{
  "id": "my_workflow",
  "name": "My Workflow Name",
  "description": "Description of what this workflow does",
  "author": "your_name",
  "createdAt": "2025-11-06T00:00:00Z",
  "state_schema": {
    "my_variable": { "type": "boolean", "default": false },
    "counter": { "type": "integer", "default": 0 }
  },
  "nodes": [
    {
      "id": "step_1",
      "intent": "What the agent should do in this step",
      "preferred_actions": ["tool_name_to_call"]
    }
  ],
  "edges": [
    {
      "id": "start",
      "source": "START",
      "target": "step_1",
      "type": "normal"
    }
  ]
}
```

### 3. Create Workflow-Specific Tools

Create a `tools.py` file with custom tools for your workflow:

```python
from livekit.agents import function_tool

@function_tool
async def my_custom_tool(self, param: str) -> str:
    """
    Description of what this tool does.
    
    Args:
        param: Description of the parameter
    
    Returns:
        Description of what's returned
    """
    print(f"LeLamp: my_custom_tool called with {param}")
    # Your implementation here
    return f"Tool executed with {param}"
```

**Important Notes:**
- All tool functions must be `async`
- Use the `@function_tool` decorator from `livekit.agents`
- First parameter must be `self` (references the LeLamp agent instance)
- Tools have access to all agent properties: `self.motors_service`, `self.rgb_service`, etc.
- Tools are automatically registered when the workflow starts
- Tools are automatically unregistered when the workflow completes

### 4. Reference Tools in workflow.json

In your workflow nodes, reference your custom tools in the `preferred_actions` array:

```json
{
  "id": "my_step",
  "intent": "Call my custom tool",
  "preferred_actions": ["my_custom_tool"]
}
```

## Using Workflows

### Start a Workflow

The agent can start any workflow by calling:
```python
await agent.start_workflow("workflow_name")
```

### Execute Workflow Steps

1. Call `get_next_step()` to see the current step instructions
2. Execute the required actions (the LLM will call the preferred tools)
3. Call `complete_step(state_updates={"variable": value})` to advance
4. Repeat until the workflow reaches END

### Example Usage

```python
# Start the wake_up workflow
await agent.start_workflow("wake_up")

# Get the first step
step_info = await agent.get_next_step()
# Returns: "Node: wake_user_1, Intent: Calmly check if person is awake..."

# After completing the step's actions
await agent.complete_step(state_updates={"user_response_detected": True})

# Continue until workflow complete
```

## State Management

Workflows can maintain state using the `state_schema`:

- **Boolean**: `{ "type": "boolean", "default": false }`
- **Integer**: `{ "type": "integer", "default": 0 }`  
- **String**: `{ "type": "string", "default": "" }`
- **Object**: `{ "type": "object", "default": {} }`

Update state when completing steps:
```python
await agent.complete_step(state_updates={
    "user_response_detected": True,
    "attempt_count": 2
})
```

## Conditional Edges

Use state variables to create branching logic:

```json
{
  "id": "branch_edge",
  "source": "check_response",
  "target": {
    "true": "success_node",
    "false": "retry_node"
  },
  "state_key": "user_response_detected",
  "type": "condition"
}
```

## Built-in Agent Tools

Your workflow tools have access to all standard LeLamp capabilities:
- `self.motors_service` - Control motor movements
- `self.rgb_service` - Control LED lights  
- `self.workflow_service` - Access workflow state
- All standard agent tools (play_recording, set_rgb_solid, etc.)

## Examples

See existing workflows for reference:
- **wake_up**: Multi-step workflow with conditional branching and custom calendar tool
- **focus_session**: Energy-based routing with RGB color control
- **dancing**: Simple workflow template

