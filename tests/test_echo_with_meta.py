"""
Example test for everything_echo tool with _meta parameter (projection and grep).
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_echo_basic():
    """Test basic echo without _meta."""
    print("=" * 60)
    print("Test 1: Basic echo (no _meta)")
    print("=" * 60)
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await asyncio.sleep(3)  # Wait for underlying servers
            
            result = await session.call_tool(
                "everything_echo",
                {
                    "message": "Hello, this is a test message with ERROR and WARN keywords"
                }
            )
            
            print("Arguments:")
            print(json.dumps({"message": "Hello, this is a test message with ERROR and WARN keywords"}, indent=2))
            print("\nResponse:")
            for item in result.content:
                if hasattr(item, 'text'):
                    print(item.text)
            print()


async def test_echo_with_grep():
    """Test echo with grep filtering."""
    print("=" * 60)
    print("Test 2: Echo with grep (filter for ERROR/WARN)")
    print("=" * 60)
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await asyncio.sleep(3)
            
            result = await session.call_tool(
                "everything_echo",
                {
                    "message": "This is line 1\nThis is an ERROR message\nThis is line 3\nThis is a WARN message\nThis is line 5",
                    "_meta": {
                        "grep": {
                            "pattern": "ERROR|WARN",
                            "caseInsensitive": True
                        }
                    }
                }
            )
            
            print("Arguments:")
            print(json.dumps({
                "message": "This is line 1\nThis is an ERROR message\nThis is line 3\nThis is a WARN message\nThis is line 5",
                "_meta": {
                    "grep": {
                        "pattern": "ERROR|WARN",
                        "caseInsensitive": True
                    }
                }
            }, indent=2))
            print("\nResponse:")
            for item in result.content:
                if hasattr(item, 'text'):
                    text = item.text
                    if "MCP Proxy Metadata" in text:
                        print("Metadata:")
                        print(text)
                    else:
                        print("Filtered content:")
                        print(text)
            print()


async def test_echo_with_grep_max_matches():
    """Test echo with grep and maxMatches limit."""
    print("=" * 60)
    print("Test 3: Echo with grep and maxMatches=2")
    print("=" * 60)
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await asyncio.sleep(3)
            
            result = await session.call_tool(
                "everything_echo",
                {
                    "message": "ERROR 1\nINFO message\nERROR 2\nWARN message\nERROR 3\nDEBUG message",
                    "_meta": {
                        "grep": {
                            "pattern": "ERROR|WARN",
                            "caseInsensitive": False,
                            "maxMatches": 2
                        }
                    }
                }
            )
            
            print("Arguments:")
            print(json.dumps({
                "message": "ERROR 1\nINFO message\nERROR 2\nWARN message\nERROR 3\nDEBUG message",
                "_meta": {
                    "grep": {
                        "pattern": "ERROR|WARN",
                        "caseInsensitive": False,
                        "maxMatches": 2
                    }
                }
            }, indent=2))
            print("\nResponse:")
            for item in result.content:
                if hasattr(item, 'text'):
                    text = item.text
                    if "MCP Proxy Metadata" in text:
                        print("Metadata:")
                        # Extract and pretty print metadata
                        try:
                            meta_start = text.find("{")
                            if meta_start != -1:
                                meta_json = json.loads(text[meta_start:])
                                print(json.dumps(meta_json, indent=2))
                        except:
                            print(text)
                    else:
                        print("Filtered content (max 2 matches):")
                        print(text)
            print()


async def test_echo_schema_check():
    """Check that echo tool schema includes _meta parameter."""
    print("=" * 60)
    print("Test 4: Verify _meta parameter in tool schema")
    print("=" * 60)
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await asyncio.sleep(3)
            
            tools_result = await session.list_tools()
            
            # Find the echo tool
            echo_tool = None
            for tool in tools_result.tools:
                if tool.name == "everything_echo":
                    echo_tool = tool
                    break
            
            if not echo_tool:
                print("✗ everything_echo tool not found!")
                return
            
            print(f"Found tool: {echo_tool.name}")
            print(f"Description: {echo_tool.description}\n")
            
            # Get schema
            schema = echo_tool.inputSchema
            if hasattr(schema, 'model_dump'):
                schema_dict = schema.model_dump()
            elif isinstance(schema, dict):
                schema_dict = schema
            else:
                schema_dict = {}
            
            print("Tool Input Schema:")
            print(json.dumps(schema_dict, indent=2))
            print()
            
            # Check for _meta
            properties = schema_dict.get("properties", {})
            if "_meta" in properties:
                print("✓ _meta parameter is present in schema!")
                print("\n_meta structure:")
                print(json.dumps(properties["_meta"], indent=2))
            else:
                print("✗ _meta parameter is MISSING from schema!")
            
            print()


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("MCP Proxy - everything_echo Tool Tests with _meta")
    print("=" * 60 + "\n")
    
    try:
        await test_echo_schema_check()
        await test_echo_basic()
        await test_echo_with_grep()
        await test_echo_with_grep_max_matches()
        
        print("=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

