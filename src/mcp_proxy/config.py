"""
Configuration loading utilities.
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml


def load_config(config_path: str = "config.yaml") -> List[Dict[str, Any]]:
    """
    Load server configurations from YAML file.

    Args:
        config_path: Path to the configuration file

    Returns:
        List of server configurations
    """
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            if config is None:
                return []
            return config.get("underlying_servers", []) or []
    except FileNotFoundError:
        print(f"Config file {config_path} not found. Using empty configuration.")
        return []
    except Exception as e:
        print(f"Error loading config: {e}. Using empty configuration.")
        return []

