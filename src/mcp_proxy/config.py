"""
Configuration loading utilities with Pydantic validation.

Uses MCP client-style JSON format (mcp.json) which matches the standard
configuration format used by Claude Desktop and other MCP clients.
Also supports proxy-specific settings under a ``proxySettings`` key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from mcp_proxy.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Proxy settings (non-server config)
# ---------------------------------------------------------------------------

@dataclass
class ProxySettings:
    """Runtime settings for the proxy itself.

    These are loaded from the optional ``proxySettings`` key in ``mcp.json``.
    """

    max_response_size: int = 8000
    """Character threshold above which a response is auto-truncated and cached."""

    cache_max_entries: int = 50
    """Maximum number of entries in the response cache."""

    cache_ttl_seconds: int = 300
    """Time-to-live in seconds for cache entries."""

    enable_auto_truncation: bool = True
    """Whether to automatically truncate + cache large responses."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProxySettings":
        return cls(
            max_response_size=data.get("maxResponseSize", cls.max_response_size),
            cache_max_entries=data.get("cacheMaxEntries", cls.cache_max_entries),
            cache_ttl_seconds=data.get("cacheTTLSeconds", cls.cache_ttl_seconds),
            enable_auto_truncation=data.get("enableAutoTruncation", cls.enable_auto_truncation),
        )


# ---------------------------------------------------------------------------
# Server configuration models (Pydantic)
# ---------------------------------------------------------------------------

class ServerConfig(BaseModel):
    """
    Configuration model for a single underlying MCP server.

    Attributes:
        name: Unique identifier for the server (used in tool names as "name_tool_name")
        command: Command to run the server (e.g., "npx", "python", "node", "uv")
        args: List of arguments to pass to the command
        env: Optional environment variables dictionary
    """

    name: str = Field(
        ...,
        description="Unique identifier for the server",
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    command: str = Field(
        ...,
        description="Command to run the server",
        min_length=1,
    )
    args: List[str] = Field(
        default_factory=list,
        description="List of arguments to pass to the command",
    )
    env: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional environment variables for the server process",
    )

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        v = v.strip()
        if not v:
            raise ValueError("Server name cannot be empty or whitespace only")
        return v

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Command cannot be empty or whitespace only")
        return v.strip()

    @field_validator("args")
    @classmethod
    def validate_args(cls, v: List[str]) -> List[str]:
        return v if v is not None else []

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "filesystem",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
            }
        }
    )


class ProxyConfig(BaseModel):
    """
    Root configuration model for the MCP Proxy Server.

    Attributes:
        underlying_servers: List of server configurations
    """

    underlying_servers: List[ServerConfig] = Field(
        default_factory=list,
        description="List of underlying MCP server configurations",
    )

    @field_validator("underlying_servers")
    @classmethod
    def validate_unique_names(cls, v: List[ServerConfig]) -> List[ServerConfig]:
        names = [server.name for server in v]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(
                f"Duplicate server names found: {', '.join(set(duplicates))}. "
                "Each server must have a unique name."
            )
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "underlying_servers": [
                    {
                        "name": "filesystem",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                    }
                ]
            }
        }
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(
    config_path: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], ProxySettings]:
    """
    Load and validate server configurations **and** proxy settings from
    ``mcp.json`` (MCP client format).

    Args:
        config_path: Optional path to the configuration file.
                     If *None*, looks for ``mcp.json`` in the current directory.

    Returns:
        A 2-tuple ``(server_configs, proxy_settings)``.

    Raises:
        ValidationError: If configuration validation fails.
    """
    config_file = Path(config_path) if config_path else Path("mcp.json")

    if not config_file.exists():
        logger.warning("Configuration file %s not found.", config_file)
        logger.warning("Using empty configuration (no servers).")
        logger.info("Create %s to configure underlying MCP servers.", config_file)
        return [], ProxySettings()

    logger.info("Loading configuration from %s", config_file)

    try:
        return _load_json_config(config_file)
    except (ValidationError, ValueError):
        raise
    except Exception as e:
        error_msg = f"Failed to load {config_file}: {e}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e


def _load_json_config(
    config_file: Path,
) -> tuple[List[Dict[str, Any]], ProxySettings]:
    """
    Load configuration from MCP client-style JSON format.

    Expected format::

        {
          "mcpServers": {
            "server_name": {
              "command": "npx",
              "args": ["-y", "package"],
              "env": {"KEY": "value"}
            }
          },
          "proxySettings": {
            "maxResponseSize": 8000,
            "cacheMaxEntries": 50,
            "cacheTTLSeconds": 300,
            "enableAutoTruncation": true
          }
        }
    """
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            raw_config = json.load(f)

        if raw_config is None or not raw_config:
            logger.info("Config file is empty. Using empty configuration.")
            return [], ProxySettings()

        if "mcpServers" not in raw_config:
            raise ValueError(
                f"Invalid configuration in {config_file}: "
                "Missing 'mcpServers' key. "
                'Expected format: {"mcpServers": {"server_name": {...}}}'
            )

        mcp_servers = raw_config["mcpServers"]
        if not isinstance(mcp_servers, dict):
            raise ValueError(
                f"Invalid configuration in {config_file}: "
                "'mcpServers' must be an object/dictionary"
            )

        # Parse proxy settings
        proxy_settings_raw = raw_config.get("proxySettings", {})
        proxy_settings = ProxySettings.from_dict(proxy_settings_raw) if proxy_settings_raw else ProxySettings()

        # Convert MCP client format → internal list
        servers: List[Dict[str, Any]] = []
        for server_name, server_config in mcp_servers.items():
            if not isinstance(server_config, dict):
                logger.warning("Skipping invalid server config for '%s': not a dictionary", server_name)
                continue

            server_dict: Dict[str, Any] = {
                "name": server_name,
                "command": server_config.get("command"),
                "args": server_config.get("args", []),
            }
            if "env" in server_config:
                server_dict["env"] = server_config["env"]
            servers.append(server_dict)

        # Validate with Pydantic
        try:
            proxy_config = ProxyConfig(
                underlying_servers=[ServerConfig.model_validate(s) for s in servers]
            )
            logger.info(
                "Successfully loaded %d server(s) from %s",
                len(proxy_config.underlying_servers),
                config_file,
            )
            return (
                [server.model_dump() for server in proxy_config.underlying_servers],
                proxy_settings,
            )
        except ValidationError as e:
            logger.error("Configuration validation failed: %s", e)
            errors = []
            for error in e.errors():
                field_path = " -> ".join(str(loc) for loc in error["loc"])
                errors.append(f"  {field_path}: {error['msg']}")
            error_message = "Configuration validation errors:\n" + "\n".join(errors)
            logger.error(error_message)
            raise ValueError(f"Invalid configuration in {config_file}:\n{error_message}") from e

    except json.JSONDecodeError as e:
        error_msg = f"JSON parsing error in {config_file}: {e}"
        logger.error(error_msg, exc_info=True)
        raise ValueError(error_msg) from e
    except FileNotFoundError:
        logger.warning("Config file %s not found.", config_file)
        return [], ProxySettings()
    except (ValidationError, ValueError):
        raise
    except Exception as e:
        error_msg = f"Unexpected error loading config from {config_file}: {e}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e
