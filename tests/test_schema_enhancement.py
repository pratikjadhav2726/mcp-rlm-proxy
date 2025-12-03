"""
Test script to verify that tool schemas include the _meta parameter.
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_schema_enhancement():
    """Test that tool schemas include _meta parameter."""
    print("Testing Schema Enhancement...")
    print("=" * 60)
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"]
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await asyncio.sleep(3)  # Wait for underlying servers
                
                # List tools
                tools_result = await session.list_tools()
                print(f"\nFound {len(tools_result.tools)} tools\n")
                
                # Check first few tools for _meta parameter
                found_meta = 0
                missing_meta = 0
                
                for tool in tools_result.tools[:5]:  # Check first 5 tools
                    print(f"Tool: {tool.name}")
                    
                    # Get schema
                    schema = tool.inputSchema
                    if hasattr(schema, 'model_dump'):
                        schema_dict = schema.model_dump()
                    elif isinstance(schema, dict):
                        schema_dict = schema
                    else:
                        schema_dict = {}
                    
                    # Check for _meta
                    if isinstance(schema_dict, dict):
                        properties = schema_dict.get("properties", {})
                        additional_props = schema_dict.get("additionalProperties", None)
                        
                        print(f"  additionalProperties: {additional_props}")
                        print(f"  Properties: {list(properties.keys())}")
                        
                        if "_meta" in properties:
                            print(f"  ✓ _meta parameter found!")
                            meta_props = properties["_meta"].get("properties", {})
                            print(f"    _meta.properties: {list(meta_props.keys())}")
                            found_meta += 1
                        else:
                            print(f"  ✗ _meta parameter MISSING")
                            missing_meta += 1
                            # Print full schema for debugging
                            print(f"    Full schema: {json.dumps(schema_dict, indent=2)}")
                    print()
                
                print("=" * 60)
                print(f"Summary:")
                print(f"  Tools with _meta: {found_meta}")
                print(f"  Tools without _meta: {missing_meta}")
                
                if found_meta > 0:
                    print("\n✓ SUCCESS: _meta parameter is being added to tool schemas!")
                else:
                    print("\n✗ FAILURE: _meta parameter is NOT being added to tool schemas!")
                
                return found_meta > 0
                
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_schema_enhancement())
    exit(0 if success else 1)

