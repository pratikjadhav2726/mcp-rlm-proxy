# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

