"""
Example usage of the MCP-RLM Proxy Server

This demonstrates how to use the proxy server with field projection and grep search.
"""

import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def example_with_projection():
    """Example: Using field projection to get only specific fields."""
    print("=== Example: Field Projection ===\n")
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "proxy_server.py"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Wait for underlying servers to connect
            await asyncio.sleep(3)
            
            # List available tools
            tools = await session.list_tools()
            print(f"Available tools: {[tool.name for tool in tools.tools[:10]]}")
            if len(tools.tools) > 10:
                print(f"... and {len(tools.tools) - 10} more\n")
            else:
                print()
            
            # Try to find a tool that might return structured data
            # Look for tools from the "everything" server
            everything_tools = [t for t in tools.tools if t.name.startswith("everything_")]
            
            if everything_tools:
                tool_name = everything_tools[0].name
                print(f"Trying tool: {tool_name}")
                print("Note: This example demonstrates the new proxy_filter syntax.\n")
                print("Typical RLM-style flow:")
                print("  1. Call the underlying tool (possibly truncated, with cache_id).")
                print("  2. Use proxy_filter with that cache_id to project only needed fields.\n")
                print("Example proxy_filter request:")
                print('  Tool: "proxy_filter"')
                print("  Arguments:")
                print("  {")
                print('    "cache_id": "agent_1:ABC123DEF456",')
                print('    "fields": ["name", "email", "status"],')
                print('    "mode": "include"')
                print("  }")
                print("\nThis returns only the specified fields from the cached response.\n")
            else:
                print("No tools available. Configure underlying servers in config.yaml.\n")


async def example_with_grep():
    """Example: Using grep to filter tool outputs."""
    print("=== Example: Grep Search ===\n")
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "proxy_server.py"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Wait for underlying servers to connect
            await asyncio.sleep(3)
            
            # List available tools
            tools = await session.list_tools()
            
            # Look for file reading tools
            file_tools = [t for t in tools.tools if "read" in t.name.lower() or "file" in t.name.lower()]
            
            if file_tools:
                tool_name = file_tools[0].name
                print(f"Example underlying tool: {tool_name}")
                print("Note: This example demonstrates the new proxy_search syntax.\n")
                print("Typical RLM-style flow:")
                print("  1. Call the underlying tool (filesystem_read_file, api_call, etc.).")
                print("  2. Use proxy_search with the cache_id to search inside the cached text.\n")
                print("Example proxy_search request:")
                print('  Tool: "proxy_search"')
                print("  Arguments:")
                print("  {")
                print('    "cache_id": "agent_1:ABC123DEF456",')
                print('    "pattern": "ERROR|WARN",')
                print('    "mode": "regex",')
                print('    "context_lines": 2,')
                print('    "max_results": 20')
                print("  }")
                print("\nThis returns only matching lines plus context.\n")
            else:
                print("Example proxy_search syntax:")
                print('  Tool: "proxy_search"')
                print("  Arguments:")
                print("  {")
                print('    "cache_id": "agent_1:ABC123DEF456",')
                print('    "pattern": "ERROR",')
                print('    "mode": "regex",')
                print('    "max_results": 10')
                print("  }\n")


async def example_combined():
    """Example: Using both projection and grep together."""
    print("=== Example: Combined Transformations ===\n")
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "proxy_server.py"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Wait for underlying servers to connect
            await asyncio.sleep(3)
            
            print("Example: Combining proxy_filter and proxy_search")
            print("This allows you to:")
            print("  1. Filter fields using proxy_filter")
            print("  2. Search within the filtered results using proxy_search\n")
            print("Example combined flow:")
            print("  1) Call underlying tool (e.g., api_get_users) via the proxy.")
            print("  2) Use proxy_filter with the returned cache_id:")
            print("     Tool: proxy_filter")
            print("     Arguments:")
            print("     {")
            print('       "cache_id": "agent_1:ABC123DEF456",')
            print('       "fields": ["name", "email", "status"],')
            print('       "mode": "include"')
            print("     }")
            print("  3) Then use proxy_search on the same cache_id or on a new cached result:")
            print("     Tool: proxy_search")
            print("     Arguments:")
            print("     {")
            print('       "cache_id": "agent_1:ABC123DEF456",')
            print('       "pattern": "gmail\\.com",')
            print('       "mode": "regex"')
            print("     }")
            print("\nThis will project only selected fields and then search for entries containing 'gmail.com'.\n")


async def main():
    """Run all examples."""
    print("MCP-RLM Proxy Server Usage Examples\n")
    print("=" * 50 + "\n")
    
    # Note: These examples are commented out because they require
    # actual underlying MCP servers to be configured.
    # Uncomment and configure your servers in config.yaml to test.
    
    await example_with_projection()
    await example_with_grep()
    await example_combined()
    
    print("\n" + "=" * 50)
    print("Note: Configure underlying servers in config.yaml to test these examples.")


if __name__ == "__main__":
    asyncio.run(main())

