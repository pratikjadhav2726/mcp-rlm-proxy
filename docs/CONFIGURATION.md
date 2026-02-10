# Configuration Documentation

## Overview

The MCP Proxy Server uses MCP client-style JSON configuration (`mcp.json`), which matches the standard configuration format used by Claude Desktop and other MCP clients. Configuration is validated using Pydantic for robustness.

## Configuration File

The configuration is stored in `mcp.json` (default location). The server looks for this file in:
1. Current working directory
2. Project root (one level up from `src/`)

## Configuration Structure

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
      "env": {
        "VAR1": "value1",
        "VAR2": "value2"
      }
    }
  }
}
```

## Server Configuration Fields

### Server Name (Object Key)

The key in the `mcpServers` object is the server name.

- **Type**: String
- **Constraints**:
  - Must be unique across all servers
  - Alphanumeric characters, underscores (`_`), and hyphens (`-`) recommended
  - Used to prefix tool names (e.g., `filesystem_read_file`)

**Valid Examples:**
- `filesystem`
- `my_server`
- `server-1`
- `api_server_v2`

### `command` (Required)

Command to execute the server.

- **Type**: String
- **Examples**: `npx`, `python`, `node`, `uv`

### `args` (Optional)

List of arguments to pass to the command.

- **Type**: Array of strings
- **Default**: Empty array `[]`
- **Examples**:
  ```json
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  "args": ["-m", "my_mcp_server"]
  "args": []
  ```

### `env` (Optional)

Environment variables for the server process.

- **Type**: Object (key-value pairs)
- **Default**: `null` (no environment variables)
- **Example**:
  ```json
  "env": {
    "API_KEY": "your-api-key",
    "DEBUG": "true",
    "PATH": "/custom/path"
  }
  ```

## Validation Rules

### Server Name Validation

1. **Uniqueness**: Each server must have a unique name
2. **Format**: Recommended pattern `^[a-zA-Z0-9_-]+$`
3. **Clarity**: Use descriptive names

### Command Validation

1. **Required**: Must be provided
2. **Non-empty**: Cannot be empty string

### Global Validation

1. **No Duplicate Names**: All server names must be unique
2. **Valid JSON**: Configuration file must be valid JSON
3. **Type Safety**: All fields are type-checked

## Error Messages

When validation fails, you'll receive detailed error messages:

### Missing Required Field

```
ValueError: Invalid configuration in mcp.json:
Configuration validation errors:
  filesystem -> command: Field required
```

### Duplicate Server Names

```
ValueError: Invalid configuration in mcp.json:
Configuration validation errors:
  Duplicate server names found: filesystem
```

### Invalid JSON

```
ValueError: JSON parsing error in mcp.json: ...
```

## Examples

### Minimal Configuration

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

### Multiple Servers

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git", "/path/to/repo"]
    },
    "python-server": {
      "command": "python",
      "args": ["-m", "my_mcp_server"]
    }
  }
}
```

### With Environment Variables

```json
{
  "mcpServers": {
    "api-server": {
      "command": "python",
      "args": ["-m", "api_server"],
      "env": {
        "API_KEY": "secret-key",
        "DEBUG": "false",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Empty Configuration

```json
{
  "mcpServers": {}
}
```

Or an empty file (returns empty list).

## Programmatic Usage

### Loading Configuration

```python
from mcp_proxy.config import load_config

# Load from default location (mcp.json)
servers = load_config()

# Load from custom location
servers = load_config("/path/to/custom_mcp.json")
```

### Using Pydantic Models Directly

```python
from mcp_proxy.config import ServerConfig, ProxyConfig

# Create a server configuration
server_data = {
    "name": "filesystem",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
}

server = ServerConfig.model_validate(server_data)

# Validate and convert to dict
config_dict = server.model_dump()
```

## Best Practices

1. **Use Descriptive Names**: Choose clear, descriptive server names
   - Good: `filesystem`, `git-server`, `api-backend`
   - Bad: `s1`, `server`, `test`

2. **Keep Names Simple**: Use alphanumeric characters, underscores, and hyphens
   - Avoid special characters that might cause issues

3. **Validate Early**: Test your configuration before deploying
   ```bash
   python -c "from mcp_proxy.config import load_config; load_config('mcp.json')"
   ```

4. **Use Environment Variables**: For sensitive data like API keys
   ```json
   {
     "env": {
       "API_KEY": "${API_KEY}"
     }
   }
   ```
   Note: Environment variable substitution depends on your shell/environment

5. **Document Your Configuration**: Add comments in a separate README
   ```json
   {
     "mcpServers": {
       "filesystem": {
         "comment": "Provides file system access to /tmp only",
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
       }
     }
   }
   ```

## Troubleshooting

### Configuration Not Found

If the config file is not found, the server will:
- Log a warning
- Return an empty list (no servers configured)
- Continue running (useful for testing)

### Validation Errors

If validation fails:
1. Check the error message for the specific field and issue
2. Verify the field name is correct (case-sensitive)
3. Check for duplicate server names
4. Ensure JSON syntax is correct

### Common Issues

**Issue**: "Field required" error
- **Solution**: Ensure all required fields (`command`) are present

**Issue**: "Duplicate server names" error
- **Solution**: Ensure each server has a unique name

**Issue**: JSON parsing errors
- **Solution**: Validate your JSON syntax using a JSON validator or linter

## Comparison with Claude Desktop Config

The proxy `mcp.json` format is **identical** to Claude Desktop's configuration format. You can copy server configurations directly between them:

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
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

**MCP Proxy config** (`mcp.json`):
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

Same format! This makes migration and configuration management much easier.

## Advanced Configuration

### Multiple Instances of Same Server

```json
{
  "mcpServers": {
    "fs-home": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
    },
    "fs-projects": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]
    }
  }
}
```

### Using uv to Run Python Servers

```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "python", "-m", "my_mcp_server"]
    }
  }
}
```

## See Also

- [Architecture Documentation](ARCHITECTURE.md) - System architecture
- [Quick Reference Guide](QUICK_REFERENCE.md) - Quick lookup
- [Main README](../README.md) - Project overview
- [Migration Guide](MIGRATION_GUIDE.md) - Migrating from other formats
