# Architecture

## Overview

The MCP-RLM-Proxy acts as an intelligent middleware between MCP clients and underlying MCP tool servers. It implements Recursive Language Model (RLM) principles for efficient context management: automatic large-response handling, first-class proxy tools for recursive data exploration, smart caching, and a composable processor pipeline — all while maintaining full compatibility with the MCP specification.

## High-Level Architecture

```
+-------------------+
|    MCP Client     |  (Claude Desktop, Cursor, Custom Client)
+--------+----------+
         | Single MCP connection (stdio)
         v
+-------------------+
| MCPProxyServer    |
|                   |
|  +--------------+ |
|  | Proxy Tools  | |   proxy_filter, proxy_search, proxy_explore
|  +--------------+ |
|  +--------------+ |
|  | Cache Layer  | |   SmartCacheManager / AgentAwareCacheManager
|  +--------------+ |
|  +--------------+ |
|  | Processor    | |   ProcessorPipeline -> ProjectionProcessor
|  | Pipeline     | |                    -> GrepProcessor
|  +--------------+ |                    -> BM25/Fuzzy/Context/Structure
|  +--------------+ |
|  | Auto-        | |   Truncation + cache for large responses
|  | Truncation   | |
|  +--------------+ |
+--------+----------+
         | Manages N connections
    +----+----+--------+--------+
    v         v        v        v
+-------+  +-----+  +-----+  +-----+
| FS    |  | Git |  | API |  | DB  |   Underlying MCP Servers
+-------+  +-----+  +-----+  +-----+   (NO changes needed)
```

## Components

### Core Modules

#### `mcp_proxy.server`

Contains the main `MCPProxyServer` class that:
- Manages connections to underlying MCP servers via persistent async tasks
- Aggregates tools from multiple servers with `{server}_{tool}` prefixes
- Registers three first-class **proxy tools** (`proxy_filter`, `proxy_search`, `proxy_explore`)
- Passes underlying tool schemas through **unmodified** (no `_meta` injection)
- Automatically truncates large responses and caches originals for follow-up
- Tracks token savings metrics

#### `mcp_proxy.processors`

Contains the transformation processor hierarchy:

- **`BaseProcessor`** (ABC): Abstract interface — `process(content, params) -> ProcessorResult`
- **`ProcessorResult`**: Standardized dataclass for processor outputs (content, metadata, sizes, applied flag, errors)
- **`ProjectionProcessor`**: Applies field projection (include/exclude modes) on JSON content
- **`GrepProcessor`**: Regex-based filtering with context lines, multiline support; delegates to advanced search modes (BM25, fuzzy, context, structure)
- **`ProcessorPipeline`**: Composes a sequence of `BaseProcessor` instances and runs them in order, accumulating metadata and tracking original→processed size

#### `mcp_proxy.advanced_search`

Advanced search strategies, all inheriting from `BaseProcessor`:

- **`BM25Processor`**: Term-frequency / inverse-document-frequency relevance ranking
- **`FuzzyMatcher`**: Levenshtein-distance fuzzy matching for typo-tolerant search
- **`ContextExtractor`**: Extracts surrounding context (paragraphs/sentences) around matches
- **`StructureNavigator`**: Discovers and summarizes data structure (types, field names, sizes, samples)

#### `mcp_proxy.cache`

Contains the cache implementations:
- **`SmartCacheManager`**: Simple TTL‑based, size‑aware cache used for legacy/global mode
  - TTL-based expiration (configurable, default 300s)
  - LRU‑style eviction when capacity is reached
  - UUID‑based cache keys for uniqueness
  - Thread-safe for concurrent async operations
- **`AgentAwareCacheManager`**: Agent‑isolated cache used by default
  - Per‑agent limits on entries and memory
  - Automatic eviction of least‑recently‑used / largest idle entries
  - Bounded number of concurrent agents
  - Backed by the same `CacheEntry` model as `SmartCacheManager`

#### `mcp_proxy.config`

Configuration loading and validation:
- **`ServerConfig`**: Per-server command, args, env, timeout
- **`ProxySettings`**: Proxy-specific settings (cache size, TTL, max response tokens, truncation message)
- **`ProxyConfig`**: Top-level config aggregating servers + proxy settings
- Loads from `mcp.json` with Pydantic validation

#### `mcp_proxy.logging_config`

Structured logging infrastructure with configurable log levels.

## Data Flow

### Standard Tool Call

```
MCP Client
    │
    │  call_tool("filesystem_read_file", {path: "data.json"})
    ▼
MCPProxyServer.call_tool()
    │
    │  1. Parse tool name → server="filesystem", tool="read_file"
    │  2. Forward call to underlying server (no arg modification)
    ▼
Underlying MCP Server
    │
    │  Response (e.g. 50,000 chars)
    ▼
MCPProxyServer (post-processing)
    │
    │  3. Check response size vs max_response_tokens
    │  4. If large: cache full response, truncate, append cache_id
    │  5. Return to client
    ▼
MCP Client
    (receives truncated response + cache_id for follow-up)
```

### Proxy Tool Call (Cached Follow-Up)

```
MCP Client
    │
    │  call_tool("proxy_filter", {cache_id: "abc123", fields: ["name", "email"]})
    ▼
MCPProxyServer.call_tool()
    │
    │  1. Recognize "proxy_filter" as a proxy tool
    │  2. Retrieve cached content from SmartCacheManager
    │  3. Build ProcessorPipeline with ProjectionProcessor
    │  4. Execute pipeline: project fields ["name", "email"]
    ▼
ProcessorPipeline
    │
    │  ProjectionProcessor.process(content, {fields, mode})
    │  → ProcessorResult(content, metadata, sizes)
    ▼
MCPProxyServer
    │
    │  5. Return filtered content + savings metadata
    ▼
MCP Client
    (receives only projected fields — 95%+ token savings)
```

### Proxy Tool Call (Fresh Execution)

```
MCP Client
    │
    │  call_tool("proxy_search", {tool: "api_query", arguments: {q: "users"},
    │                             pattern: "admin", mode: "bm25", top_k: 5})
    ▼
MCPProxyServer.call_tool()
    │
    │  1. Recognize "proxy_search" as a proxy tool with a fresh tool call
    │  2. Execute underlying tool "api_query" with {q: "users"}
    │  3. Cache the full response
    │  4. Build ProcessorPipeline with GrepProcessor (BM25 mode)
    │  5. Execute pipeline
    ▼
GrepProcessor → BM25Processor.process(content, params)
    │
    │  → Top-5 BM25-ranked results
    ▼
MCPProxyServer
    │
    │  Return filtered results + cache_id for further exploration
    ▼
MCP Client
```

## Proxy Tools

Three first-class MCP tools registered by the proxy:

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **`proxy_filter`** | Field projection (include/exclude) | You know which fields you need |
| **`proxy_search`** | Pattern search (regex, BM25, fuzzy, context) | You need to find specific content |
| **`proxy_explore`** | Structure discovery (types, fields, sizes) | You don't know the data shape yet |

### Why First-Class Tools Instead of `_meta`?

The original approach injected a `_meta` parameter into every tool's schema. This failed because:

1. **Agent Discovery**: LLMs don't reliably use deeply nested custom parameters
2. **Schema Bloat**: Every tool schema grew significantly, wasting tokens
3. **Non-Standard**: `_meta` is not part of the MCP specification
4. **`additionalProperties` Hack**: Required setting `additionalProperties: true` which breaks strict validation

The new approach uses standard MCP tools with flat, simple parameters that agents discover naturally via `list_tools()`.

## Connection Management

The proxy maintains persistent connections to underlying servers using:
- Background async tasks to keep connections alive
- Context managers for proper resource cleanup
- Connection pooling and caching
- Graceful reconnection on failure

## Tool Aggregation

Tools from multiple servers are aggregated with naming convention:
- Format: `{server_name}_{tool_name}`
- Prevents naming conflicts
- Maintains server identity

**Parallel Discovery**: Tool listing from multiple servers is performed in parallel using `asyncio.gather()`, providing significant performance improvements when multiple servers need tool discovery.

**Caching**: Tool definitions are cached after first discovery to avoid repeated queries.

## Processor Pipeline

The `ProcessorPipeline` composes multiple `BaseProcessor` instances:

```
Input Content
    │
    ▼
┌─────────────────────┐
│ ProjectionProcessor  │  fields=["name","email"], mode="include"
│ → ProcessorResult    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ GrepProcessor        │  pattern="admin", mode="bm25", top_k=5
│ → ProcessorResult    │
└─────────┬───────────┘
          │
          ▼
Final ProcessorResult
  .content     → filtered content
  .metadata    → {projection: {...}, grep: {...}}
  .original_size → bytes before
  .processed_size → bytes after
  .applied     → True
```

Each processor:
- Receives content + params
- Returns a `ProcessorResult` with standardized fields
- Is skipped if its params are not present in the pipeline config
- Can report errors without crashing the pipeline

## Cache Architecture

```
SmartCacheManager (async)
├── Storage: Dict[str, CacheEntry]
│                    │
│                content (List[Content])
│                tool_name, arguments
│                created_at, last_accessed_at
│                access_count, size_bytes
├── TTL: Configurable per-entry, default 300s (ttl_seconds)
├── Eviction: size-aware LRU (evicts entries with largest idle_seconds × size_bytes)
├── Keys: UUID-based short IDs (first 12 chars of UUID4)
├── API: Async put/get/get_entry/remove/clear/size/stats
└── AgentAwareCacheManager: per-agent isolation and quotas built on SmartCacheManager
```

## Error Handling

- Graceful degradation if underlying server fails
- Validation of transformation parameters via Pydantic
- Clear error messages with context
- Timeout handling for long-running operations
- Processors return errors in `ProcessorResult.error` without crashing

## Performance Considerations

- **Async/await**: All operations are asynchronous for non-blocking I/O
- **Parallel Tool Discovery**: Tools are fetched from multiple servers concurrently
- **Connection Pooling**: Persistent connections reduce overhead
- **Tool Caching**: Definitions cached to avoid repeated queries
- **Response Caching**: Full responses cached for follow-up proxy tool calls
- **Minimal Overhead**: Projection and grep typically add <10ms latency
- **Auto-Truncation**: Prevents token explosion for large responses
- **Structured Logging**: Configurable levels allow performance tuning

See [PERFORMANCE.md](PERFORMANCE.md) for detailed performance documentation.
