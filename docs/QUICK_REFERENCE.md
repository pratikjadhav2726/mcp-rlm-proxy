# Quick Reference Guide

## Command Reference

### Starting the Proxy

```bash
# Basic start
uv run -m mcp_proxy

# With custom config
CONFIG_FILE=custom.yaml uv run -m mcp_proxy

# With debug logging
LOG_LEVEL=DEBUG uv run -m mcp_proxy

# As installed package
mcp-proxy
```

### Configuration File

```json
{
  "mcpServers": {
    "server_id": {               // Required: unique server identifier
      "command": "executable",   // Required: npx, python, node, uv, etc.
      "args": ["arg1", "arg2"],  // Optional: list of arguments
      "env": {                    // Optional: environment variables
        "KEY": "value"
      }
    }
  }
}
```

## Tool Call Reference

### Basic Tool Call (No Filtering)

```python
result = await session.call_tool("filesystem_read_file", {
    "path": "/data/file.json"
})
```

### With Field Projection

#### Include Mode (Whitelist)

```python
result = await session.call_tool("filesystem_read_file", {
    "path": "/data/users.json",
    "_meta": {
        "projection": {
            "mode": "include",
            "fields": ["id", "name", "email"]
        }
    }
})
```

#### Nested Fields

```python
fields = [
    "user.profile.name",      # Nested object
    "orders[].id",            # Array elements
    "settings.notifications.email"  # Deep nesting
]
```

#### Exclude Mode (Blacklist)

```python
result = await session.call_tool("api_get_user", {
    "userId": "123",
    "_meta": {
        "projection": {
            "mode": "exclude",
            "fields": ["password", "ssn", "internal_id"]
        }
    }
})
```

### With Grep Search

#### Basic Pattern

```python
result = await session.call_tool("filesystem_read_file", {
    "path": "/logs/app.log",
    "_meta": {
        "grep": {
            "pattern": "ERROR"
        }
    }
})
```

#### Case Insensitive

```python
{
    "grep": {
        "pattern": "error|warn|fatal",
        "caseInsensitive": True
    }
}
```

#### With Context Lines

```python
{
    "grep": {
        "pattern": "Exception",
        "contextLines": {
            "before": 3,    # 3 lines before match
            "after": 5,     # 5 lines after match
            "both": 2       # Or 2 lines both (overrides before/after)
        }
    }
}
```

#### Limit Matches

```python
{
    "grep": {
        "pattern": "TODO",
        "maxMatches": 20    # Return max 20 matches
    }
}
```

#### Multiline Patterns

```python
{
    "grep": {
        "pattern": "function.*{\\n.*return",
        "multiline": True
    }
}
```

#### Search in Structured Content

```python
{
    "grep": {
        "pattern": "gmail\\.com",
        "target": "structuredContent"  # Search in JSON fields/values
    }
}
```

### Combined: Projection + Grep

```python
result = await session.call_tool("api_search_users", {
    "query": "*",
    "_meta": {
        "projection": {
            "mode": "include",
            "fields": ["name", "email", "status"]
        },
        "grep": {
            "pattern": "active",
            "target": "structuredContent"
        }
    }
})
```

**Processing order**: 
1. Tool executes and returns full response
2. Projection filters fields
3. Grep searches in filtered content
4. Minimal result returned to agent

## Common Patterns

### Discover Structure First (RLM Pattern)

```python
# Step 1: Get available fields
structure = await session.call_tool("api_get_data", {
    "_meta": {
        "projection": {
            "mode": "include",
            "fields": ["_keys"]  # Special: returns field names
        }
    }
})

# Step 2: Request only needed fields
data = await session.call_tool("api_get_data", {
    "_meta": {
        "projection": {
            "mode": "include",
            "fields": ["id", "name", "email"]  # Based on discovery
        }
    }
})
```

### Log File Analysis

```python
# Find errors with context
errors = await session.call_tool("filesystem_read_file", {
    "path": "/var/log/app.log",
    "_meta": {
        "grep": {
            "pattern": "ERROR|FATAL",
            "caseInsensitive": True,
            "contextLines": {"both": 3},
            "maxMatches": 50
        }
    }
})
```

### API Response Filtering

```python
# Get only specific fields from large API response
users = await session.call_tool("api_list_users", {
    "limit": 1000,
    "_meta": {
        "projection": {
            "mode": "include",
            "fields": ["users[].id", "users[].email", "users[].status"]
        }
    }
})
```

### Security: Remove Sensitive Fields

```python
# Exclude sensitive data automatically
user = await session.call_tool("db_get_user", {
    "userId": "123",
    "_meta": {
        "projection": {
            "mode": "exclude",
            "fields": [
                "password",
                "password_hash",
                "ssn",
                "credit_card",
                "api_key",
                "internal_notes"
            ]
        }
    }
})
```

## Tool Name Mapping

Tools from underlying servers are prefixed with server names:

| Server Name | Original Tool | Proxied Tool Name |
|-------------|---------------|-------------------|
| `filesystem` | `read_file` | `filesystem_read_file` |
| `filesystem` | `write_file` | `filesystem_write_file` |
| `git` | `commit` | `git_commit` |
| `git` | `log` | `git_log` |
| `api_server` | `search` | `api_server_search` |

## Client Configuration Examples

### Claude Desktop (macOS)

```json
{
  "mcpServers": {
    "proxy": {
      "command": "uv",
      "args": ["run", "-m", "mcp_proxy"],
      "cwd": "/Users/me/mcp-rlm-proxy"
    }
  }
}
```

**File location**: `~/Library/Application Support/Claude/claude_desktop_config.json`

### Claude Desktop (Windows)

```json
{
  "mcpServers": {
    "proxy": {
      "command": "uv",
      "args": ["run", "-m", "mcp_proxy"],
      "cwd": "C:\\Users\\Me\\mcp-rlm-proxy"
    }
  }
}
```

**File location**: `%APPDATA%\Claude\claude_desktop_config.json`

### Python Client

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
        # Use session...
```

### Node.js/TypeScript Client

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: "uv",
  args: ["run", "-m", "mcp_proxy"],
  cwd: "/path/to/mcp-rlm-proxy"
});

const client = new Client({
  name: "my-client",
  version: "1.0.0"
}, {
  capabilities: {}
});

await client.connect(transport);
```

## Troubleshooting Quick Fixes

### "Config file not found"
```bash
# Create mcp.json in proxy directory
cd /path/to/mcp-rlm-proxy
cp mcp.json.example mcp.json
# Edit mcp.json with your servers
```

### "Failed to connect to server X"
```bash
# Test server independently
npx -y @modelcontextprotocol/server-filesystem /tmp

# Check logs
LOG_LEVEL=DEBUG uv run -m mcp_proxy
```

### "Tool not found: read_file"
```python
# Tools are prefixed now
# Wrong: "read_file"
# Correct: "filesystem_read_file"

tools = await session.list_tools()
print([t.name for t in tools.tools])  # See all available tools
```

### "_meta is ignored"
```python
# Ensure _meta is at same level as other arguments
# ✗ Wrong:
{
    "path": "file.txt",
    "options": {
        "_meta": {"projection": ...}  # Too nested!
    }
}

# ✓ Correct:
{
    "path": "file.txt",
    "_meta": {"projection": ...}  # Same level as path
}
```

## Performance Tips

1. **Use projection for structured data**: 90-95% token savings
2. **Use grep for logs/text**: 99%+ token savings
3. **Combine both**: Project fields, then grep within them
4. **Discover first**: Use `"_keys"` to see available fields before requesting
5. **Cache-friendly**: Same tool + args (excluding `_meta`) use cached results

## Token Savings Calculator

```python
# Estimate savings
full_response_size = 50000  # tokens
projected_fields = 3        # out of 50 fields
projected_size = full_response_size * (projected_fields / 50)  # ~3,000 tokens

savings_percent = (1 - projected_size / full_response_size) * 100
print(f"Estimated savings: {savings_percent:.1f}%")  # ~94%

# Cost savings (GPT-4 pricing: $0.03/1K input tokens)
cost_before = (full_response_size / 1000) * 0.03  # $1.50
cost_after = (projected_size / 1000) * 0.03       # $0.09
print(f"Cost savings per call: ${cost_before - cost_after:.2f}")  # $1.41
```

## Environment Variables

```bash
# Configuration file path
CONFIG_FILE=custom_mcp.json uv run -m mcp_proxy

# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=DEBUG uv run -m mcp_proxy

# Both
CONFIG_FILE=prod_mcp.json LOG_LEVEL=WARNING uv run -m mcp_proxy
```

## See Also

- [README.md](../README.md) - Full documentation
- [MIDDLEWARE_ADOPTION.md](MIDDLEWARE_ADOPTION.md) - Adoption guide for current MCP users
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Detailed migration instructions
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical architecture
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration details
- [RLM Paper](https://arxiv.org/abs/2512.24601) - Theoretical background
