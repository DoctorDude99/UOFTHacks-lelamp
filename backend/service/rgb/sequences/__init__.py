"""RGB animation sequences for expressive lighting"""

from typing import Dict, Callable
import importlib
import os

# Animation registry - maps animation names to their functions and metadata
ANIMATIONS: Dict[str, dict] = {}

# Default FPS if config not loaded
_rgb_fps: float = 1.0

def set_rgb_fps(fps: float):
    """Set the global RGB FPS from config"""
    global _rgb_fps
    _rgb_fps = max(0.1, fps)  # Minimum 0.1 FPS

def get_frame_interval() -> float:
    """Get the frame interval (sleep time) based on configured FPS"""
    return 1.0 / _rgb_fps

def register_animation(name: str, description: str):
    """Decorator to register an animation function"""
    def decorator(func: Callable):
        ANIMATIONS[name] = {
            "function": func,
            "description": description,
            "name": name
        }
        return func
    return decorator

# Auto-import all animation modules
try:
    _current_dir = os.path.dirname(__file__)
    for filename in os.listdir(_current_dir):
        if filename.endswith('.py') and filename not in ('__init__.py', 'base.py'):
            module_name = filename[:-3]
            try:
                importlib.import_module(f'.{module_name}', package=__name__)
            except Exception as e:
                print(f"Warning: Failed to import animation module {module_name}: {e}")
except Exception as e:
    print(f"Warning: Failed to auto-import animations: {e}")

def get_animation(name: str) -> Callable:
    """Get animation function by name"""
    if name in ANIMATIONS:
        return ANIMATIONS[name]["function"]
    return None

def list_animations() -> Dict[str, str]:
    """Get all available animations with descriptions"""
    return {name: info["description"] for name, info in ANIMATIONS.items()}
