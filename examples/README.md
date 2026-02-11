# MCP Proxy Examples

This directory contains usage examples for the MCP Proxy Server.

## Available Examples

### 1. `comprehensive_example.py` ⭐ (Recommended)

A complete demonstration of all proxy features including:
- Multi-server tool aggregation
- Field projection (include/exclude modes)
- Grep search with context lines
- Combined projection + grep
- Recursive exploration (RLM pattern)
- Token savings calculations

**Run it:**
```bash
cd examples
python comprehensive_example.py
```

This is the best starting point to understand all capabilities.

### 2. `example_usage.py`

Interactive examples showing:
- Field projection syntax
- Grep search patterns
- Combined transformations

**Run it:**
```bash
cd examples
python example_usage.py
```

**Note**: Requires configured servers in `config.yaml`

## Quick Examples

### Field Projection (via `proxy_filter`)

```python
# After a large response is truncated, you'll receive a cache_id like "agent_1:ABC123DEF456".
# Use proxy_filter with that cache_id to get only specific fields.

result = await session.call_tool("proxy_filter", {
    "cache_id": "agent_1:ABC123DEF456",
    "fields": ["users.name", "users.email"],
    "mode": "include"
})
```

### Grep Search (via `proxy_search`)

```python
# Search for errors in a cached log response
result = await session.call_tool("proxy_search", {
    "cache_id": "agent_1:ABC123DEF456",
    "pattern": "ERROR|FATAL",
    "mode": "regex",
    "case_insensitive": True,
    "context_lines": 2,
    "max_results": 50
})
```

### Combined Transformations (projection + search)

```python
# Step 1: Call underlying tool through the proxy (may be truncated + cached)
users = await session.call_tool("api_get_users", {"limit": 1000})
# Assume response was truncated and you received cache_id="agent_1:ABC123DEF456"

# Step 2: Project fields from the cached result
projected = await session.call_tool("proxy_filter", {
    "cache_id": "agent_1:ABC123DEF456",
    "fields": ["name", "email", "status"],
    "mode": "include"
})

# Step 3: Search within the (same) cached result
search_results = await session.call_tool("proxy_search", {
    "cache_id": "agent_1:ABC123DEF456",
    "pattern": "gmail\\.com",
    "mode": "regex"
})
```

## Using with Different Clients

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Then ask Claude to use the proxy tools `proxy_filter`, `proxy_search`, and `proxy_explore`
with the `cache_id` values returned from large tool responses.

### Custom Python Client

See `comprehensive_example.py` for complete client implementation.

### Node.js/TypeScript

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: "uv",
  args: ["run", "-m", "mcp_proxy"],
  cwd: "/path/to/mcp-rlm-proxy"
});

const client = new Client({
  name: "example-client",
  version: "1.0.0"
}, {
  capabilities: {}
});

await client.connect(transport);

// Use proxy tools
const result = await client.callTool({
  name: "proxy_filter",
  arguments: {
    cache_id: "agent_1:ABC123DEF456",
    fields: ["users.name"],
    mode: "include"
  }
});
```

## Real-World Use Cases

### Use Case 1: Log Analysis Agent

```python
# Agent needs to find authentication failures in logs
# 1) Call filesystem_read_file via proxy; assume it was truncated with cache_id="agent_1:LOGS123456".
# 2) Use proxy_search on the cached log content.
failures = await session.call_tool("proxy_search", {
    "cache_id": "agent_1:LOGS123456",
    "pattern": "authentication failure|Failed password",
    "mode": "regex",
    "case_insensitive": True,
    "context_lines": 2,
    "max_results": 100
})

# Result: Only relevant log lines (99.7% token savings)
```

### Use Case 2: API Integration

```python
# Agent needs user emails from large API response
# 1) Call api_list_users via proxy; assume response cached with cache_id="agent_1:USERS123456".
# 2) Use proxy_filter to get only IDs and emails.
users = await session.call_tool("proxy_filter", {
    "cache_id": "agent_1:USERS123456",
    "fields": ["users[].id", "users[].email"],
    "mode": "include"
})

# Result: Only IDs and emails (95% token savings)
```

### Use Case 3: Security/Privacy

```python
# Agent needs user data but must exclude sensitive fields
# 1) Call db_get_user via proxy; assume response cached with cache_id="agent_1:USER123456".
# 2) Use proxy_filter to exclude sensitive fields.
user = await session.call_tool("proxy_filter", {
    "cache_id": "agent_1:USER123456",
    "fields": ["password", "ssn", "credit_card", "api_key"],
    "mode": "exclude"
})

# Result: All data except sensitive fields
```

### Use Case 4: Recursive Exploration (RLM)

```python
# Step 1: Call api_get_data via proxy; assume response cached with cache_id="agent_1:DATA123456".
# Step 2: Use proxy_explore to discover structure.
structure = await session.call_tool("proxy_explore", {
    "cache_id": "agent_1:DATA123456",
    "max_depth": 3
})

# Step 3: Use proxy_filter to get an overview of key fields.
overview = await session.call_tool("proxy_filter", {
    "cache_id": "agent_1:DATA123456",
    "fields": ["id", "name"],
    "mode": "include"
})

# Step 4: Drill down into a specific nested field.
details = await session.call_tool("proxy_filter", {
    "cache_id": "agent_1:DATA123456",
    "fields": ["profile.bio"],
    "mode": "include"
})

# Total: ~98% token savings vs loading everything
```

## Tips

1. **Start Simple**: Begin with basic projection, then add grep as needed
2. **Monitor Savings**: Check proxy logs for token reduction metrics
3. **Design Flows**: Design reusable proxy_filter/proxy_search flows for common queries
4. **Iterate**: Use RLM pattern (proxy_explore → proxy_filter → proxy_search) to explore, then query
5. **Test Patterns**: Use `comprehensive_example.py` to test different proxy tool flows

## Troubleshooting

### "Server not found"

Ensure proxy is configured with servers in `config.yaml`:

```yaml
underlying_servers:
  - name: filesystem
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

### "Tool name not found"

Tools are prefixed with server names:
- `read_file` → `filesystem_read_file`
- `commit` → `git_commit`

List available tools:
```python
tools = await session.list_tools()
print([t.name for t in tools.tools])
```

### "_meta not working"

Ensure:
1. `_meta` is at same level as other arguments (not nested)
2. Tool is called through proxy (has server prefix)
3. JSON structure is valid

## More Resources

- [Quick Reference](../docs/QUICK_REFERENCE.md) - Complete syntax reference
- [Middleware Adoption](../docs/MIDDLEWARE_ADOPTION.md) - Integration guide
- [Migration Guide](../docs/MIGRATION_GUIDE.md) - Migrating from direct MCP
- [Architecture](../docs/ARCHITECTURE.md) - How it works internally

## Contributing Examples

Have a great use case? Contribute an example:

1. Create a new `.py` file in `examples/`
2. Add documentation at the top
3. Follow the pattern in `comprehensive_example.py`
4. Submit a PR

Examples especially welcome for:
- Industry-specific use cases
- Novel projection/grep patterns
- Integration with specific AI frameworks
- Performance optimization techniques
