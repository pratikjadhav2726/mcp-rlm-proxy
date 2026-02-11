# Quick Start Guide

Get the MCP‑RLM‑Proxy up and running in a few minutes.

## Step 1: Install Dependencies

```bash
uv sync
```

Or, if you prefer `pip`:

```bash
pip install -e .
```

## Step 2: Configure Underlying Servers (`mcp.json`)

Copy the example config and edit it:

```bash
cp mcp.json.example mcp.json
```

Edit `mcp.json` to add your MCP servers. This uses the same format as Claude Desktop:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
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

## Step 3: Run the MCP-RLM Proxy Server

From the project root:

```bash
uv run -m mcp_proxy
```

Or, after installation:

```bash
mcp-rlm-proxy
```

The server will:
- Load configuration from `mcp.json`
- Connect to all configured servers
- Start listening for MCP client connections via stdio

## Step 4: Connect from an MCP Client

### Claude Desktop

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

Claude will now see:
- All underlying tools, prefixed as `filesystem_read_file`, `git_commit`, etc.
- Three first‑class proxy tools: `proxy_filter`, `proxy_search`, and `proxy_explore`

## Step 5: Use the Proxy Tools

1. Call an underlying tool via the proxy (e.g. `filesystem_read_file`).  
2. If the response is large, it will be truncated and cached, and you’ll receive a `cache_id`.  
3. Use one of the proxy tools with that `cache_id`:

- `proxy_filter` – project/filter fields
- `proxy_search` – regex/BM25/fuzzy/context search
- `proxy_explore` – discover structure without loading everything

### Example: Filter Cached Result

```json
{
  "name": "proxy_filter",
  "arguments": {
    "cache_id": "abc123def456",
    "fields": ["users.name", "users.email"],
    "mode": "include"
  }
}
```

## Legacy `_meta` Support

The proxy still accepts `_meta.projection` and `_meta.grep` on underlying tools for backward compatibility, but the **recommended** approach is to use the dedicated proxy tools (`proxy_filter`, `proxy_search`, `proxy_explore`).

## Troubleshooting

**Problem**: "Config file not found"  
- **Solution**: Create `mcp.json` from `mcp.json.example`

**Problem**: "Failed to connect to server"  
- **Solution**: Check that the server `command` and `args` are correct in `mcp.json`

**Problem**: "Tool not found"  
- **Solution**: Remember that tools are prefixed with the server name, e.g. `filesystem_read_file`

## Next Steps

- Read the full `README.md` for detailed documentation
- Check the `examples/` directory for usage examples
- Explore the docs in `docs/` for architecture, configuration, and performance details

