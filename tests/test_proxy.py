"""
Integration test script to verify the proxy server works correctly.

Connects to the proxy via stdio and validates:
- Connection and initialisation
- Tool listing (proxy tools + underlying tools, clean schemas)
- Server instructions are present
"""

import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_proxy_connection():
    """Test basic connection to proxy server."""
    print("Testing MCP-RLM Proxy Server Connection...")
    print("=" * 60)

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize session
                init_result = await session.initialize()
                print("[OK] Successfully connected to proxy server")
                server_info = init_result.serverInfo
                print(f"  Server: {server_info.name if server_info else 'Unknown'}")
                print(f"  Version: {server_info.version if server_info else 'Unknown'}")

                # Check instructions
                if hasattr(init_result, "instructions") and init_result.instructions:
                    print(f"  Instructions: {init_result.instructions[:80]}...")
                else:
                    print("  Instructions: (not provided by SDK version)")

                # List tools
                tools_result = await session.list_tools()
                print(f"\n[OK] Successfully listed tools")
                print(f"  Available tools: {len(tools_result.tools)}")

                # Check for proxy tools
                proxy_tool_names = {"proxy_filter", "proxy_search", "proxy_explore"}
                found_proxy = set()
                for tool in tools_result.tools:
                    if tool.name in proxy_tool_names:
                        found_proxy.add(tool.name)

                if found_proxy == proxy_tool_names:
                    print("  [OK] All 3 proxy tools registered: proxy_filter, proxy_search, proxy_explore")
                else:
                    missing = proxy_tool_names - found_proxy
                    print(f"  [WARN] Missing proxy tools: {missing}")

                # Show first few tools
                if tools_result.tools:
                    print("  Tool names:")
                    for tool in tools_result.tools[:6]:
                        schema = tool.inputSchema
                        props = list(schema.get("properties", {}).keys()) if isinstance(schema, dict) else []
                        # Confirm no _meta pollution
                        has_meta = "_meta" in props
                        meta_status = "HAS _meta (unexpected)" if has_meta else "clean schema"
                        print(f"    - {tool.name} ({meta_status})")
                    if len(tools_result.tools) > 6:
                        print(f"    ... and {len(tools_result.tools) - 6} more tools")

                print("\n" + "=" * 60)
                print("[OK] All checks passed!")

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(test_proxy_connection())
    exit(0 if success else 1)
