"""
Main entry point for the MCP Proxy Server.
"""

import asyncio
import sys
from pathlib import Path


def main():
    """Main entry point."""
    asyncio.run(async_main())


async def async_main():
    """Async main entry point."""
    from mcp_proxy.config import load_config
    from mcp_proxy.server import MCPProxyServer

    # Load server configurations from config file
    # Look for config.yaml in the current directory or project root
    config_path = Path("config.yaml")
    if not config_path.exists():
        # Try project root (one level up from src/)
        config_path = Path(__file__).parent.parent.parent / "config.yaml"

    underlying_servers = load_config(str(config_path))
    proxy = MCPProxyServer(underlying_servers)
    await proxy.run()


if __name__ == "__main__":
    main()

