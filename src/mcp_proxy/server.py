"""
MCP-RLM Proxy Server implementation.

Provides a transparent proxy between MCP clients and underlying MCP tool
servers, with automatic large-response handling and first-class proxy tools
(``proxy_filter``, ``proxy_search``, ``proxy_explore``) for efficient
recursive exploration of tool outputs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Union

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Content, TextContent, Tool, ServerCapabilities

from mcp_proxy.cache import AgentAwareCacheManager, SmartCacheManager, AsyncCacheManager
from mcp_proxy.config import ProxySettings
from mcp_proxy.executor_manager import ExecutorManager
from mcp_proxy.logging_config import get_logger
from mcp_proxy.rlm_processor import RecursiveContextManager
from mcp_proxy.processors import (
    GrepProcessor,
    ProcessorPipeline,
    ProcessorResult,
    ProjectionProcessor,
    _measure_content,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class ConnectionPoolMetrics:
    """Tracks metrics for connection pool and token savings."""
    
    def __init__(self) -> None:
        self.total_calls = 0
        self.total_original_tokens = 0
        self.total_filtered_tokens = 0
        self.projection_calls = 0
        self.grep_calls = 0
        self.auto_truncation_calls = 0
        self.connection_count = 0
        self.failed_connections = 0
        
    def record_call(
        self,
        original_tokens: int,
        filtered_tokens: int,
        used_projection: bool = False,
        used_grep: bool = False,
        auto_truncated: bool = False,
    ) -> None:
        self.total_calls += 1
        self.total_original_tokens += original_tokens
        self.total_filtered_tokens += filtered_tokens
        if used_projection:
            self.projection_calls += 1
        if used_grep:
            self.grep_calls += 1
        if auto_truncated:
            self.auto_truncation_calls += 1
    
    def get_summary(self) -> Dict[str, Any]:
        if self.total_original_tokens == 0:
            savings_percent = 0.0
        else:
            savings_percent = (
                (self.total_original_tokens - self.total_filtered_tokens)
                / self.total_original_tokens
                * 100
            )
        return {
            "total_calls": self.total_calls,
            "projection_calls": self.projection_calls,
            "grep_calls": self.grep_calls,
            "auto_truncation_calls": self.auto_truncation_calls,
            "total_original_tokens": self.total_original_tokens,
            "total_filtered_tokens": self.total_filtered_tokens,
            "tokens_saved": self.total_original_tokens - self.total_filtered_tokens,
            "savings_percent": round(savings_percent, 2),
            "active_connections": self.connection_count,
            "failed_connections": self.failed_connections,
        }
    
    def log_summary(self) -> None:
        summary = self.get_summary()
        if summary["total_calls"] > 0:
            logger.info("=== Proxy Performance Summary ===")
            logger.info("  Total calls: %d", summary["total_calls"])
            logger.info("  Projection calls: %d", summary["projection_calls"])
            logger.info("  Grep calls: %d", summary["grep_calls"])
            logger.info("  Auto-truncated: %d", summary["auto_truncation_calls"])
            logger.info("  Original tokens: %d", summary["total_original_tokens"])
            logger.info("  Filtered tokens: %d", summary["total_filtered_tokens"])
            logger.info("  Tokens saved: %d", summary["tokens_saved"])
            logger.info("  Savings: %.1f%%", summary["savings_percent"])
            logger.info("  Active connections: %d", summary["active_connections"])
            logger.info("  Failed connections: %d", summary["failed_connections"])


# ---------------------------------------------------------------------------
# Proxy server
# ---------------------------------------------------------------------------

_SERVER_INSTRUCTIONS = (
    "This proxy aggregates tools from multiple MCP servers. "
    "Tool names are prefixed with the server name (e.g. filesystem_read_file). "
    "When a tool response is large it is automatically truncated and cached. "
    "The truncated response includes a cache_id you can use with these proxy "
    "tools to drill into the data without re-executing the original call:\n"
    "  - proxy_filter: project/filter specific fields from cached or fresh results\n"
    "  - proxy_search: grep/bm25/fuzzy/context search on cached or fresh results\n"
    "  - proxy_explore: discover data structure (keys, types, sizes) without loading content\n"
    "All proxy tool parameters are flat top-level strings/arrays/integers — no nested objects required."
)


class MCPProxyServer:
    """MCP-RLM Proxy Server that intermediates between clients and underlying servers."""

    def __init__(
        self,
        underlying_servers: Optional[List[Dict[str, Any]]] = None,
        proxy_settings: Optional[ProxySettings] = None,
    ) -> None:
        self.settings = proxy_settings or ProxySettings()

        self.server = Server("mcp-rlm-proxy", instructions=_SERVER_INSTRUCTIONS)

        self.underlying_servers: Dict[str, ClientSession] = {}
        self.server_configs = underlying_servers or []
        self.tools_cache: Dict[str, List[Tool]] = {}

        # Executor for CPU-bound work
        self.executor_manager = ExecutorManager()
        
        # Processors with executor
        self.projection_processor = ProjectionProcessor(self.executor_manager)
        self.grep_processor = GrepProcessor(self.executor_manager)
        self.pipeline = ProcessorPipeline([self.projection_processor, self.grep_processor])

        # RLM-style recursive context manager for exploration hints
        self.recursive_context_manager = RecursiveContextManager()

        # Response cache (agent-aware if enabled)
        self.cache: AsyncCacheManager
        if self.settings.enable_agent_isolation:
            self.cache = AgentAwareCacheManager(
                max_entries_per_agent=self.settings.max_entries_per_agent,
                max_memory_per_agent=self.settings.max_memory_per_agent,
                ttl_seconds=self.settings.cache_ttl_seconds,
                max_total_agents=self.settings.max_total_agents,
                enable_agent_isolation=True,
            )
        else:
            # Backward compatibility: use simple cache
            self.cache = SmartCacheManager(
                max_entries=self.settings.cache_max_entries,
                ttl_seconds=self.settings.cache_ttl_seconds,
            )

        # Connection bookkeeping
        self._server_contexts: Dict[str, Any] = {}
        self._connection_tasks: Dict[str, asyncio.Task] = {}
        
        # Agent/session tracking for cache isolation
        self._session_to_agent: Dict[str, str] = {}
        self._agent_counter = 0
        self._agent_lock = asyncio.Lock()

        # Metrics
        self.metrics = ConnectionPoolMetrics()

        # Register handlers
        self._register_handlers()

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        """Register MCP server handlers (tools/list + tools/call)."""

        # ── list_tools ────────────────────────────────────────────────
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """Aggregate tools from all underlying servers plus proxy tools."""
            all_tools: List[Tool] = []

            logger.debug("list_tools called")
            logger.debug("underlying_servers keys: %s", list(self.underlying_servers.keys()))
            logger.debug("tools_cache keys: %s", list(self.tools_cache.keys()))

            # ── 1. Register first-class proxy tools ───────────────────
            all_tools.extend(self._build_proxy_tools())

            # ── 2. Cached tools (clean pass-through) ──────────────────
            for server_name, cached_tools in self.tools_cache.items():
                logger.debug("Using %d cached tools from %s", len(cached_tools), server_name)
                for tool in cached_tools:
                    all_tools.append(
                        Tool(
                        name=f"{server_name}_{tool.name}",
                            description=(tool.description or "") + f"\n(via {server_name})",
                            inputSchema=self._clean_schema(tool.inputSchema),
                    )
                    )

            # ── 3. Fetch from servers with cache misses ───────────────
            servers_to_fetch = [
                (sn, sess)
                for sn, sess in self.underlying_servers.items()
                if sn not in self.tools_cache or not self.tools_cache.get(sn)
            ]

            if servers_to_fetch:
                logger.debug("Fetching tools from %d server(s) in parallel", len(servers_to_fetch))

                async def _fetch(sn: str, sess: ClientSession) -> tuple[str, List[Tool]]:
                    try:
                        result = await asyncio.wait_for(sess.list_tools(), timeout=10.0)
                        return sn, result.tools
                    except asyncio.TimeoutError:
                        logger.error("Timeout fetching tools from %s", sn)
                        return sn, []
                    except Exception as exc:
                        logger.error("Error listing tools from %s: %s", sn, exc, exc_info=True)
                        return sn, []

                results = await asyncio.gather(
                    *(_fetch(sn, sess) for sn, sess in servers_to_fetch),
                    return_exceptions=True,
                )

                for res in results:
                    if isinstance(res, Exception):
                        logger.error("Exception during parallel tool fetch: %s", res, exc_info=True)
                        continue
                    server_name, tools = res
                    if tools:
                        self.tools_cache[server_name] = tools
                        logger.info("Loaded %d tools from %s", len(tools), server_name)
                        for tool in tools:
                            all_tools.append(
                                Tool(
                                name=f"{server_name}_{tool.name}",
                                    description=(tool.description or "") + f"\n(via {server_name})",
                                    inputSchema=self._clean_schema(tool.inputSchema),
                            )
                            )
                    else:
                        logger.warning("%s returned 0 tools", server_name)

            logger.debug("Returning %d total tools", len(all_tools))
            return all_tools

        # ── call_tool ─────────────────────────────────────────────────
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[Content]:
            """Intercept tool calls, forward to underlying servers, and apply transformations."""
            logger.debug("call_tool called: %s", name)

            # ── Proxy tools ───────────────────────────────────────────
            if name == "proxy_filter":
                return await self._handle_proxy_filter(arguments)
            if name == "proxy_search":
                return await self._handle_proxy_search(arguments)
            if name == "proxy_explore":
                return await self._handle_proxy_explore(arguments)

            # ── Validate arguments ────────────────────────────────────
            if not isinstance(arguments, dict):
                raise ValueError(f"Arguments must be a dictionary, got: {type(arguments)}")

            # ── Resolve server + tool ─────────────────────────────────
            server_name, tool_name = self._resolve_tool_name(name)

            session = self.underlying_servers[server_name]
            logger.debug("Parsed: server=%s, tool=%s", server_name, tool_name)

            # ── Call underlying tool ──────────────────────────────────
            try:
                logger.debug("Calling tool %s on %s with timeout 60s", tool_name, server_name)
                result = await asyncio.wait_for(session.call_tool(tool_name, arguments), timeout=60.0)
                logger.debug("Tool call completed successfully")
            except asyncio.TimeoutError:
                msg = f"Timeout calling tool {tool_name} on {server_name} (60s)"
                logger.error(msg)
                return [TextContent(type="text", text=f"Error: {msg}")]
            except Exception as exc:
                msg = f"Error calling tool {tool_name} on {server_name}: {exc}"
                logger.error(msg, exc_info=True)
                return [TextContent(type="text", text=f"Error: {msg}")]

            content: List[Content] = list(result.content) if hasattr(result, "content") else []
            original_size = _measure_content(content)

            # ── Auto-truncation + caching ─────────────────────────────
            new_size = _measure_content(content)
            auto_truncated = False
            exploration_metadata: Optional[Dict[str, Any]] = None

            if (
                self.settings.enable_auto_truncation
                and new_size > self.settings.max_response_size
            ):
                # Use agent_id if available
                agent_id = await self._get_agent_id()
                cache_id = await self.cache.put(content, name, arguments, agent_id=agent_id)

                # Generate RLM exploration hints based on the full content
                try:
                    exploration_metadata = self.recursive_context_manager.create_exploration_metadata(
                        content,
                        cache_id=cache_id,
                    )
                except Exception as exc:
                    logger.debug("Failed to generate RLM exploration metadata: %s", exc, exc_info=True)

                truncated_text = self._truncate_content(content, self.settings.max_response_size)
                hint_lines = [
                    f"--- Response truncated ({new_size:,} chars). "
                    f"Full result cached as cache_id=\"{cache_id}\". "
                    "Use proxy_filter, proxy_search, or proxy_explore with this cache_id "
                    "to drill into the data. ---"
                ]

                # If we have RLM hints, surface a concise textual summary for agents
                if exploration_metadata and exploration_metadata.get("rlm_hints"):
                    rlm_hints = exploration_metadata["rlm_hints"]
                    steps = rlm_hints.get("next_steps") or []
                    hint_lines.append("")
                    hint_lines.append("--- RLM exploration suggestions ---")
                    for idx, step in enumerate(steps[:3], start=1):
                        tool = step.get("tool") or "tool"
                        when = step.get("when") or ""
                        hint_lines.append(f"{idx}. Call {tool} when: {when}")
                    extra_hint = rlm_hints.get("hint")
                    if extra_hint:
                        hint_lines.append("")
                        hint_lines.append(extra_hint)

                hint = "\n\n" + "\n".join(hint_lines)
                content = [TextContent(type="text", text=truncated_text + hint)]
                auto_truncated = True
                new_size = _measure_content(content)

            # ── Optional RLM hints for non-truncated responses ────────
            if not auto_truncated:
                try:
                    exploration_metadata = self.recursive_context_manager.create_exploration_metadata(
                        content,
                    )
                except Exception as exc:
                    logger.debug("Failed to generate RLM exploration metadata: %s", exc, exc_info=True)

            # ── Metrics ───────────────────────────────────────────────
            # Legacy `_meta`-driven projection/grep support has been fully removed.
            # `used_projection` and `used_grep` are now reserved for first-class
            # proxy tools (see `_handle_proxy_filter` and `_handle_proxy_search`).
            used_projection = False
            used_grep = False
            self.metrics.record_call(
                original_size, new_size, used_projection, used_grep, auto_truncated
            )

            if original_size > 0:
                savings = ((original_size - new_size) / original_size) * 100
                logger.info(
                    "Token savings: %d -> %d tokens (%.1f%% reduction)",
                    original_size,
                    new_size,
                    savings,
                )

            # If we have exploration metadata, attach it as a lightweight JSON block
            if exploration_metadata and exploration_metadata.get("rlm_hints"):
                try:
                    meta_text = json.dumps(exploration_metadata, indent=2)
                    # Append as a separate content item to keep original response intact
                    content.append(
                        TextContent(
                            type="text",
                            text=f"\n\nRLM exploration metadata:\n{meta_text}",
                        )
                    )
                except Exception as exc:
                    logger.debug("Failed to attach RLM exploration metadata: %s", exc, exc_info=True)

            return content
    
    # ------------------------------------------------------------------
    # Proxy tool definitions
    # ------------------------------------------------------------------

    @staticmethod
    def _build_proxy_tools() -> List[Tool]:
        """Return the three first-class proxy tools with flat, simple schemas."""
        return [
            Tool(
                name="proxy_filter",
                description=(
                    "Filter/project specific fields from a cached or fresh tool result. "
                    "Use this when a previous tool response was truncated and you received a cache_id, "
                    "or supply tool+arguments to call and filter in one step.\n\n"
                    "Modes: include (whitelist fields), exclude (blacklist fields)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cache_id": {
                            "type": "string",
                            "description": "Cache ID from a previous truncated response. Use this OR tool+arguments.",
                        },
                        "tool": {
                            "type": "string",
                            "description": "Full tool name (e.g. filesystem_read_file) to call fresh. Use with 'arguments'.",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Arguments for the fresh tool call (only used with 'tool').",
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Field paths to include/exclude (e.g. ['name', 'users.email']).",
                        },
                        "exclude": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Field paths to exclude. If provided, mode is auto-set to 'exclude'.",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["include", "exclude"],
                            "description": "Projection mode. Defaults to 'include' if fields provided, 'exclude' if exclude provided.",
                        },
                    },
                },
            ),
            Tool(
                name="proxy_search",
                description=(
                    "Search/grep within a cached or fresh tool result. "
                    "Supports multiple search modes: regex (default), bm25, fuzzy, context.\n\n"
                    "Use when you need to find specific content within a large response."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cache_id": {
                            "type": "string",
                            "description": "Cache ID from a previous truncated response.",
                        },
                        "tool": {
                            "type": "string",
                            "description": "Full tool name to call fresh.",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Arguments for fresh tool call.",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Search pattern (regex for regex mode, query text for bm25/fuzzy).",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["regex", "bm25", "fuzzy", "context"],
                            "description": "Search mode. Defaults to 'regex'.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return.",
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "Number of context lines around each match (regex mode).",
                        },
                        "case_insensitive": {
                            "type": "boolean",
                            "description": "Case-insensitive matching (regex mode). Default false.",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "Similarity threshold 0-1 (fuzzy mode). Default 0.7.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of top chunks to return (bm25 mode). Default 5.",
                        },
                        "context_type": {
                            "type": "string",
                            "enum": ["paragraph", "section", "sentence", "lines"],
                            "description": "Context extraction unit (context mode). Default 'paragraph'.",
                        },
                    },
                    "required": ["pattern"],
                },
            ),
            Tool(
                name="proxy_explore",
                description=(
                    "Discover the structure of a cached or fresh tool result without loading "
                    "all data. Returns types, field names, sizes, and a small sample. "
                    "Use this first when you receive a large truncated response to understand "
                    "the shape of the data before filtering."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cache_id": {
                            "type": "string",
                            "description": "Cache ID from a previous truncated response.",
                        },
                        "tool": {
                            "type": "string",
                            "description": "Full tool name to call fresh.",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Arguments for fresh tool call.",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum depth to explore. Default 3.",
                        },
                    },
                },
            ),
        ]

    # ------------------------------------------------------------------
    # Proxy tool handlers
    # ------------------------------------------------------------------

    async def _resolve_content_source(
        self, arguments: Dict[str, Any]
    ) -> List[Content]:
        """Resolve content from cache_id or by calling a tool fresh."""
        cache_id = arguments.get("cache_id")
        tool = arguments.get("tool")
        agent_id = await self._get_agent_id()

        if cache_id:
            cached = await self.cache.get(cache_id)
            if cached is None:
                raise ValueError(
                    f"Cache entry '{cache_id}' not found or expired. "
                    "Re-call the original tool to get a new cache_id."
                )
            return cached

        if tool:
            tool_args = arguments.get("arguments", {})
            server_name, tool_name = self._resolve_tool_name(tool)
            session = self.underlying_servers[server_name]
            try:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, tool_args), timeout=60.0
                )
                content = list(result.content) if hasattr(result, "content") else []
                # Cache the fresh result for potential follow-up
                cid = await self.cache.put(content, tool, tool_args, agent_id=agent_id)
                logger.debug("Fresh call cached as %s", cid)
                return content
            except asyncio.TimeoutError:
                raise ValueError(f"Timeout calling tool {tool} (60s)")
            except Exception as exc:
                raise ValueError(f"Error calling tool {tool}: {exc}")

        raise ValueError(
            "Provide either 'cache_id' (from a previous truncated response) "
            "or 'tool' + 'arguments' to call a tool fresh."
        )

    async def _handle_proxy_filter(self, arguments: Dict[str, Any]) -> List[Content]:
        """Handle proxy_filter tool call."""
        content = await self._resolve_content_source(arguments)

        fields = arguments.get("fields")
        exclude = arguments.get("exclude")
        mode = arguments.get("mode")

        if exclude and not mode:
            mode = "exclude"
        elif not mode:
            mode = "include"

        projection_fields = exclude if mode == "exclude" else fields
        if not projection_fields:
            return [TextContent(type="text", text="Error: Provide 'fields' or 'exclude' to filter.")]

        spec = {"mode": mode, "fields": projection_fields}
        # Use async version
        result = await self.projection_processor.process_async(content, spec)

        self.metrics.record_call(
            result.original_size, result.filtered_size, used_projection=True
        )
        return result.content

    async def _handle_proxy_search(self, arguments: Dict[str, Any]) -> List[Content]:
        """Handle proxy_search tool call."""
        content = await self._resolve_content_source(arguments)

        pattern = arguments.get("pattern", "")
        if not pattern:
            return [TextContent(type="text", text="Error: 'pattern' is required for proxy_search.")]

        mode = arguments.get("mode", "regex")

        grep_spec: Dict[str, Any] = {"mode": mode, "pattern": pattern}

        # Map flat parameters → grep spec
        if arguments.get("max_results"):
            grep_spec["maxMatches"] = arguments["max_results"]
            grep_spec["topK"] = arguments["max_results"]
        if arguments.get("context_lines"):
            grep_spec["contextLines"] = {"both": arguments["context_lines"]}
        if arguments.get("case_insensitive"):
            grep_spec["caseInsensitive"] = True
        if arguments.get("threshold"):
            grep_spec["threshold"] = arguments["threshold"]
        if arguments.get("top_k"):
            grep_spec["topK"] = arguments["top_k"]
        if arguments.get("context_type"):
            grep_spec["contextType"] = arguments["context_type"]
        # For bm25, alias pattern as query
        if mode == "bm25":
            grep_spec["query"] = pattern

        # Use async version
        result = await self.grep_processor.process_async(content, grep_spec)
        self.metrics.record_call(
            result.original_size, result.filtered_size, used_grep=True
        )
        return result.content

    async def _handle_proxy_explore(self, arguments: Dict[str, Any]) -> List[Content]:
        """Handle proxy_explore tool call."""
        content = await self._resolve_content_source(arguments)
        max_depth = arguments.get("max_depth", 3)

        # First, use structure-mode grep to produce a human-readable summary
        grep_spec = {"mode": "structure", "maxDepth": max_depth}
        result = await self.grep_processor.process_async(content, grep_spec)

        # Then, attempt to derive RLM-style structure hints for follow-up calls
        exploration_hints: Optional[Dict[str, Any]] = None
        try:
            exploration_hints = self.recursive_context_manager.create_exploration_metadata(content)
        except Exception as exc:
            logger.debug("Failed to generate RLM hints for proxy_explore: %s", exc, exc_info=True)

        # Attach guidance as an additional content item if available
        if exploration_hints and exploration_hints.get("rlm_hints"):
            try:
                hints_text = json.dumps(exploration_hints, indent=2)
                guidance = TextContent(
                    type="text",
                    text=(
                        "\n\nRLM-guided next steps:\n"
                        "You can now use proxy_filter or proxy_search with the suggested projections/grep patterns.\n"
                        f"{hints_text}"
                    ),
                )
                result.content.append(guidance)
            except Exception as exc:
                logger.debug("Failed to attach RLM hints to proxy_explore: %s", exc, exc_info=True)

        return result.content

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_schema(input_schema: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
        """Return a clean dict copy of a tool schema (no mutations)."""
        if hasattr(input_schema, "model_dump"):
            return input_schema.model_dump()
        if hasattr(input_schema, "dict"):
            return input_schema.dict()
        if isinstance(input_schema, dict):
            return dict(input_schema)
        return dict(input_schema) if input_schema else {"type": "object", "properties": {}}

    # ------------------------------------------------------------------
    # Tool-name resolution
    # ------------------------------------------------------------------

    def _resolve_tool_name(self, name: str) -> tuple[str, str]:
        """Parse ``{server}_{tool}`` and validate against known servers."""
        if "_" not in name:
            raise ValueError(f"Tool name must be in format 'server_tool', got: {name}")

        # Try known server prefixes first
        for known_server in self.underlying_servers:
            if name.startswith(known_server + "_"):
                return known_server, name[len(known_server) + 1:]

        # Fallback: rsplit
        parts = name.rsplit("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Tool name must be in format 'server_tool', got: {name}")

        server_name, tool_name = parts
        if server_name not in self.underlying_servers:
            available = list(self.underlying_servers.keys())
            raise ValueError(
                f"Unknown server: '{server_name}'. Available: {', '.join(available) or 'none'}. "
                f"Tool name format: {{server_name}}_{{tool_name}}. "
                f"Call list_tools() to see all available tool names."
            )
        return server_name, tool_name

    # ------------------------------------------------------------------
    # Agent ID management
    # ------------------------------------------------------------------

    async def _get_agent_id(self) -> Optional[str]:
        """
        Get agent ID for current request context.
        
        Since MCP doesn't provide built-in agent identification, we use
        a session-based approach. In a real deployment, this could be
        enhanced to extract agent IDs from:
        - MCP request headers/metadata
        - Authentication tokens
        - Session identifiers
        - Custom context passed through the protocol
        
        Returns:
            Agent ID string or None if isolation disabled.
        """
        if not self.settings.enable_agent_isolation:
            return None
        
        # For now, use a simple session-based approach
        # In production, extract from actual request context
        try:
            # Try to get current task/context identifier
            # This is a simplified approach - in production you'd extract
            # from actual MCP request metadata
            current_task = asyncio.current_task()
            if current_task:
                task_name = current_task.get_name()
                # Use task name as session identifier
                session_id = task_name.split("-")[-1] if "-" in task_name else "default"
            else:
                session_id = "default"
            
            # Map session to agent ID
            async with self._agent_lock:
                if session_id not in self._session_to_agent:
                    self._agent_counter += 1
                    agent_id = f"agent_{self._agent_counter}"
                    self._session_to_agent[session_id] = agent_id
                    logger.debug("Assigned agent ID %s to session %s", agent_id, session_id)
                else:
                    agent_id = self._session_to_agent[session_id]
            
            return agent_id
        except Exception:
            # Fallback to default agent
            return "default"

    # ------------------------------------------------------------------
    # Truncation helper
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_content(content: List[Content], max_chars: int) -> str:
        """Concatenate TextContent items and truncate to *max_chars*."""
        parts: List[str] = []
        total = 0
        for item in content:
            if isinstance(item, TextContent):
                remaining = max_chars - total
                if remaining <= 0:
                    break
                text = item.text[:remaining]
                parts.append(text)
                total += len(text)
        return "".join(parts)

    # ------------------------------------------------------------------
    # Connection management (unchanged from original)
    # ------------------------------------------------------------------

    async def _connect_to_server_sync(
        self, server_name: str, server_params: StdioServerParameters
    ) -> None:
        """Connect to a server and keep connection alive via a background task."""
        logger.debug("_connect_to_server_sync called for %s", server_name)

        connection_event = asyncio.Event()
        connection_error: list[Optional[Exception]] = [None]

        async def _keep_connection() -> None:
            try:
                async with stdio_client(server_params) as (read_stream, write_stream):
                    session_obj = ClientSession(read_stream, write_stream)
                    session = await session_obj.__aenter__()
                    self._server_contexts[server_name] = session_obj

                    try:
                        try:
                            init_result = await asyncio.wait_for(session.initialize(), timeout=30.0)
                            logger.info("Connected to underlying server: %s", server_name)
                            if init_result.serverInfo:
                                logger.info(
                                    "     Server: %s, Version: %s",
                                    init_result.serverInfo.name,
                                    init_result.serverInfo.version,
                                )
                        except asyncio.TimeoutError:
                            logger.error("Timeout initializing %s (30s)", server_name)
                            connection_error[0] = Exception(f"Timeout connecting to {server_name}")
                            connection_event.set()
                            await session_obj.__aexit__(None, None, None)
                            return
                        except Exception as exc:
                            logger.error("Init exception for %s: %s", server_name, exc, exc_info=True)
                            connection_error[0] = exc
                            connection_event.set()
                            await session_obj.__aexit__(None, None, None)
                            return

                        self.underlying_servers[server_name] = session
                        self.metrics.connection_count += 1

                        # Pre-load tools
                        try:
                            tools_result = await asyncio.wait_for(session.list_tools(), timeout=10.0)
                            logger.info("     Loaded %d tools from %s", len(tools_result.tools), server_name)
                            self.tools_cache[server_name] = tools_result.tools
                            if tools_result.tools:
                                sample = [t.name for t in tools_result.tools[:5]]
                                logger.info(
                                    "     Sample tools: %s%s",
                                    sample,
                                    "..." if len(tools_result.tools) > 5 else "",
                                )
                        except Exception as exc:
                            logger.error("Could not list tools from %s: %s", server_name, exc, exc_info=True)

                        connection_event.set()

                        try:
                            await asyncio.Event().wait()
                        except asyncio.CancelledError:
                            logger.info("Connection to %s cancelled", server_name)
                            self.underlying_servers.pop(server_name, None)
                            ctx = self._server_contexts.pop(server_name, None)
                            if ctx:
                                try:
                                    await ctx.__aexit__(None, None, None)
                                except Exception:
                                    pass
                            raise
                    finally:
                        ctx = self._server_contexts.pop(server_name, None)
                        if ctx:
                            try:
                                await ctx.__aexit__(None, None, None)
                            except Exception:
                                pass

            except Exception as exc:
                logger.error("Connection task failed for %s: %s", server_name, exc, exc_info=True)
                connection_error[0] = exc
                connection_event.set()
                self.underlying_servers.pop(server_name, None)

        task = asyncio.create_task(_keep_connection())
        self._connection_tasks[server_name] = task

        try:
            await asyncio.wait_for(connection_event.wait(), timeout=35.0)
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for connection to %s", server_name)
            task.cancel()
            raise Exception(f"Timeout waiting for connection to {server_name}")

        if connection_error[0]:
            raise connection_error[0]

    async def initialize_underlying_servers(self) -> None:
        """Initialize connections to underlying MCP servers."""
        if not self.server_configs:
            logger.info("No underlying servers configured.")
            return

        logger.info("Initializing %d underlying server(s)...", len(self.server_configs))

        for config in self.server_configs:
            server_name = config["name"]
            command = config["command"]
            args = config.get("args", [])

            try:
                logger.info("Connecting to %s (command: %s, args: %s)", server_name, command, args)
                server_params = StdioServerParameters(command=command, args=args, env=None)
                await self._connect_to_server_sync(server_name, server_params)
            except Exception as exc:
                logger.error("Failed to connect to %s: %s", server_name, exc, exc_info=True)
                self.metrics.failed_connections += 1

    async def cleanup(self) -> None:
        """Clean up connections to underlying servers."""
        try:
            logger.info("Cleaning up connections...")
            self.metrics.log_summary()
            
            # Shutdown executor
            self.executor_manager.shutdown(wait=True)
            
            for server_name, session_obj in list(self._server_contexts.items()):
                try:
                    await session_obj.__aexit__(None, None, None)
                except Exception as exc:
                    logger.warning("Error closing %s: %s", server_name, exc)
            self._server_contexts.clear()

            for server_name, task in list(self._connection_tasks.items()):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._connection_tasks.clear()
            self.underlying_servers.clear()
            self.tools_cache.clear()
            await self.cache.clear()
        except Exception:
            pass

    async def run(self) -> None:
        """Run the proxy server."""
        try:
            # Set event loop for executor
            loop = asyncio.get_event_loop()
            self.executor_manager.set_event_loop(loop)
            
            await self.initialize_underlying_servers()

            capabilities = ServerCapabilities.model_validate({
                "tools": {},
            })

            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions.model_validate({
                        "server_name": "mcp-rlm-proxy",
                        "server_version": "0.1.0",
                        "capabilities": capabilities.model_dump(),
                    }),
                )
        finally:
            await self.cleanup()
