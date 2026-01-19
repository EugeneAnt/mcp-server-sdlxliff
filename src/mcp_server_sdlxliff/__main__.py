"""
Entry point for running the MCP server.

Usage:
    python -m mcp_server_sdlxliff
    # or after installation:
    mcp-server-sdlxliff
"""

from .server import main
import asyncio


def run():
    """Run the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()