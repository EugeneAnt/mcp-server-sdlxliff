"""
Entry point for running the MCP server.

Usage:
    python -m mcp_server_sdlxliff
    # or after installation:
    mcp-server-sdlxliff

    # With search directories for Claude Desktop:
    mcp-server-sdlxliff --directory /path/to/translations
    mcp-server-sdlxliff -d ~/Documents/Projects -d ~/Translations

    # Or use environment variable:
    SDLXLIFF_SEARCH_DIRS=/path1:/path2 mcp-server-sdlxliff
"""

import argparse
import asyncio
import os
from pathlib import Path


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MCP server for SDLXLIFF translation files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mcp-server-sdlxliff                                    # Use default directories
  mcp-server-sdlxliff -d ~/Documents/Translations        # Search specific directory
  mcp-server-sdlxliff -d ~/Dir1 -d ~/Dir2                # Search multiple directories
  SDLXLIFF_SEARCH_DIRS=~/Dir1:~/Dir2 mcp-server-sdlxliff # Use environment variable
        """
    )
    parser.add_argument(
        "-d", "--directory",
        action="append",
        dest="directories",
        metavar="PATH",
        help="Directory to search for SDLXLIFF files. Can be specified multiple times."
    )
    return parser.parse_args()


def get_search_directories(args) -> list[Path]:
    """
    Get search directories from arguments and environment variables.

    Priority:
    1. Command-line --directory arguments
    2. SDLXLIFF_SEARCH_DIRS environment variable (colon-separated on Unix, semicolon on Windows)
    3. Default directories (Documents, Downloads, Desktop, Translations)
    """
    directories = []

    # Check command-line arguments first
    if args.directories:
        for d in args.directories:
            path = Path(d).expanduser().resolve()
            if path.exists() and path.is_dir():
                directories.append(path)

    # If no CLI args, check environment variable
    if not directories:
        env_dirs = os.environ.get("SDLXLIFF_SEARCH_DIRS", "")
        if env_dirs:
            # Use : on Unix, ; on Windows
            separator = ";" if os.name == "nt" else ":"
            for d in env_dirs.split(separator):
                d = d.strip()
                if d:
                    path = Path(d).expanduser().resolve()
                    if path.exists() and path.is_dir():
                        directories.append(path)

    return directories


def run():
    """Run the MCP server."""
    args = parse_args()
    search_dirs = get_search_directories(args)

    # Import here to avoid circular imports and set up directories before server starts
    from .server import main, set_search_directories

    if search_dirs:
        set_search_directories(search_dirs)

    asyncio.run(main())


if __name__ == "__main__":
    run()