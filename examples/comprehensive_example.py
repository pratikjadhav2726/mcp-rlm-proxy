"""
Comprehensive example demonstrating all MCP-RLM-Proxy features.

This example shows:
1. Multi-server connection
2. Field projection (include/exclude modes)
3. Grep search with context
4. Combined projection + grep
5. Recursive exploration (RLM pattern)
6. Token savings tracking
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def connect_to_proxy():
    """Connect to the MCP proxy server."""
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "-m", "mcp_proxy"],
        cwd="../"  # Assuming examples/ is subdirectory
    )
    
    return stdio_client(server_params)


async def example_1_list_tools():
    """Example 1: List all tools from multiple servers."""
    print("=" * 60)
    print("Example 1: Multi-Server Tool Aggregation")
    print("=" * 60)
    
    async with await connect_to_proxy() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Wait for servers to connect
            await asyncio.sleep(2)
            
            # List all tools
            tools_result = await session.list_tools()
            
            # Group by server
            servers = {}
            for tool in tools_result.tools:
                server_name = tool.name.split("_")[0]
                if server_name not in servers:
                    servers[server_name] = []
                servers[server_name].append(tool.name)
            
            print(f"\nFound {len(tools_result.tools)} tools from {len(servers)} server(s):\n")
            for server, tools in servers.items():
                print(f"  {server}: {len(tools)} tools")
                print(f"    Sample: {', '.join(tools[:3])}")
            
            print("\n✓ All servers connected through one proxy interface!\n")


async def example_2_field_projection():
    """Example 2: Using field projection to reduce token usage."""
    print("=" * 60)
    print("Example 2: Field Projection (Token Savings)")
    print("=" * 60)
    
    async with await connect_to_proxy() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await asyncio.sleep(2)
            
            # Create sample JSON file
            sample_data = {
                "users": [
                    {
                        "id": 1,
                        "name": "Alice Smith",
                        "email": "alice@example.com",
                        "password_hash": "hashed_secret_1",
                        "profile": {
                            "bio": "Software engineer",
                            "location": "San Francisco",
                            "website": "https://alice.dev"
                        },
                        "internal_notes": "VIP customer",
                        "created_at": "2024-01-15",
                        "last_login": "2026-02-05"
                    },
                    {
                        "id": 2,
                        "name": "Bob Jones",
                        "email": "bob@gmail.com",
                        "password_hash": "hashed_secret_2",
                        "profile": {
                            "bio": "Product manager",
                            "location": "New York",
                            "website": "https://bob.io"
                        },
                        "internal_notes": "Beta tester",
                        "created_at": "2024-02-20",
                        "last_login": "2026-02-04"
                    }
                ],
                "metadata": {
                    "total": 2,
                    "page": 1,
                    "timestamp": "2026-02-05T10:30:00Z"
                }
            }
            
            print("\n📄 Sample data structure:")
            print(f"  Full JSON: {len(json.dumps(sample_data))} characters")
            print(f"  Contains: users (with profiles), metadata, sensitive fields")
            
            # Example 2a: Include only needed fields
            print("\n🔍 Example 2a: Include mode (whitelist)")
            print("  Request: Get only user names and emails")
            print("  Projection: include ['users.name', 'users.email']")
            
            # Simulate projection (in real use, this would be done by proxy)
            projected_include = {
                "users": [
                    {"name": u["name"], "email": u["email"]} 
                    for u in sample_data["users"]
                ]
            }
            
            print(f"\n  ✓ Result: {len(json.dumps(projected_include))} characters")
            print(f"  ✓ Savings: {100 - (len(json.dumps(projected_include)) / len(json.dumps(sample_data)) * 100):.1f}%")
            print(f"\n  {json.dumps(projected_include, indent=2)}")
            
            # Example 2b: Exclude sensitive fields
            print("\n🔒 Example 2b: Exclude mode (blacklist sensitive data)")
            print("  Request: Get all data EXCEPT passwords and internal notes")
            print("  Projection: exclude ['users.password_hash', 'users.internal_notes']")
            
            projected_exclude = {
                "users": [
                    {k: v for k, v in u.items() if k not in ["password_hash", "internal_notes"]}
                    for u in sample_data["users"]
                ],
                "metadata": sample_data["metadata"]
            }
            
            print(f"\n  ✓ Result: Sensitive fields removed")
            print(f"  ✓ Safe for agent context")
            print(f"\n  Sample user: {json.dumps(projected_exclude['users'][0], indent=2)}")


async def example_3_grep_search():
    """Example 3: Using grep to filter large text outputs."""
    print("\n" + "=" * 60)
    print("Example 3: Grep Search (Log Analysis)")
    print("=" * 60)
    
    # Sample log data
    log_content = """2026-02-05 10:00:01 INFO Server started on port 8080
2026-02-05 10:00:15 INFO User alice@example.com logged in
2026-02-05 10:01:22 INFO Database connection established
2026-02-05 10:02:45 WARN Slow query detected: SELECT * FROM users (2.3s)
2026-02-05 10:03:12 INFO Request processed: GET /api/users
2026-02-05 10:05:33 ERROR Database connection lost
2026-02-05 10:05:34 ERROR Retry attempt 1 failed
2026-02-05 10:05:35 ERROR Retry attempt 2 failed
2026-02-05 10:05:36 INFO Database connection restored
2026-02-05 10:06:00 INFO Request processed: POST /api/users
2026-02-05 10:07:15 WARN High memory usage: 85%
2026-02-05 10:08:00 INFO User bob@gmail.com logged in
2026-02-05 10:09:00 FATAL Out of memory error
2026-02-05 10:09:01 ERROR Server crashed
2026-02-05 10:09:02 INFO Server restarting
2026-02-05 10:09:10 INFO Server started on port 8080"""
    
    print(f"\n📊 Sample log file:")
    print(f"  Total lines: {len(log_content.split(chr(10)))}")
    print(f"  Size: {len(log_content)} characters")
    
    # Example 3a: Basic grep
    print("\n🔍 Example 3a: Basic grep (find errors)")
    print("  Pattern: 'ERROR'")
    
    error_lines = [line for line in log_content.split("\n") if "ERROR" in line]
    print(f"\n  ✓ Found {len(error_lines)} matches")
    print(f"  ✓ Savings: {100 - (len('\n'.join(error_lines)) / len(log_content) * 100):.1f}%")
    print("\n  Results:")
    for line in error_lines:
        print(f"    {line}")
    
    # Example 3b: Grep with context
    print("\n📍 Example 3b: Grep with context lines")
    print("  Pattern: 'FATAL'")
    print("  Context: 2 lines before and after")
    
    lines = log_content.split("\n")
    fatal_idx = [i for i, line in enumerate(lines) if "FATAL" in line]
    
    print(f"\n  ✓ Found {len(fatal_idx)} matches with context")
    print("\n  Results:")
    for idx in fatal_idx:
        start = max(0, idx - 2)
        end = min(len(lines), idx + 3)
        print("\n  Context:")
        for i in range(start, end):
            marker = "  >>> " if i == idx else "      "
            print(f"{marker}{lines[i]}")
    
    # Example 3c: Regex pattern
    print("\n🔎 Example 3c: Regex pattern (emails)")
    print("  Pattern: r'\\w+@\\w+\\.com'")
    
    import re
    email_pattern = re.compile(r'\w+@\w+\.com')
    email_lines = [line for line in lines if email_pattern.search(line)]
    
    print(f"\n  ✓ Found {len(email_lines)} lines with emails")
    print("\n  Results:")
    for line in email_lines:
        emails = email_pattern.findall(line)
        print(f"    {line}")
        print(f"      Emails: {', '.join(emails)}")


async def example_4_combined():
    """Example 4: Combining projection and grep."""
    print("\n" + "=" * 60)
    print("Example 4: Combined Projection + Grep")
    print("=" * 60)
    
    # Sample API response with user activity logs
    api_response = {
        "users": [
            {
                "id": 1,
                "name": "Alice",
                "email": "alice@gmail.com",
                "status": "active",
                "activity_log": "Login successful\nProfile updated\nLogout successful"
            },
            {
                "id": 2,
                "name": "Bob",
                "email": "bob@yahoo.com",
                "status": "inactive",
                "activity_log": "Login failed\nPassword reset\nLogin successful"
            },
            {
                "id": 3,
                "name": "Charlie",
                "email": "charlie@gmail.com",
                "status": "active",
                "activity_log": "Login successful\nData export\nLogout successful"
            }
        ]
    }
    
    print("\n📦 Sample API response:")
    print(f"  3 users with activity logs")
    print(f"  Size: {len(json.dumps(api_response))} characters")
    
    print("\n🎯 Goal: Find Gmail users with 'Login successful' in logs")
    print("  Step 1: Project to get emails and logs only")
    print("  Step 2: Grep for Gmail addresses")
    print("  Step 3: Grep within logs for 'Login successful'")
    
    # Step 1: Project
    projected = {
        "users": [
            {"name": u["name"], "email": u["email"], "activity_log": u["activity_log"]}
            for u in api_response["users"]
        ]
    }
    
    # Step 2: Filter for Gmail
    gmail_users = {
        "users": [u for u in projected["users"] if "gmail.com" in u["email"]]
    }
    
    # Step 3: Filter by activity
    successful_login_users = {
        "users": [u for u in gmail_users["users"] if "Login successful" in u["activity_log"]]
    }
    
    print(f"\n  ✓ After projection: {len(json.dumps(projected))} chars")
    print(f"  ✓ After Gmail filter: {len(gmail_users['users'])} users")
    print(f"  ✓ After login filter: {len(successful_login_users['users'])} users")
    print(f"  ✓ Total savings: {100 - (len(json.dumps(successful_login_users)) / len(json.dumps(api_response)) * 100):.1f}%")
    
    print("\n  Final results:")
    print(json.dumps(successful_login_users, indent=2))


async def example_5_recursive_exploration():
    """Example 5: Recursive exploration (RLM pattern)."""
    print("\n" + "=" * 60)
    print("Example 5: Recursive Exploration (RLM Pattern)")
    print("=" * 60)
    
    # Large nested structure
    large_data = {
        "company": {
            "name": "Acme Corp",
            "employees": [{"id": i, "name": f"Employee {i}", "salary": 50000 + i * 1000} for i in range(1, 101)],
            "departments": [{"id": i, "name": f"Dept {i}", "budget": 100000 * i} for i in range(1, 21)],
            "projects": [{"id": i, "name": f"Project {i}", "status": "active"} for i in range(1, 51)],
        },
        "metadata": {"version": "1.0", "timestamp": "2026-02-05"}
    }
    
    full_size = len(json.dumps(large_data))
    print(f"\n📦 Large data structure:")
    print(f"  Size: {full_size:,} characters")
    print(f"  Contains: 100 employees, 20 departments, 50 projects")
    print(f"  Loading all data: ~{full_size * 0.25:.0f} tokens")
    
    print("\n🔄 RLM Recursive Exploration:")
    
    # Step 1: Discover structure
    print("\n  Step 1: Discover available fields")
    print("    Request: Get field names only")
    keys = list(large_data.keys())
    company_keys = list(large_data["company"].keys())
    print(f"    ✓ Top-level keys: {keys}")
    print(f"    ✓ Company keys: {company_keys}")
    print(f"    ✓ Tokens used: ~20")
    
    # Step 2: Get overview
    print("\n  Step 2: Get high-level overview")
    print("    Request: Get company name and counts")
    overview = {
        "company": {
            "name": large_data["company"]["name"],
            "employee_count": len(large_data["company"]["employees"]),
            "department_count": len(large_data["company"]["departments"]),
            "project_count": len(large_data["company"]["projects"])
        }
    }
    overview_size = len(json.dumps(overview))
    print(f"    ✓ Result: {overview_size} characters")
    print(f"    ✓ Tokens used: ~{overview_size * 0.25:.0f}")
    print(f"    {json.dumps(overview, indent=2)}")
    
    # Step 3: Drill down
    print("\n  Step 3: Get specific details")
    print("    Request: Get employees 1-5 with names and salaries")
    details = {
        "employees": [
            {"name": e["name"], "salary": e["salary"]}
            for e in large_data["company"]["employees"][:5]
        ]
    }
    details_size = len(json.dumps(details))
    print(f"    ✓ Result: {details_size} characters")
    print(f"    ✓ Tokens used: ~{details_size * 0.25:.0f}")
    
    # Summary
    total_tokens = 20 + (overview_size * 0.25) + (details_size * 0.25)
    full_tokens = full_size * 0.25
    savings = 100 - (total_tokens / full_tokens * 100)
    
    print(f"\n  📊 Summary:")
    print(f"    Traditional approach: ~{full_tokens:.0f} tokens")
    print(f"    RLM approach: ~{total_tokens:.0f} tokens")
    print(f"    ✓ Savings: {savings:.1f}%")
    print(f"    ✓ Agent explored data efficiently without loading everything!")


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("MCP-RLM-Proxy Comprehensive Examples")
    print("=" * 60)
    print("\nDemonstrating:")
    print("  1. Multi-server tool aggregation")
    print("  2. Field projection (include/exclude)")
    print("  3. Grep search with patterns")
    print("  4. Combined projection + grep")
    print("  5. Recursive exploration (RLM)")
    print("\n" + "=" * 60)
    
    try:
        # Example 1: Multi-server
        await example_1_list_tools()
        
        # Example 2: Projection
        await example_2_field_projection()
        
        # Example 3: Grep
        await example_3_grep_search()
        
        # Example 4: Combined
        await example_4_combined()
        
        # Example 5: RLM
        await example_5_recursive_exploration()
        
        print("\n" + "=" * 60)
        print("✓ All examples completed!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Try these patterns with your own servers")
        print("  2. Monitor token savings in proxy logs")
        print("  3. Create reusable projection templates")
        print("  4. Explore recursive patterns for your data")
        print("\nSee docs/ for more information!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        print("\nMake sure:")
        print("  1. Proxy is configured with at least one server")
        print("  2. config.yaml exists and is valid")
        print("  3. Run from examples/ directory: python comprehensive_example.py")


if __name__ == "__main__":
    asyncio.run(main())

