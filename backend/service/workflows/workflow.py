from dataclasses import dataclass, field
from typing import Dict, List, Any, Union
from enum import Enum

class EdgeType(Enum):
    NORMAL = "normal"
    CONDITION = "condition"

@dataclass
class Node:
    id: str
    intent: str
    preferred_actions: List[str] = field(default_factory=list)

@dataclass
class Edge:
    id: str
    source: str
    target: Union[str, Dict[str, str]]  # Can be string or conditional dict
    type: EdgeType
    state_key: str | None = None # Which state variable to check for the condition
    
@dataclass
class StateVariable:
    type: str
    default: Any

@dataclass
class Workflow:
    id: str
    name: str
    description: str
    author: str
    createdAt: str
    state_schema: Dict[str, StateVariable]
    nodes: Dict[str, Node]  # Indexed by node ID for O(1) lookup
    edges: Dict[str, Edge]  # Indexed by source node (one edge per source)
    
    @classmethod
    def from_json(cls, data: dict) -> 'Workflow':
        """Convert JSON dict to Workflow object"""
        # Parse state schema
        state_schema = {
            key: StateVariable(**value) 
            for key, value in data['state_schema'].items()
        }
        
        # Parse nodes and index by ID
        nodes = {
            node['id']: Node(**node) 
            for node in data['nodes']
        }
        
        # Parse edges indexed by source (one edge per source)
        edges_by_source = {}
        for edge_data in data['edges']:
            edge = Edge(
                id=edge_data['id'],
                source=edge_data['source'],
                target=edge_data['target'],
                type=EdgeType(edge_data['type']),
                state_key=edge_data.get('state_key')
            )
            edges_by_source[edge.source] = edge
        
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            author=data['author'],
            createdAt=data['createdAt'],
            state_schema=state_schema,
            nodes=nodes,
            edges=edges_by_source
        )