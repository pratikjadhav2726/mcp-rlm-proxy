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

### Field Projection

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
        
        # Get only specific fields
        result = await session.call_tool("filesystem_read_file", {
            "path": "data.json",
            "_meta": {
                "projection": {
                    "mode": "include",
                    "fields": ["users.name", "users.email"]
                }
            }
        })
```

### Grep Search

```python
# Search for errors in logs
result = await session.call_tool("filesystem_read_file", {
    "path": "app.log",
    "_meta": {
        "grep": {
            "pattern": "ERROR|FATAL",
            "caseInsensitive": True,
            "maxMatches": 50,
            "contextLines": {"both": 2}
        }
    }
})
```

### Combined Transformations

```python
# Filter fields, then search within them
result = await session.call_tool("api_get_users", {
    "_meta": {
        "projection": {
            "mode": "include",
            "fields": ["name", "email", "status"]
        },
        "grep": {
            "pattern": "gmail\\.com",
            "target": "structuredContent"
        }
    }
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

Then ask Claude to use the tools with `_meta` parameters.

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

// Use tools with _meta
const result = await client.callTool({
  name: "filesystem_read_file",
  arguments: {
    path: "data.json",
    _meta: {
      projection: {
        mode: "include",
        fields: ["users.name"]
      }
    }
  }
});
```

## Real-World Use Cases

### Use Case 1: Log Analysis Agent

```python
# Agent needs to find authentication failures in logs
failures = await session.call_tool("filesystem_read_file", {
    "path": "/var/log/auth.log",
    "_meta": {
        "grep": {
            "pattern": "authentication failure|Failed password",
            "caseInsensitive": True,
            "contextLines": {"before": 1, "after": 2},
            "maxMatches": 100
        }
    }
})

# Result: Only relevant log lines (99.7% token savings)
```

### Use Case 2: API Integration

```python
# Agent needs user emails from large API response
users = await session.call_tool("api_list_users", {
    "limit": 1000,
    "_meta": {
        "projection": {
            "mode": "include",
            "fields": ["users[].id", "users[].email"]
        }
    }
})

# Result: Only IDs and emails (95% token savings)
```

### Use Case 3: Security/Privacy

```python
# Agent needs user data but must exclude sensitive fields
user = await session.call_tool("db_get_user", {
    "userId": "123",
    "_meta": {
        "projection": {
            "mode": "exclude",
            "fields": ["password", "ssn", "credit_card", "api_key"]
        }
    }
})

# Result: All data except sensitive fields
```

### Use Case 4: Recursive Exploration (RLM)

```python
# Step 1: Discover structure
fields = await session.call_tool("api_get_data", {
    "_meta": {"projection": {"mode": "include", "fields": ["_keys"]}}
})
# Returns: ["id", "name", "profile", ...]

# Step 2: Get overview
overview = await session.call_tool("api_get_data", {
    "_meta": {"projection": {"mode": "include", "fields": ["id", "name"]}}
})
# Returns: Minimal data

# Step 3: Drill down
details = await session.call_tool("api_get_data", {
    "_meta": {"projection": {"mode": "include", "fields": ["profile.bio"]}}
})
# Returns: Specific nested field

# Total: 98% token savings vs loading everything
```

## Tips

1. **Start Simple**: Begin with basic projection, then add grep as needed
2. **Monitor Savings**: Check proxy logs for token reduction metrics
3. **Create Templates**: Design reusable `_meta` patterns for common queries
4. **Iterate**: Use RLM pattern to explore data structure first, then query specifics
5. **Test Patterns**: Use `comprehensive_example.py` to test different approaches

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
