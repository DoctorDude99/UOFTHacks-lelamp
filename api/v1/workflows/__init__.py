"""
Workflow API endpoints.

Provides workflow listing and visualization data.
"""

from fastapi import APIRouter
from pathlib import Path
import json
from typing import List, Dict, Any

router = APIRouter()


def get_workflows_dir() -> Path:
    """Get the workflows directory path."""
    return Path(__file__).parent.parent.parent.parent / "lelamp" / "workflows"


def compute_workflow_layout(nodes: List[Dict], edges: List[Dict]) -> List[Dict]:
    """
    Compute node positions for visualization using improved layout.
    Handles branching workflows better by tracking paths and vertical slots.
    """
    # Build node ID set
    node_ids = {n["id"] for n in nodes}
    node_ids.add("START")
    node_ids.add("END")

    # Create graph adjacency and reverse adjacency
    adjacency = {nid: [] for nid in node_ids}
    reverse_adj = {nid: [] for nid in node_ids}

    for edge in edges:
        source = edge["source"]
        target = edge["target"]

        if isinstance(target, dict):
            # Conditional edge - multiple targets
            for t in target.values():
                if t in node_ids:
                    adjacency[source].append(t)
                    reverse_adj[t].append(source)
        else:
            if target in node_ids:
                adjacency[source].append(target)
                reverse_adj[target].append(source)

    # Compute levels using BFS from START (longest path for each node)
    levels = {"START": 0}
    queue = ["START"]
    visited = set()

    # Use multiple passes to get the maximum level for each node
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        current_level = levels[current]

        for neighbor in adjacency.get(current, []):
            # Always take the maximum level (longest path)
            new_level = current_level + 1
            if neighbor not in levels or new_level > levels[neighbor]:
                levels[neighbor] = new_level
            if neighbor not in visited:
                queue.append(neighbor)

    # Place END at the rightmost column
    max_level = max(lv for nid, lv in levels.items() if nid != "END") if levels else 0
    levels["END"] = max_level + 1

    # Group nodes by level (excluding END)
    level_groups: Dict[int, List[str]] = {}
    for nid, level in levels.items():
        if nid != "END":
            level_groups.setdefault(level, []).append(nid)

    # Sort nodes within each level for consistent ordering
    # Try to keep nodes that share parents close together
    for level in level_groups:
        if level > 0:
            # Sort by parent's position hint
            def parent_order(nid):
                parents = reverse_adj.get(nid, [])
                if parents:
                    # Get average parent level position
                    return sum(levels.get(p, 0) for p in parents) / len(parents)
                return 0
            level_groups[level].sort(key=parent_order)

    # Assign positions with more vertical spacing
    x_spacing = 220
    y_spacing = 140
    y_center = 250
    node_positions = {}

    for level, node_list in level_groups.items():
        x = level * x_spacing + 50

        # Center nodes vertically around y_center
        total_height = (len(node_list) - 1) * y_spacing
        y_start = y_center - total_height / 2

        for i, nid in enumerate(node_list):
            node_positions[nid] = {"x": x, "y": y_start + i * y_spacing}

    # Position END centered at rightmost column
    end_x = (max_level + 1) * x_spacing + 50
    node_positions["END"] = {"x": end_x, "y": y_center}

    # Build positioned nodes list
    positioned_nodes = []

    # Add START node
    if "START" in node_positions:
        positioned_nodes.append({
            "id": "START",
            "intent": "Workflow entry point",
            "preferred_actions": [],
            "type": "start",
            "position": node_positions["START"]
        })

    # Add workflow nodes
    for node in nodes:
        pos = node_positions.get(node["id"], {"x": 100, "y": 100})
        positioned_nodes.append({
            **node,
            "type": "action",
            "position": pos
        })

    # Add END node
    if "END" in node_positions:
        positioned_nodes.append({
            "id": "END",
            "intent": "Workflow complete",
            "preferred_actions": [],
            "type": "end",
            "position": node_positions["END"]
        })

    return positioned_nodes


@router.get("/")
async def list_workflows():
    """List all available workflows."""
    workflows_dir = get_workflows_dir()
    workflows = []

    if not workflows_dir.exists():
        return {"workflows": []}

    for workflow_dir in workflows_dir.iterdir():
        if workflow_dir.is_dir():
            workflow_file = workflow_dir / "workflow.json"
            if workflow_file.exists():
                try:
                    with open(workflow_file, 'r') as f:
                        data = json.load(f)
                        workflows.append({
                            "id": data.get("id"),
                            "name": data.get("name"),
                            "description": data.get("description"),
                            "author": data.get("author"),
                            "node_count": len(data.get("nodes", [])),
                            "edge_count": len(data.get("edges", []))
                        })
                except Exception as e:
                    print(f"Error loading workflow {workflow_dir.name}: {e}")

    return {"workflows": workflows}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get full workflow definition for visualization."""
    workflows_dir = get_workflows_dir()
    workflow_file = workflows_dir / workflow_id / "workflow.json"

    if not workflow_file.exists():
        return {"error": f"Workflow '{workflow_id}' not found"}

    try:
        with open(workflow_file, 'r') as f:
            data = json.load(f)

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        positioned_nodes = compute_workflow_layout(nodes, edges)

        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "description": data.get("description"),
            "author": data.get("author"),
            "state_schema": data.get("state_schema", {}),
            "nodes": positioned_nodes,
            "edges": edges
        }
    except Exception as e:
        return {"error": str(e)}
