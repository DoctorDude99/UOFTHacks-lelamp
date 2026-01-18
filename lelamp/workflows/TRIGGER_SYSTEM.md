# Workflow Trigger System

## Overview
The trigger system allows workflows to progress autonomously without constant user interaction.

## Trigger Types

### 1. time_interval
Checks periodically at specified intervals (e.g., every 5 minutes).
- **Config**: `interval_seconds` - how often to check
- **Action**: `prompt_agent` - instructs the agent to check and progress workflow
- **Use Case**: Bedside alarm checking if user is up every 5 minutes

### 2. keyword
Triggers when user says specific phrases.
- **Config**: `keywords` - list of phrases to match
- **Action**: `update_state` - automatically update workflow state
- **Use Case**: User says "I'm up" → updates user_awake = true

### 3. state_change
Triggers when a state variable changes.
- **Config**: `state_key` - which state variable to watch
- **Action**: `prompt_agent` or `update_state`
- **Use Case**: When user_awake changes to true, proceed to next step

## Database Schema

### workflow_active_triggers
Tracks active triggers for running workflows:
- `active_trigger_id` - Unique ID
- `run_id` - Which workflow run
- `trigger_type` - Type of trigger
- `trigger_config` - JSON configuration
- `next_check_at` - When to next check (for time-based)
- `check_interval_seconds` - Interval for time-based triggers
- `enabled` - Whether trigger is active

## Implementation Flow

1. **Workflow Start**: When workflow starts, create active triggers from `progression_triggers` in workflow.json
2. **Background Polling**: WorkflowService runs a background task every few seconds
3. **Trigger Check**: For each active trigger:
   - Time triggers: Check if `next_check_at` has passed
   - Keyword triggers: Check user speech against keywords
   - State triggers: Check if state has changed
4. **Trigger Action**: When triggered:
   - `prompt_agent`: Tell agent to check workflow and proceed
   - `update_state`: Automatically update state variables
5. **Agent Response**: Agent calls get_next_step() and executes workflow steps

## Example: Bedside Alarm

```json
{
  "progression_triggers": [
    {
      "type": "time_interval",
      "interval_seconds": 300,
      "action": "prompt_agent",
      "prompt": "Check bedside_alarm workflow progress"
    },
    {
      "type": "keyword",
      "keywords": ["i'm up", "i'm awake"],
      "action": "update_state",
      "state_updates": {"user_awake": true}
    }
  ]
}
```

**Flow**:
1. Alarm triggers at 7:30am
2. Workflow starts, creates 5-minute interval trigger
3. Agent asks "Are you up?"
4. 5 minutes pass → Trigger fires → Agent prompted to check again
5. User eventually says "I'm up" → keyword trigger → state updated → workflow completes
