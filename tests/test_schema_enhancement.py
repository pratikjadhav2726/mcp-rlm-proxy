"""
Integration test to verify that tool schemas are CLEAN (no _meta pollution)
and that the three proxy tools are present with flat schemas.
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_schema_cleanliness():
    """Verify schemas are clean and proxy tools are present."""
    print("Testing Schema Cleanliness & Proxy Tools...")
    print("=" * 60)

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await asyncio.sleep(3)  # Wait for underlying servers

                tools_result = await session.list_tools()
                print(f"\nFound {len(tools_result.tools)} tools\n")

                # Check for proxy tools
                proxy_tools = {}
                underlying_tools = []
                polluted_count = 0

                for tool in tools_result.tools:
                    schema = tool.inputSchema
                    if hasattr(schema, "model_dump"):
                        schema_dict = schema.model_dump()
                    elif isinstance(schema, dict):
                        schema_dict = schema
                    else:
                        schema_dict = {}

                    props = list(schema_dict.get("properties", {}).keys())

                    if tool.name.startswith("proxy_"):
                        proxy_tools[tool.name] = props
                        print(f"[PROXY] {tool.name}")
                        print(f"  Parameters: {props}")
                    else:
                        underlying_tools.append(tool.name)
                        has_meta = "_meta" in props
                        if has_meta:
                            polluted_count += 1
                            print(f"  [FAIL] {tool.name} — _meta still present!")
                        else:
                            print(f"  [OK]   {tool.name} — clean schema")

                print(f"\n{'=' * 60}")
                print("Summary:")
                print(f"  Proxy tools:      {len(proxy_tools)}/3")
                print(f"  Underlying tools: {len(underlying_tools)}")
                print(f"  Polluted schemas: {polluted_count}")

                # Verify proxy tools
                expected_proxy = {"proxy_filter", "proxy_search", "proxy_explore"}
                found_proxy = set(proxy_tools.keys())

                if found_proxy == expected_proxy:
                    print("\n[OK] All proxy tools present!")
                else:
                    missing = expected_proxy - found_proxy
                    print(f"\n[FAIL] Missing proxy tools: {missing}")

                # Verify no _meta pollution
                if polluted_count == 0:
                    print("[OK] No _meta pollution in underlying tool schemas!")
                else:
                    print(f"[FAIL] {polluted_count} tool(s) still have _meta in schema!")

                # Verify proxy tools have flat schemas
                for name, params in proxy_tools.items():
                    nested_count = 0
                    tool_schema = None
                    for t in tools_result.tools:
                        if t.name == name:
                            tool_schema = t.inputSchema if isinstance(t.inputSchema, dict) else {}
                            break
                    if tool_schema:
                        for p_name, p_def in tool_schema.get("properties", {}).items():
                            p_type = p_def.get("type", "")
                            # 'object' for arguments is acceptable (it's a pass-through)
                            if p_type == "object" and p_name != "arguments":
                                nested_count += 1
                    if nested_count == 0:
                        print(f"[OK] {name} has flat parameters")
                    else:
                        print(f"[WARN] {name} has {nested_count} nested object param(s)")

                success = found_proxy == expected_proxy and polluted_count == 0
                print(f"\nOverall: {'PASS' if success else 'FAIL'}")
                return success

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_schema_cleanliness())
    exit(0 if success else 1)
