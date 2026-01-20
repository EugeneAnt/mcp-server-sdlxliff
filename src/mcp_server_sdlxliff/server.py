"""
MCP Server for SDLXLIFF File Operations

This server exposes tools for reading, analyzing, and modifying SDLXLIFF files
through the Model Context Protocol (MCP).
"""

import asyncio
import json
import os
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent, Resource
from mcp.server.stdio import stdio_server
import logging

from .parser import SDLXLIFFParser


# Set up logging - try multiple locations for sandbox compatibility
def setup_logging():
    """Set up logging to multiple locations for debugging."""
    log_locations = [
        Path("/mnt/sdlxliff_debug.log"),  # Cowork sandbox mounted folder
        Path.home() / "sdlxliff_debug.log",  # User home
        Path(tempfile.gettempdir()) / "sdlxliff_mcp_server.log",  # Temp dir
        Path("sdlxliff_debug.log"),  # Current working directory
    ]

    handlers = [logging.StreamHandler(sys.stderr)]  # Always log to stderr

    for log_path in log_locations:
        try:
            handler = logging.FileHandler(str(log_path), mode='a')
            handlers.append(handler)
            break  # Use first writable location
        except (PermissionError, OSError):
            continue

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    return logging.getLogger("sdlxliff-server")

logger = setup_logging()
logger.info(f"=== MCP Server Starting ===")
logger.info(f"CWD: {os.getcwd()}")
logger.info(f"Python: {sys.executable}")
logger.info(f"Platform: {sys.platform}")

# Create the MCP server instance
app = Server("sdlxliff-server")


@dataclass
class CachedParser:
    """Cache entry for parser with modification time tracking."""
    parser: SDLXLIFFParser
    mtime: float


# LRU-style cache with size limit and mtime validation
_parser_cache: dict[str, CachedParser] = {}
_CACHE_MAX_SIZE = 10  # Maximum number of cached parsers

# Cache for resolved paths (sandbox path -> host path)
_path_resolution_cache: dict[str, Path] = {}


# Allowed file extensions for this MCP server
ALLOWED_EXTENSIONS = {'.sdlxliff'}


def validate_file_extension(file_path: str) -> None:
    """
    Validate that the file has an allowed extension.

    Args:
        file_path: The file path to validate

    Raises:
        ValueError: If the file extension is not allowed
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Invalid file type: '{suffix}'. "
            f"This tool only supports SDLXLIFF files ({', '.join(ALLOWED_EXTENSIONS)})"
        )


def resolve_file_path(file_path: str) -> Path:
    """
    Resolve a file path, handling Cowork sandbox path translation.

    Args:
        file_path: The file path to resolve (may be sandbox or host path)

    Returns:
        Resolved Path object

    Raises:
        FileNotFoundError: If file cannot be found in any location
        ValueError: If the file extension is not allowed
    """
    # Validate file extension first
    validate_file_extension(file_path)
    # Check path resolution cache first (for sandbox paths)
    if file_path in _path_resolution_cache:
        cached_path = _path_resolution_cache[file_path]
        if cached_path.exists():
            logger.info(f"Path cache hit: {file_path} -> {cached_path}")
            return cached_path
        else:
            # Cached path no longer exists, remove from cache
            del _path_resolution_cache[file_path]

    logger.info(f"resolve_file_path called with: {file_path}")

    path = Path(file_path)

    # Fast path: if the file exists directly, return immediately
    try:
        if path.exists() and path.is_file():
            resolved = path.resolve()
            logger.info(f"Direct path exists: {resolved}")
            return resolved
    except (OSError, ValueError) as e:
        logger.debug(f"Direct path check failed: {e}")

    # If it's not a sandbox path and doesn't exist, fail fast
    is_sandbox_path = "/sessions/" in file_path or file_path.startswith("/mnt/")
    if not is_sandbox_path:
        raise FileNotFoundError(f"File not found: {file_path}")

    # Sandbox path translation: extract filename and parent folder
    filename = path.name
    parent_name = path.parent.name if path.parent.name and path.parent.name != "mnt" else None

    logger.info(f"Sandbox path detected, searching for: {filename} in parent: {parent_name}")

    # Search in common user directories
    home = Path.home()
    search_roots = [
        home / "Documents",
        home / "Downloads",
        home / "Desktop",
    ]

    # Try direct subfolder paths first (fast)
    for root in search_roots:
        if not root.exists():
            continue
        if parent_name:
            candidate = root / parent_name / filename
            if candidate.exists() and candidate.is_file():
                logger.info(f"Found via direct path: {candidate}")
                return candidate.resolve()

    # Last resort: recursive search (slow, but limited)
    for root in search_roots:
        if not root.exists():
            continue
        try:
            pattern = f"**/{parent_name}/{filename}" if parent_name else f"**/{filename}"
            for match in root.glob(pattern):
                if match.is_file():
                    resolved = match.resolve()
                    logger.info(f"Found via glob: {resolved}")
                    # Cache the resolution for future calls
                    _path_resolution_cache[file_path] = resolved
                    return resolved
        except (PermissionError, OSError) as e:
            logger.debug(f"Glob search in {root} failed: {e}")

    raise FileNotFoundError(f"File not found: {file_path}\nSearched for: {filename}")


def get_parser(file_path: str) -> SDLXLIFFParser:
    """
    Get or create a parser instance for the given file.

    Uses LRU-style caching with modification time validation to ensure
    fresh data and bounded memory usage.

    Args:
        file_path: Path to the SDLXLIFF file

    Returns:
        SDLXLIFFParser instance
    """
    # Resolve path with sandbox awareness
    path = resolve_file_path(file_path)
    normalized_path = str(path)

    # Get current file modification time
    current_mtime = path.stat().st_mtime

    # Check if cached and still valid
    if normalized_path in _parser_cache:
        cached = _parser_cache[normalized_path]
        if cached.mtime == current_mtime:
            # Move to end for LRU behavior (most recently used)
            _parser_cache.pop(normalized_path)
            _parser_cache[normalized_path] = cached
            return cached.parser
        else:
            # File modified, remove stale cache
            logger.debug(f"Cache invalidated for {normalized_path} (file modified)")
            _parser_cache.pop(normalized_path)

    # Evict oldest entry if cache is full
    if len(_parser_cache) >= _CACHE_MAX_SIZE:
        oldest_key = next(iter(_parser_cache))
        logger.debug(f"Evicting oldest cache entry: {oldest_key}")
        _parser_cache.pop(oldest_key)

    # Create new parser and cache it
    parser = SDLXLIFFParser(normalized_path)
    _parser_cache[normalized_path] = CachedParser(parser=parser, mtime=current_mtime)

    return parser


def clear_parser_cache(file_path: Optional[str] = None):
    """
    Clear parser cache for a specific file or all files.

    Args:
        file_path: Optional specific file path. If None, clears all cache.
    """
    if file_path:
        normalized_path = str(Path(file_path).resolve())
        _parser_cache.pop(normalized_path, None)
    else:
        _parser_cache.clear()


@app.list_resources()
async def list_resources() -> list[Resource]:
    """
    List available SDLXLIFF files as resources.

    Note: Returns empty list as file discovery should use the built-in
    filesystem server's search_files capability.
    """
    logger.info("list_resources called - returning empty (use filesystem search)")
    return []


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    logger.info(f"read_resource called with URI: {uri}")

    # Extract file path from URI
    if uri.startswith("sdlxliff:///"):
        file_path = uri.replace("sdlxliff:///", "")
        parser = get_parser(file_path)
        segments = parser.extract_segments()

        return json.dumps({
            "file": file_path,
            "segments": segments,
        }, indent=2, ensure_ascii=False)

    raise ValueError(f"Unknown resource URI: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available SDLXLIFF tools."""
    return [
        # NOTE: No find_sdlxliff_files tool - let Cowork's built-in file tools
        # discover files first, then use these tools with the real host paths.
        Tool(
            name="read_sdlxliff",
            description=(
                "Extract all translation segments from an SDLXLIFF file. "
                "Returns segment IDs, source text, target text, status, and locked state. "
                "ALWAYS use this tool to read SDLXLIFF files - DO NOT write Python code to parse XML. "
                "Use Cowork's built-in file tools to find the .sdlxliff file path first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the SDLXLIFF file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_sdlxliff_segment",
            description=(
                "Get a specific segment from an SDLXLIFF file by its segment ID. "
                "Returns the segment's source text, target text, status, and locked state."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the SDLXLIFF file (can be relative or absolute)",
                    },
                    "segment_id": {
                        "type": "string",
                        "description": "The segment ID to retrieve",
                    },
                },
                "required": ["file_path", "segment_id"],
            },
        ),
        Tool(
            name="update_sdlxliff_segment",
            description=(
                "Update a segment's target text and set status to RejectedTranslation. "
                "Use this to correct translations. The segment_id is the mrk mid (e.g., '1', '2', '42'). "
                "Changes are made in memory; you must call save_sdlxliff to persist changes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the SDLXLIFF file",
                    },
                    "segment_id": {
                        "type": "string",
                        "description": "The segment ID (mrk mid) to update",
                    },
                    "target_text": {
                        "type": "string",
                        "description": "New target text for the segment",
                    },
                },
                "required": ["file_path", "segment_id", "target_text"],
            },
        ),
        Tool(
            name="save_sdlxliff",
            description=(
                "Save changes made to an SDLXLIFF file. All modifications from "
                "update_sdlxliff_segment are kept in memory until this tool is called. "
                "Can optionally save to a different file path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the SDLXLIFF file to save",
                    },
                    "output_path": {
                        "type": "string",
                        "description": (
                            "Optional output path. If not provided, overwrites the original file."
                        ),
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_sdlxliff_statistics",
            description=(
                "Get statistics and metadata about an SDLXLIFF file. Returns source/target "
                "language codes (e.g., 'en-US' -> 'de-DE'), total segment count, counts by "
                "status, and locked segment count. Call this first to understand the file "
                "before reading segments."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the SDLXLIFF file (can be relative or absolute)",
                    },
                },
                "required": ["file_path"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""

    logger.info(f"call_tool: {name} with arguments: {arguments}")

    try:
        if name == "read_sdlxliff":
            file_path = arguments["file_path"]
            logger.info(f"read_sdlxliff: file_path={file_path}")
            logger.info(f"CWD: {os.getcwd()}")

            parser = get_parser(file_path)
            segments = parser.extract_segments()
            logger.info(f"Extracted {len(segments)} segments")

            return [
                TextContent(
                    type="text",
                    text=json.dumps(segments, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "get_sdlxliff_segment":
            file_path = arguments["file_path"]
            segment_id = arguments["segment_id"]
            parser = get_parser(file_path)
            segment = parser.get_segment_by_id(segment_id)

            if segment is None:
                return [
                    TextContent(
                        type="text",
                        text=f"Segment with ID '{segment_id}' not found.",
                    )
                ]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(segment, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "update_sdlxliff_segment":
            file_path = arguments["file_path"]
            segment_id = arguments["segment_id"]
            target_text = arguments["target_text"]

            parser = get_parser(file_path)
            success = parser.update_segment(segment_id, target_text)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully updated segment '{segment_id}' (status set to RejectedTranslation). "
                             f"Remember to call save_sdlxliff to persist changes.",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to update segment '{segment_id}'. Segment not found.",
                    )
                ]

        elif name == "save_sdlxliff":
            file_path = arguments["file_path"]
            output_path = arguments.get("output_path")

            # Validate output_path extension if provided
            if output_path:
                validate_file_extension(output_path)

            parser = get_parser(file_path)
            parser.save(output_path)

            # Clear cache after saving
            clear_parser_cache(file_path)

            save_location = output_path if output_path else file_path
            return [
                TextContent(
                    type="text",
                    text=f"Successfully saved SDLXLIFF file to: {save_location}",
                )
            ]

        elif name == "get_sdlxliff_statistics":
            file_path = arguments["file_path"]
            parser = get_parser(file_path)
            stats = parser.get_statistics()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(stats, indent=2, ensure_ascii=False),
                )
            ]

        else:
            return [
                TextContent(
                    type="text",
                    text=f"Unknown tool: {name}",
                )
            ]

    except FileNotFoundError as e:
        # Try to provide more helpful error message
        file_path = arguments.get("file_path", "unknown")
        resolved_path = str(Path(file_path).resolve())
        return [TextContent(
            type="text",
            text=f"File not found.\nRequested: {file_path}\nResolved to: {resolved_path}\nError: {str(e)}"
        )]
    except Exception as e:
        # Provide detailed error for debugging
        error_details = traceback.format_exc()
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}\n\nDetails:\n{error_details}"
        )]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())