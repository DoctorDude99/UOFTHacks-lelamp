#!/usr/bin/env python
"""Utility functions for managing device configuration (port only, ID is always 'lelamp')."""

import yaml
from pathlib import Path

# Use ~/.lelamp/config.yaml as the canonical config location
from lelamp.user_data import get_config_path as _get_config_path, USER_CONFIG_FILE


def save_config(port: str) -> None:
    """Save port to ~/.lelamp/config.yaml file."""
    config_file = _get_config_path()

    # Load existing config or create new one
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # Update port (id is always 'lelamp')
    config['port'] = port

    # Always save to user config location
    with open(USER_CONFIG_FILE, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Config saved to {USER_CONFIG_FILE} with port {port}")


def load_config() -> str | None:
    """Load port from ~/.lelamp/config.yaml. Returns port or None if not found."""
    config_file = _get_config_path()

    if not config_file.exists():
        return None

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        if config is None:
            return None

        return config.get("port")
    except (yaml.YAMLError, KeyError, IOError):
        return None


def get_config_path() -> str:
    """Return the path to the config file (~/.lelamp/config.yaml)."""
    return str(_get_config_path())

