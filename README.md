# MCP-RLM-Proxy: Intelligent Middleware for MCP Servers

> **Production-ready middleware** implementing Recursive Language Model principles ([arXiv:2512.24601](https://arxiv.org/abs/2512.24601)) for efficient multi-server management, automatic large-response handling, and first-class proxy tools for recursive data exploration. **100% compatible with the MCP specification** - works with any existing MCP server without modification.

## Quick Start for Current MCP Users

**Already using MCP servers?** Add this as middleware in 5 minutes:

```bash
# 1. Clone and install
git clone https://github.com/pratikjadhav2726/mcp-rlm-proxy.git && cd mcp-rlm-proxy && uv sync

# 2. Configure your existing servers
cat > mcp.json << EOF
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/your/path"]
    }
  }
}
EOF

# 3. Run the proxy
uv run -m mcp_proxy
```

**That's it!** Your servers now have automatic large-response handling and three powerful proxy tools for recursive exploration.

---

## Why Use This as Middleware?

### The Problem with Direct MCP Connections

When AI agents connect directly to MCP servers:
- **Token waste**: 85-95% of returned data is often unnecessary
- **Context pollution**: Irrelevant data dilutes important information
- **No multi-server aggregation**: Must connect to each server separately
- **Performance degradation**: Large responses slow everything down
- **Cost explosion**: Every unnecessary token costs money

### The Solution: Intelligent Middleware

```
+---------------+
|  MCP Client   |  (Claude Desktop, Cursor, Custom Client)
+-------+-------+
        | ONE connection
        v
+---------------+
| MCP-RLM       |  <-- THIS MIDDLEWARE
| Proxy         |  - Connects to N servers
|               |  - Auto-truncates large responses
|               |  - Caches + provides proxy_filter / proxy_search / proxy_explore
|               |  - Tracks token savings
+-------+-------+
        | Manages connections to your servers
    +---+----+--------+--------+
    v        v        v        v
+-----+  +-----+  +-----+  +-----+
| FS  |  | Git |  | API |  | DB  |  <-- Your existing servers
+-----+  +-----+  +-----+  +-----+      (NO changes needed!)
```

### Benefits

- **Zero Friction**: Works with existing MCP servers (no code changes)
- **Huge Token Savings**: 85-95% reduction typical
- **Multi-Server**: Aggregate tools from many servers through one interface
- **Clean Schemas**: No `_meta` injection; tool schemas are passed through unmodified
- **Agent-Friendly**: Three first-class proxy tools with flat, simple parameters
- **Auto-Truncation**: Large responses automatically truncated + cached for follow-up
- **Production Ready**: Connection pooling, error handling, metrics, TTL-based caching

---

## How It Works

### Architecture Overview

1. **Client connects to proxy** (instead of individual servers)
2. **Proxy connects to N servers** (configured in `mcp.json`)
3. **Tools are aggregated** with server prefixes (`filesystem_read_file`)
4. **Tool schemas pass through clean** - no modification, no `_meta` injection
5. **Large responses are auto-truncated** and cached with a `cache_id`
6. **Three proxy tools** let agents drill into cached data without re-executing

### The Proxy Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `proxy_filter` | Project/filter specific fields from cached or fresh result | `cache_id`, `fields`, `exclude`, `mode` |
| `proxy_search` | Grep/BM25/fuzzy/context search on cached or fresh result | `cache_id`, `pattern`, `mode`, `max_results` |
| `proxy_explore` | Discover data structure without loading content | `cache_id`, `max_depth` |

All parameters are **flat, top-level, simple types** - no nested objects required. Each tool can work in two modes:

- **Cached mode**: pass `cache_id` from a previous truncated response
- **Fresh mode**: pass `tool` + `arguments` to call and filter in one step

### Typical Agent Workflow

```
Step 1: Agent calls filesystem_read_file(path="large-data.json")
        -> Response is 50,000 chars -> auto-truncated + cached
        -> Agent receives first 8,000 chars + cache_id="a1b2c3d4e5f6"

Step 2: Agent calls proxy_explore(cache_id="a1b2c3d4e5f6")
        -> Returns structure summary: types, field names, sizes, sample
        -> 200 tokens instead of 50,000

Step 3: Agent calls proxy_filter(cache_id="a1b2c3d4e5f6", fields=["users.name", "users.email"])
        -> Returns only projected fields
        -> 500 tokens instead of 50,000

Step 4: Agent calls proxy_search(cache_id="a1b2c3d4e5f6", pattern="error", mode="bm25", top_k=3)
        -> Returns top-3 most relevant chunks
        -> 800 tokens instead of 50,000

Total: ~1,500 tokens vs 50,000+ (97% savings!)
```

---

## Token Savings Impact

### Real-World Token Reduction Examples

| Use Case | Without Proxy | With Proxy | Savings | Cost Impact* |
|----------|---------------|------------|---------|--------------|
| **User Profile API** | 2,500 tokens | 150 tokens | **94%** | $0.10 -> $0.006 |
| **Log File Search** (1MB) | 280,000 tokens | 800 tokens | **99.7%** | Rate limited -> $0.32 |
| **Database Query** (100 rows) | 15,000 tokens | 1,200 tokens | **92%** | $0.60 -> $0.048 |
| **File System Scan** | 8,000 tokens | 400 tokens | **95%** | $0.32 -> $0.016 |

\* Estimated using GPT-4 pricing ($0.03/1K input tokens)

### Compound Savings in Multi-Step Workflows

For a typical AI agent workflow with 10 tool calls:
- **Without proxy**: 10 calls x 10,000 tokens avg = **100,000 tokens** -> $3.00
- **With proxy**: 10 calls x 800 tokens avg = **8,000 tokens** -> $0.24
- **Total savings per workflow**: **$2.76 (92% reduction)**

---

## Proxy Tool Reference

### proxy_filter

Filter/project specific fields from a cached or fresh tool result.

```json
{
  "cache_id": "a1b2c3d4e5f6",
  "fields": ["name", "users.email"],
  "mode": "include"
}
```

Or with fresh call:

```json
{
  "tool": "filesystem_read_file",
  "arguments": {"path": "data.json"},
  "fields": ["users.name", "users.email"]
}
```

### proxy_search

Search within a cached or fresh result. Modes: `regex`, `bm25`, `fuzzy`, `context`.

```json
{
  "cache_id": "a1b2c3d4e5f6",
  "pattern": "ERROR|FATAL",
  "mode": "regex",
  "case_insensitive": true,
  "max_results": 20,
  "context_lines": 2
}
```

BM25 relevance search:

```json
{
  "cache_id": "a1b2c3d4e5f6",
  "pattern": "database connection timeout",
  "mode": "bm25",
  "top_k": 5
}
```

### proxy_explore

Discover the structure of data without loading it all.

```json
{
  "cache_id": "a1b2c3d4e5f6",
  "max_depth": 3
}
```

Returns: types, field names, sizes, and a small sample.

---

## Configuration

### mcp.json

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git", "/repo"]
    }
  },
  "proxySettings": {
    "maxResponseSize": 8000,
    "cacheMaxEntries": 50,
    "cacheTTLSeconds": 300,
    "enableAutoTruncation": true
  }
}
```

### Proxy Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `maxResponseSize` | 8000 | Character threshold for auto-truncation |
| `cacheMaxEntries` | 50 | Maximum cached responses |
| `cacheTTLSeconds` | 300 | Cache entry time-to-live (seconds) |
| `enableAutoTruncation` | true | Enable/disable auto-truncation + caching |

---

## Installation

```bash
# Using uv (recommended)
git clone https://github.com/pratikjadhav2726/mcp-rlm-proxy.git
cd mcp-rlm-proxy
uv sync

# Using pip
pip install -e .
```

### Running the Proxy

```bash
uv run -m mcp_proxy
```

### Using with Claude Desktop

Edit your Claude Desktop config:

```json
{
  "mcpServers": {
    "proxy": {
      "command": "uv",
      "args": ["run", "-m", "mcp_proxy"],
      "cwd": "/path/to/mcp-rlm-proxy"
    }
  }
}
```

### Using Programmatically

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="uv",
    args=["run", "-m", "mcp_proxy"],
    cwd="/path/to/mcp-rlm-proxy"
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # List tools (prefixed with server names + 3 proxy tools)
        tools = await session.list_tools()

        # Call a tool - if response is large, it's auto-truncated with cache_id
        result = await session.call_tool("filesystem_read_file", {
            "path": "large-data.json"
        })

        # Drill into the cached data
        filtered = await session.call_tool("proxy_filter", {
            "cache_id": "a1b2c3d4e5f6",
            "fields": ["users.name", "users.email"]
        })
```

---

## Legacy _meta Support

For backward compatibility, the `_meta` parameter is still accepted in tool arguments but is no longer advertised in schemas. If you pass `_meta.projection` or `_meta.grep`, the proxy will apply them. However, the recommended approach is to use the proxy tools instead:

| Old way (_meta) | New way (proxy tools) |
|-----------------|----------------------|
| Hidden in nested `_meta.projection` | `proxy_filter(fields=["name"])` |
| Hidden in nested `_meta.grep` | `proxy_search(pattern="ERROR")` |
| Not discoverable by agents | First-class tools visible in `list_tools()` |

---

## Search Modes

| Mode | Use When | Token Savings |
|------|----------|---------------|
| `structure` (proxy_explore) | Don't know data format | 99.9%+ |
| `bm25` | Know what, not where | 99%+ |
| `fuzzy` | Handle typos/variations | 98%+ |
| `context` | Need full paragraphs | 95%+ |
| `regex` | Know exact pattern | 95%+ |

---

## Performance Monitoring

Automatic tracking of token savings and performance:

```
INFO: Token savings: 50,000 -> 500 tokens (99.0% reduction)

=== Proxy Performance Summary ===
  Total calls: 127
  Projection calls: 45
  Grep calls: 23
  Auto-truncated: 15
  Original tokens: 2,450,000
  Filtered tokens: 125,000
  Tokens saved: 2,325,000
  Savings: 94.9%
  Active connections: 3
```

---

## Comparison with RLM Paper Concepts

| RLM Paper Concept | MCP-RLM-Proxy Implementation |
|-------------------|------------------------------|
| **External Environment** | Tool outputs treated as inspectable data stores |
| **Recursive Decomposition** | proxy_explore -> proxy_filter -> proxy_search workflow |
| **Programmatic Exploration** | proxy_search with multiple modes |
| **Snippet Processing** | Auto-truncation + cached follow-up |
| **Cost Efficiency** | 85-95% token reduction vs. full context loading |
| **Long Context Handling** | Processes multi-MB tool outputs without context limits |

---

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** - System design and data flow
- **[Configuration](docs/CONFIGURATION.md)** - Configuration options and validation
- **[Performance](docs/PERFORMANCE.md)** - Performance benchmarks and optimization

---

## Related Concepts

- **Recursive Language Models Paper**: [arXiv:2512.24601](https://arxiv.org/abs/2512.24601)
- **Model Context Protocol**: [MCP Specification](https://github.com/modelcontextprotocol)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT License - see [LICENSE](LICENSE)

---

**Built for the AI agent community**
