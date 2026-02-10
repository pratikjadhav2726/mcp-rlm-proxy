# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed - Architecture Refactor: First-Class Proxy Tools (2026-02-10)

#### Breaking Change: `_meta` Parameter Removed from Tool Schemas
- **BREAKING**: Tool schemas are no longer modified with the `_meta` parameter injection
- **Removed** `_enhance_tool_schema()` — underlying tool schemas now pass through **unmodified**
- **Rationale**: LLM agents were unable to reliably discover or use the deeply nested `_meta` parameter due to non-standard placement, schema bloat, and the `additionalProperties: true` hack

#### Added: First-Class Proxy Tools
Three new standard MCP tools replace the `_meta` approach — agents discover them naturally via `list_tools()`:
- **`proxy_filter`** — Field projection (include/exclude) on cached or fresh tool results
- **`proxy_search`** — Pattern search (regex, BM25, fuzzy, context) on cached or fresh results
- **`proxy_explore`** — Structure discovery (types, field names, sizes, samples) without loading full content
- All parameters are **flat, top-level, simple types** — no nested objects required

#### Added: SmartCacheManager (`cache.py`)
- New caching layer for tool outputs — avoids re-executing underlying tools for filtered follow-ups
- TTL-based expiration (configurable, default 300s)
- LRU eviction when capacity limit is reached
- UUID-based cache keys for uniqueness
- Hit/miss statistics for monitoring

#### Added: Automatic Large-Response Truncation
- Responses exceeding `max_response_tokens` are automatically truncated
- Full original response is cached with a `cache_id` appended to the truncated output
- Agents can use `proxy_filter`, `proxy_search`, or `proxy_explore` with the `cache_id` to drill into the data

#### Added: BaseProcessor & ProcessorPipeline
- **`BaseProcessor`** (ABC) — standardized `process(content, params) -> ProcessorResult` interface
- **`ProcessorResult`** dataclass — content, metadata, original/processed sizes, applied flag, error field
- **`ProcessorPipeline`** — composes a sequence of processors, runs them in order, accumulates metadata and size tracking
- All existing processors refactored to inherit from `BaseProcessor`

#### Refactored: Processor Hierarchy
- `ProjectionProcessor` now inherits `BaseProcessor` and returns `ProcessorResult`
- `GrepProcessor` refactored from static methods to instance methods; uses strategy pattern to delegate to BM25, fuzzy, context, and structure search modes
- `BM25Processor`, `FuzzyMatcher`, `ContextExtractor`, `StructureNavigator` (in `advanced_search.py`) all inherit `BaseProcessor`

#### Added: ProxySettings Configuration
- New `proxySettings` section in `mcp.json` with Pydantic validation:
  - `maxResponseSize` — character threshold for auto-truncation (default 8000)
  - `cacheMaxEntries` — maximum cached responses (default 50)
  - `cacheTTLSeconds` — cache entry TTL (default 300s)
  - `enableAutoTruncation` — toggle auto-truncation (default true)

#### Updated: Tests
- 64 tests passing across all modules
- New test suites: `test_cache.py`, `test_config.py`
- Updated `test_processors.py` for `ProcessorResult` interface and `ProcessorPipeline`
- Updated `test_schema_enhancement.py` to verify schemas are **not** modified
- Updated `test_proxy.py` to verify proxy tools are registered

#### Updated: Documentation
- `README.md` rewritten with proxy tool reference, agent workflow examples, token savings tables
- `ARCHITECTURE.md` rewritten with data flow diagrams, cache architecture, pipeline visualization

#### Legacy `_meta` Compatibility
- The `_meta` parameter is still **accepted** in tool arguments for backward compatibility
- It is no longer **advertised** in tool schemas
- Recommended migration: use `proxy_filter` / `proxy_search` / `proxy_explore` instead

---

### Changed - Configuration Format (2026-02-05)

#### Breaking Change: mcp.json Format
- **BREAKING**: Switched from `config.yaml` to `mcp.json` for configuration
- **New format matches Claude Desktop**: Uses identical `mcpServers` format as Claude Desktop and other MCP clients
- **Migration**: Copy server configurations from Claude Desktop config directly to proxy config
- **Removed dependency**: No longer requires `pyyaml` package
- **Simpler**: JSON format is more familiar to most developers and matches MCP ecosystem standard

#### Migration Path
**Old format** (`config.yaml`):
```yaml
underlying_servers:
  - name: filesystem
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

**New format** (`mcp.json`):
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  }
}
```

### Added - RLM & Middleware Enhancements (2026-02-05)

#### Core Features
- **RLM-inspired recursive context management** - Implements principles from "Recursive Language Models" paper (arXiv:2512.24601)
- **Advanced RLM processor module** (`rlm_processor.py`) with:
  - `RecursiveContextManager` - Analyzes when to decompose large outputs
  - `ChunkProcessor` - Splits large outputs into manageable chunks
  - `FieldDiscoveryHelper` - Discovers available fields for recursive exploration
  - `SmartCacheManager` - Caches tool outputs for efficient re-querying
- **Performance monitoring and telemetry** - Automatic token savings tracking with detailed metrics
- **Connection pool metrics** - Track active connections, failed connections, and connection health
- **Enhanced grep capabilities** - Context lines, multiline patterns, case-insensitive search

#### Documentation
- **Middleware Adoption Guide** (`docs/MIDDLEWARE_ADOPTION.md`) - Complete guide for current MCP users
- **Migration Guide** (`docs/MIGRATION_GUIDE.md`) - Step-by-step migration instructions (5-15 min)
- **Quick Reference Guide** (`docs/QUICK_REFERENCE.md`) - Complete syntax and command reference
- **Summary & Comparison** (`docs/SUMMARY.md`) - Feature comparison and use case matrix
- **Comprehensive example** (`examples/comprehensive_example.py`) - Demonstrates all features with token calculations

#### Infrastructure
- **ConnectionPoolMetrics class** - Tracks call counts, token savings, projection/grep usage
- **Automatic metrics logging** - Summary statistics logged on proxy shutdown
- **Per-call token tracking** - Individual call savings logged at INFO level
- **Multi-server efficiency** - Already had parallel tool discovery (2-3x speedup)

### Enhanced
- **README.md** - Complete rewrite highlighting middleware capabilities and adoption path
- **Examples README** - Expanded with real-world use cases and troubleshooting
- **Tool schema enhancement** - Better `_meta` parameter documentation in schemas
- **Error handling** - More descriptive error messages for misconfigured tools

### Previous Features (Retained)
- Initial open source release
- Field projection capabilities (include/exclude/view modes)
- Grep search functionality for filtering tool outputs
- **Context lines support for grep** - Include lines before/after matches (similar to grep -A, -B, -C)
- **Multiline pattern support for grep** - Enable patterns that span multiple lines
- Support for multiple underlying MCP servers
- Token savings tracking and reporting
- Configuration via YAML file
- Comprehensive documentation
- **Structured logging system** - Replaced print statements with proper logging infrastructure
- **Parallel tool discovery** - Tools are fetched from multiple servers concurrently for 2-3x performance improvement
- **Logging configuration** - Configurable log levels via `LOG_LEVEL` environment variable
- **Performance documentation** - Detailed performance characteristics and optimization guide
- **Pydantic configuration validation** - Robust configuration validation with helpful error messages
- **Configuration documentation** - Complete guide to configuration files and validation rules

## [0.1.0] - 2024-XX-XX

### Added
- Initial release
- MCP Proxy Server implementation
- Field projection processor
- Grep processor
- Server connection management
- Tool aggregation from multiple servers
- Configuration loading from YAML

[Unreleased]: https://github.com/yourusername/mcp-proxy-server/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/mcp-proxy-server/releases/tag/v0.1.0

