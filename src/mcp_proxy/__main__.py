"""
Main entry point for the MCP-RLM Proxy Server.
"""

import asyncio
import os
import sys
from pathlib import Path

from mcp_proxy.logging_config import setup_logging


def main() -> None:
    """Main entry point."""
    log_level = os.getenv("MCP_PROXY_LOG_LEVEL", "INFO")
    setup_logging(level=log_level)
    asyncio.run(async_main())


async def async_main() -> None:
    """Async main entry point."""
    from mcp_proxy.config import load_config
    from mcp_proxy.server import MCPProxyServer

    # Look for mcp.json in the current directory or project root
    config_path = Path("mcp.json")
    if not config_path.exists():
        config_path = Path(__file__).parent.parent.parent / "mcp.json"

    underlying_servers, proxy_settings = load_config(str(config_path))
    proxy = MCPProxyServer(underlying_servers, proxy_settings=proxy_settings)
    await proxy.run()


if __name__ == "__main__":
    main()
