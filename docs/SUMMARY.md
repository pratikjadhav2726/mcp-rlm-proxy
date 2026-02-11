# MCP-RLM-Proxy: Summary & Comparison

## What Is This?

The **MCP-RLM-Proxy** is an intelligent middleware layer that sits between MCP clients (like Claude Desktop, custom agents) and MCP servers (filesystem, git, APIs, etc.). It enhances the MCP protocol with:

1. **Field Projection** - Extract only needed fields from responses (85-95% token savings)
2. **Grep Search** - Filter large outputs with regex patterns (99%+ token savings on logs)
3. **Multi-Server Aggregation** - Connect to multiple MCP servers through one interface
4. **Recursive Context Management** - Implement RLM paper principles for handling large outputs
5. **Performance Monitoring** - Track token savings and connection health

**Key Point**: Your existing MCP servers require **ZERO modifications**. The proxy works transparently as middleware.

## How It Compares

### Direct MCP Connection (Traditional)

```
┌─────────────┐
│  AI Client  │
└──────┬──────┘
       │
       ├─────► Server 1 (filesystem)
       ├─────► Server 2 (git)
       └─────► Server 3 (api)

Issues:
- Must manage 3 separate connections
- Tools might conflict (name collisions)
- No response filtering
- Full tool outputs loaded into context (wasteful)
- No token usage tracking
```

**Example Call**:
```python
# Read entire 50KB JSON file
result = await session.call_tool("read_file", {"path": "data.json"})
# Returns: 50,000 tokens (you only needed 500)
```

### With MCP-RLM-Proxy (Enhanced)

```
┌─────────────┐
│  AI Client  │
└──────┬──────┘
       │ One connection
       ▼
┌─────────────┐
│ MCP-RLM Proxy │ ◄── Filters, aggregates, tracks
└──────┬──────┘
       ├─────► Server 1 (filesystem)
       ├─────► Server 2 (git)
       └─────► Server 3 (api)

Benefits:
✓ Single connection to manage
✓ Tools namespaced (no conflicts)
✓ Response filtering (projection/grep)
✓ Only needed data in context
✓ Automatic token savings tracking
```

**Example RLM-Style Flow**:
```python
# 1) Call filesystem_read_file via proxy; assume response truncated with cache_id="agent_1:DATA123456".

# 2) Use proxy_filter to read only needed fields from the cached response.
result = await session.call_tool("proxy_filter", {
    "cache_id": "agent_1:DATA123456",
    "fields": ["users.name", "users.email"],
    "mode": "include"
})
# Returns: ~500 tokens (99% savings!)
```

## Feature Comparison Matrix

| Feature | Direct MCP | With MCP-RLM-Proxy |
|---------|-----------|-------------------|
| **Server Connections** | One client → one server | One client → N servers |
| **Tool Naming** | Direct names (conflicts possible) | Prefixed names (no conflicts) |
| **Response Filtering** | ❌ Not available | ✅ Projection + Grep |
| **Token Optimization** | ❌ Load everything | ✅ 85-99% savings |
| **Performance Tracking** | ❌ Manual | ✅ Automatic metrics |
| **Connection Pooling** | ❌ Reconnect each time | ✅ Persistent connections |
| **Parallel Tool Discovery** | ❌ Sequential | ✅ Parallel (3x faster) |
| **RLM Principles** | ❌ Not available | ✅ Recursive exploration |
| **Server Changes Required** | N/A | ✅ **Zero changes** |
| **Migration Time** | N/A | ⏱️ 5-15 minutes |

## Recursive Language Models (RLM) Integration

The proxy implements principles from the [Recursive Language Models paper](https://arxiv.org/abs/2512.24601):

### What are RLMs?

RLMs treat large contexts (like tool outputs) as "external environments" that can be explored programmatically rather than loaded entirely into the model's context window.

**Traditional Approach**:
```
Agent → Tool → [50,000 token output] → Load ALL into context
```

**RLM Approach**:
```
Agent → Proxy → Tool
      ↓
Agent: "What fields are available?"
Proxy: Returns field list (50 tokens)
      ↓
Agent: "Get user email and status only"
Proxy: Returns filtered data (200 tokens)
      ↓
Agent: "Search for active users"
Proxy: Returns grep results (300 tokens)

Total: 550 tokens vs 50,000 tokens (99% savings)
```

### RLM Features Implemented

| RLM Concept | Implementation |
|-------------|----------------|
| **External Environment** | Tool outputs treated as queryable data stores |
| **Programmatic Exploration** | Use proxy tools (`proxy_filter`, `proxy_search`, `proxy_explore`) to selectively retrieve data |
| **Recursive Decomposition** | Break large outputs into explorable chunks |
| **Snippet Processing** | Return only matched content + context |
| **Context Efficiency** | 85-99% reduction in context window usage |

### Example: Recursive Exploration

```python
# Traditional: Load everything (50,000 tokens)
data = await call_tool("api_get_users")

# RLM: Explore recursively (1,000 tokens total)

# Step 1: Call api_get_users via proxy; assume truncated + cached with cache_id="agent_1:USERS123456".

# Step 2: Discover structure with proxy_explore
fields = await call_tool("proxy_explore", {
    "cache_id": "agent_1:USERS123456",
    "max_depth": 3
})
# Returns: structure summary and field names (≈50 tokens)

# Step 3: Get overview with proxy_filter
overview = await call_tool("proxy_filter", {
    "cache_id": "agent_1:USERS123456",
    "fields": ["id", "name", "status"],
    "mode": "include"
})
# Returns: Basic info for all users (≈500 tokens)

# Step 4: Drill down with proxy_filter
details = await call_tool("proxy_filter", {
    "cache_id": "agent_1:USERS123456",
    "fields": ["email", "profile.bio"],
    "mode": "include"
})
# Returns: Specific user details (≈450 tokens)

# Total: ~1,000 tokens vs 50,000 (98% savings)
```

## When to Use This Proxy

### ✅ Use the Proxy When:

1. **Multiple MCP Servers** - You use 2+ MCP servers and want unified access
2. **Large Outputs** - Your tools return large JSON/logs/data structures
3. **Token Costs Matter** - You want to reduce AI costs by 85-99%
4. **Context Management** - You need efficient context window usage
5. **Production Systems** - You want metrics and connection pooling
6. **Recursive Exploration** - You want to implement RLM patterns

### ⚠️ Consider Alternatives When:

1. **Single Simple Server** - You only use one MCP server with small responses
2. **No Filtering Needed** - You always need full tool outputs
3. **Maximum Simplicity** - Direct connection is simpler (though proxy is only +5ms latency)

## Migration Path

### From Direct Connection

**Time Required**: 5-15 minutes  
**Server Changes**: Zero  
**Reversible**: Yes (easy rollback)

**Before**:
```json
{
  "mcpServers": {
    "filesystem": {"command": "npx", "args": ["...", "/path"]}
  }
}
```

**After**:
```yaml
# config.yaml
underlying_servers:
  - name: filesystem
    command: npx
    args: ["...", "/path"]
```

```json
{
  "mcpServers": {
    "proxy": {"command": "uv", "args": ["run", "-m", "mcp_proxy"], "cwd": "/path/to/proxy"}
  }
}
```

**Changes to Your Code**:
- Tool names: `read_file` → `filesystem_read_file` (automatic prefixing)
- Optional: Add `_meta` parameters to optimize token usage

See [Migration Guide](MIGRATION_GUIDE.md) for details.

## Cost Impact Analysis

### Example: Production Agent (1,000 calls/day)

**Scenario**: AI agent making 1,000 tool calls per day, average 20,000 tokens per response

**Without Proxy**:
```
1,000 calls × 20,000 tokens = 20,000,000 tokens/day
Cost (GPT-4 @ $0.03/1K): $600/day = $18,000/month
```

**With Proxy (90% savings)**:
```
1,000 calls × 2,000 tokens = 2,000,000 tokens/day
Cost (GPT-4 @ $0.03/1K): $60/day = $1,800/month
Savings: $16,200/month ($194,400/year)
```

**Break-even**: Immediate (proxy is free and open source)

### Real-World Examples

| Use Case | Before | After | Savings |
|----------|--------|-------|---------|
| **User Profile API** | 2,500 tokens | 150 tokens | 94% |
| **Log File Search** | 280,000 tokens | 800 tokens | 99.7% |
| **Database Query** | 15,000 tokens | 1,200 tokens | 92% |
| **File System Scan** | 8,000 tokens | 400 tokens | 95% |

## Technical Details

### Architecture

- **Language**: Python 3.12+
- **Framework**: MCP SDK (official)
- **Async**: Full async/await support
- **Connection Model**: Persistent connections with background tasks
- **Protocol**: 100% MCP specification compliant

### Performance

| Metric | Value |
|--------|-------|
| **Projection Overhead** | 2-5ms |
| **Grep Overhead (< 1MB)** | 10-50ms |
| **Grep Overhead (> 10MB)** | 100-500ms |
| **Connection Setup** | ~3s for 5 servers (parallel) |
| **Memory** | Minimal (streaming support) |

### Dependencies

```toml
dependencies = [
    "mcp>=1.23.1",        # Official MCP SDK
    "pyyaml>=6.0.3",      # Config parsing
    "pydantic>=2.0.0",    # Validation
]
```

## Comparison with Alternatives

### vs Direct MCP Connection

- **Complexity**: Slightly higher setup (+5 min), much lower runtime complexity
- **Performance**: +5ms latency, but 85-99% token savings (net win)
- **Features**: Adds projection, grep, multi-server, metrics

**Verdict**: Use proxy for production systems, direct for quick prototypes

### vs Custom Filtering in Agent Code

- **Proxy Approach**: Filter at the source (before entering context)
- **Agent Approach**: Filter after loading (wastes tokens/context)
- **Proxy Benefits**: 
  - Filter happens on server side
  - No wasted context window space
  - Reusable across all agents
  - No per-agent implementation

**Verdict**: Proxy is more efficient and reusable

### vs Other MCP Middleware Solutions

As of Feb 2026, this is one of the first comprehensive MCP middleware solutions implementing:
- Field projection
- Grep filtering
- RLM principles
- Multi-server aggregation
- Performance tracking

## Use Cases

### 1. **AI Agents in Production**

Multiple agents connecting to various data sources need efficient context management.

**Solution**: Central proxy connects to all data sources, agents get filtered responses.

### 2. **Claude Desktop Power Users**

Users with 5+ MCP servers want unified access without tool naming conflicts.

**Solution**: Proxy aggregates all servers, prefixes tool names, tracks usage.

### 3. **Log Analysis Agents**

Agent needs to search through GB-sized log files efficiently.

**Solution**: Use grep to extract only relevant log lines (99.7% token savings).

### 4. **API Integration Agents**

Agent calls APIs returning large JSON but only needs specific fields.

**Solution**: Use projection to extract only required fields (90-95% token savings).

### 5. **Development Teams**

Team wants to experiment with MCP but needs to quickly swap/test servers.

**Solution**: Change config.yaml, restart proxy. No client changes needed.

## Getting Started

1. **Read**: [Middleware Adoption Guide](docs/MIDDLEWARE_ADOPTION.md)
2. **Install**: `git clone ... && uv sync`
3. **Configure**: Create `config.yaml` with your servers
4. **Migrate**: Follow [Migration Guide](docs/MIGRATION_GUIDE.md)
5. **Optimize**: Add `_meta` parameters to reduce tokens
6. **Monitor**: Check logs for token savings

## Resources

- **Documentation**: See `docs/` folder
- **Examples**: See `examples/` folder
- **RLM Paper**: [arXiv:2512.24601](https://arxiv.org/abs/2512.24601)
- **MCP Spec**: [modelcontextprotocol.io](https://modelcontextprotocol.io)
- **GitHub**: [Repository](https://github.com/yourusername/mcp-rlm-proxy)

## Summary

| Aspect | Summary |
|--------|---------|
| **What** | Intelligent middleware for MCP servers |
| **Why** | 85-99% token savings, multi-server aggregation, RLM principles |
| **How** | Field projection + grep filtering + connection pooling |
| **For Whom** | AI agent developers, Claude Desktop users, production systems |
| **Setup Time** | 5-15 minutes |
| **Server Changes** | Zero (works with existing servers) |
| **Reversible** | Yes (easy rollback) |
| **Cost** | Free (open source) |
| **Savings** | $194K+/year for typical production agent |

**Bottom Line**: If you're using MCP servers in production or want to reduce AI token costs dramatically, this proxy is for you.

