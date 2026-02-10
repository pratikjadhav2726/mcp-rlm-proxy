"""
MCP-RLM Proxy Server

A proxy intermediary that sits between MCP clients and underlying MCP tool servers.
Implements field projection, advanced grep search, and automatic response caching
to optimise token usage, privacy, and performance.  Inspired by Recursive Language
Model principles (arXiv:2512.24601).
"""

__version__ = "0.2.0"
__author__ = "MCP Proxy Contributors"

from mcp_proxy.cache import SmartCacheManager
from mcp_proxy.processors import (
    BaseProcessor,
    GrepProcessor,
    ProcessorPipeline,
    ProcessorResult,
    ProjectionProcessor,
)
from mcp_proxy.server import MCPProxyServer

__all__ = [
    "MCPProxyServer",
    "ProjectionProcessor",
    "GrepProcessor",
    "BaseProcessor",
    "ProcessorResult",
    "ProcessorPipeline",
    "SmartCacheManager",
]
