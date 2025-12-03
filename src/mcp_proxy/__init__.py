"""
MCP Proxy Server

A proxy intermediary that sits between MCP clients and underlying MCP tool servers.
Implements field projection and grep search capabilities to optimize token usage,
privacy, and performance.
"""

__version__ = "0.1.0"
__author__ = "MCP Proxy Contributors"

from mcp_proxy.server import MCPProxyServer
from mcp_proxy.processors import ProjectionProcessor, GrepProcessor

__all__ = [
    "MCPProxyServer",
    "ProjectionProcessor",
    "GrepProcessor",
]

