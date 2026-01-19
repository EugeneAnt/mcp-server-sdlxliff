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

from sdlxliff_parser import SDLXLIFFParser


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


def resolve_file_path(file_path: str) -> Path:
    """
    Resolve a file path, handling Cowork sandbox path translation.

    Cowork passes sandbox paths like /sessions/xxx/mnt/folder/file.sdlxliff
    but MCP server runs on HOST where those don't exist. We extract the
    filename and search for it in common user directories.

    Args:
        file_path: The file path to resolve (may be sandbox or host path)

    Returns:
        Resolved Path object

    Raises:
        FileNotFoundError: If file cannot be found in any location
    """
    path = Path(file_path)
    filename = path.name

    # Extract parent folder name (e.g., "ru-RU" from the path)
    parent_name = path.parent.name if path.parent.name and path.parent.name != "mnt" else None

    logger.info(f"Resolving: {file_path}, filename={filename}, parent={parent_name}")

    # Try direct path first
    candidates = [path]

    # If it's a sandbox path, search common user directories
    if "/sessions/" in file_path or "/mnt/" in file_path or not path.exists():
        home = Path.home()
        search_roots = [
            home / "Documents",
            home / "Downloads",
            home / "Desktop",
            home,
            Path.cwd(),
        ]

        for root in search_roots:
            if not root.exists():
                continue
            # Try with parent folder name if we have it
            if parent_name:
                candidates.append(root / parent_name / filename)
                # Also search recursively for parent/filename pattern
                try:
                    for match in root.rglob(f"{parent_name}/{filename}"):
                        candidates.append(match)
                        break  # Take first match
                except (PermissionError, OSError):
                    pass
            # Try just the filename
            candidates.append(root / filename)
            # Search for file recursively (limited depth)
            try:
                for match in root.rglob(filename):
                    candidates.append(match)
                    break  # Take first match
            except (PermissionError, OSError):
                pass

    # Try each candidate
    tried = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if str(resolved) not in tried:
                tried.append(str(resolved))
            if resolved.exists() and resolved.is_file():
                logger.info(f"Resolved {file_path} -> {resolved}")
                return resolved
        except Exception as e:
            logger.debug(f"Path candidate {candidate} failed: {e}")

    # Not found - raise with details
    raise FileNotFoundError(f"File not found: {file_path}\nSearched for: {filename}\nTried: {tried[:10]}\nCWD: {os.getcwd()}")


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
        Tool(
            name="find_sdlxliff_files",
            description=(
                "IMPORTANT: Use this tool FIRST to find SDLXLIFF files before using other tools. "
                "Searches for .sdlxliff files in the specified directory. "
                "Returns file paths that can be used with read_sdlxliff and other tools. "
                "DO NOT write Python code to find or parse SDLXLIFF files - always use these dedicated tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to search (default: current directory). Use '.' for current folder.",
                        "default": ".",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Search subdirectories recursively (default: true)",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="read_sdlxliff",
            description=(
                "Extract all translation segments from an SDLXLIFF file. "
                "Returns segment IDs, source text, target text, status, and locked state. "
                "ALWAYS use this tool to read SDLXLIFF files - DO NOT write Python code to parse XML. "
                "Use find_sdlxliff_files first to get the file path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the SDLXLIFF file (from find_sdlxliff_files)",
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
                "Update a segment's target text and optionally its status. "
                "Use this to modify translations. Note: Changes are made in memory; "
                "you must call save_sdlxliff to persist changes."
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
                        "description": "The segment ID to update",
                    },
                    "target_text": {
                        "type": "string",
                        "description": "New target text for the segment",
                    },
                    "status": {
                        "type": "string",
                        "description": (
                            "Optional status to set. Common values: "
                            "'translated', 'needs-translation', 'needs-review-translation', "
                            "'needs-l10n', 'new', 'final'"
                        ),
                        "default": "needs-translation",
                    },
                },
                "required": ["file_path", "segment_id", "target_text"],
            },
        ),
        Tool(
            name="reject_sdlxliff_segment",
            description=(
                "Mark a segment as rejected and optionally update the target text. "
                "This is commonly used during translation review when a translation needs to be redone. "
                "By default, sets status to 'needs-translation'."
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
                        "description": "The segment ID to reject",
                    },
                    "target_text": {
                        "type": "string",
                        "description": "Optional corrected target text",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status to set (default: 'needs-translation'). Other options: 'needs-review-translation', 'rejected', etc.",
                        "default": "needs-translation",
                    },
                },
                "required": ["file_path", "segment_id"],
            },
        ),
        Tool(
            name="save_sdlxliff",
            description=(
                "Save changes made to an SDLXLIFF file. All modifications from "
                "update_sdlxliff_segment and reject_sdlxliff_segment are kept in memory "
                "until this tool is called. Can optionally save to a different file path."
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
                "Get statistics about an SDLXLIFF file, including total segment count, "
                "counts by status, and number of locked segments. Useful for getting "
                "an overview of translation progress."
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
        if name == "find_sdlxliff_files":
            directory = arguments.get("directory", ".")
            recursive = arguments.get("recursive", True)

            logger.info(f"find_sdlxliff_files: directory={directory}, recursive={recursive}")
            logger.info(f"CWD: {os.getcwd()}")

            # Extract folder name from sandbox path (e.g., "ru-RU" from /sessions/xxx/mnt/ru-RU)
            dir_path_obj = Path(directory)
            folder_name = dir_path_obj.name if dir_path_obj.name and dir_path_obj.name != "mnt" else None

            # Search in user directories (since sandbox paths don't exist on host)
            home = Path.home()
            search_dirs = []

            # If it's a sandbox path, search common user directories
            if "/sessions/" in directory or not Path(directory).exists():
                search_dirs = [
                    home / "Documents",
                    home / "Downloads",
                    home / "Desktop",
                ]
                # If we know the folder name, prioritize paths containing it
                if folder_name:
                    for base in search_dirs.copy():
                        if base.exists():
                            # Add specific folder path
                            specific = base / folder_name
                            if specific.exists():
                                search_dirs.insert(0, specific)
            else:
                # Direct path exists
                search_dirs = [Path(directory).resolve()]

            logger.info(f"Search dirs: {search_dirs}, folder_name: {folder_name}")

            # Search for SDLXLIFF files in these directories
            files = []
            searched_dirs = []
            for search_dir in search_dirs:
                if not search_dir.exists() or not search_dir.is_dir():
                    continue
                searched_dirs.append(str(search_dir))
                try:
                    if recursive:
                        found = list(search_dir.rglob("*.sdlxliff"))
                    else:
                        found = list(search_dir.glob("*.sdlxliff"))
                    files.extend(found)
                    logger.info(f"Found {len(found)} files in {search_dir}")
                    if found:
                        break  # Stop after finding files in first directory
                except (PermissionError, OSError) as e:
                    logger.warning(f"Cannot search {search_dir}: {e}")

            # Deduplicate
            files = list(set(files))

            logger.info(f"Found {len(files)} SDLXLIFF files")

            # Build file list with safe error handling for Unicode filenames
            file_list = []
            for file in sorted(files):
                try:
                    file_info = {
                        "path": str(file),
                        "name": file.name,
                        "size": file.stat().st_size,
                    }
                    file_list.append(file_info)
                except (OSError, UnicodeError) as e:
                    logger.warning(f"Error accessing file {file}: {e}")
                    # Still include the file path even if we can't get stats
                    file_list.append({
                        "path": str(file),
                        "name": file.name,
                        "size": -1,
                        "error": str(e)
                    })

            result = {
                "searched_directories": searched_dirs,
                "recursive": recursive,
                "count": len(file_list),
                "files": file_list,
                "hint": "Use read_sdlxliff with a file path from this list to extract segments"
            }

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]

        elif name == "read_sdlxliff":
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
            status = arguments.get("status", "needs-translation")

            parser = get_parser(file_path)
            success = parser.update_segment(segment_id, target_text, status)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully updated segment '{segment_id}'. "
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

        elif name == "reject_sdlxliff_segment":
            file_path = arguments["file_path"]
            segment_id = arguments["segment_id"]
            target_text = arguments.get("target_text")
            status = arguments.get("status", "needs-translation")

            parser = get_parser(file_path)

            if target_text:
                # Update both text and status
                success = parser.update_segment(segment_id, target_text, status)
            else:
                # Just update status
                success = parser.set_segment_status(segment_id, status)

            if success:
                msg = f"Successfully rejected segment '{segment_id}' "
                msg += f"(status set to '{status}')"
                if target_text:
                    msg += " and updated target text"
                msg += ". Remember to call save_sdlxliff to persist changes."

                return [TextContent(type="text", text=msg)]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to reject segment '{segment_id}'. Segment not found.",
                    )
                ]

        elif name == "save_sdlxliff":
            file_path = arguments["file_path"]
            output_path = arguments.get("output_path")

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