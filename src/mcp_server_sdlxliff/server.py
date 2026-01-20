"""
MCP Server for SDLXLIFF File Operations

This server exposes tools for reading, analyzing, and modifying SDLXLIFF files
through the Model Context Protocol (MCP).

Supports both Claude Cowork (folder-based) and Claude Desktop (explicit file paths).
For Claude Desktop, use --directory arguments or SDLXLIFF_SEARCH_DIRS env var to
configure search paths for file discovery.
"""

import asyncio
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    ResourceTemplate,
    Prompt,
    PromptMessage,
    PromptArgument,
    GetPromptResult,
)
from mcp.server.stdio import stdio_server
import logging

from .cache import (
    get_parser,
    clear_parser_cache,
    validate_file_extension,
)
from .constants import (
    get_default_search_directories,
    MAX_SEARCH_DEPTH,
    MAX_FILES_TO_LIST,
    ALLOWED_EXTENSIONS,
)


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

# Module-level state for search directories and discovered files
_search_directories: list[Path] = []
_discovered_files_cache: dict[str, dict] = {}  # path -> {mtime, size, ...}
_last_discovery_time: Optional[float] = None
DISCOVERY_CACHE_TTL = 30.0  # seconds


def set_search_directories(directories: list[Path]) -> None:
    """Set the directories to search for SDLXLIFF files."""
    global _search_directories, _discovered_files_cache, _last_discovery_time
    _search_directories = directories
    _discovered_files_cache = {}
    _last_discovery_time = None
    logger.info(f"Search directories set: {[str(d) for d in directories]}")


def get_search_directories() -> list[Path]:
    """Get configured search directories, falling back to defaults."""
    if _search_directories:
        return _search_directories
    return get_default_search_directories()


def discover_sdlxliff_files(
    directories: Optional[list[Path]] = None,
    max_depth: int = MAX_SEARCH_DEPTH,
    max_files: int = MAX_FILES_TO_LIST,
) -> list[dict]:
    """
    Discover SDLXLIFF files in the given directories.

    Args:
        directories: Directories to search (uses configured/defaults if None)
        max_depth: Maximum recursion depth
        max_files: Maximum number of files to return

    Returns:
        List of file info dicts with path, name, size, modified time
    """
    global _discovered_files_cache, _last_discovery_time

    # Use cache if recent enough
    import time
    now = time.time()
    if _last_discovery_time and (now - _last_discovery_time) < DISCOVERY_CACHE_TTL:
        if _discovered_files_cache:
            return list(_discovered_files_cache.values())[:max_files]

    dirs = directories or get_search_directories()
    if not dirs:
        logger.warning("No search directories configured or available")
        return []

    files = []
    seen_paths = set()

    def search_dir(dir_path: Path, depth: int = 0):
        if depth > max_depth or len(files) >= max_files:
            return
        try:
            for entry in dir_path.iterdir():
                if len(files) >= max_files:
                    return
                try:
                    if entry.is_file():
                        if entry.suffix.lower() in ALLOWED_EXTENSIONS:
                            abs_path = str(entry.resolve())
                            if abs_path not in seen_paths:
                                seen_paths.add(abs_path)
                                stat = entry.stat()
                                file_info = {
                                    "path": abs_path,
                                    "name": entry.name,
                                    "size": stat.st_size,
                                    "modified": datetime.fromtimestamp(
                                        stat.st_mtime
                                    ).isoformat(),
                                    "directory": str(entry.parent),
                                }
                                files.append(file_info)
                                _discovered_files_cache[abs_path] = file_info
                    elif entry.is_dir() and not entry.name.startswith('.'):
                        search_dir(entry, depth + 1)
                except (PermissionError, OSError) as e:
                    logger.debug(f"Cannot access {entry}: {e}")
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot read directory {dir_path}: {e}")

    for directory in dirs:
        if len(files) >= max_files:
            break
        logger.info(f"Searching for SDLXLIFF files in: {directory}")
        search_dir(directory)

    _last_discovery_time = now

    # Sort by modified time (most recent first)
    files.sort(key=lambda f: f["modified"], reverse=True)
    logger.info(f"Discovered {len(files)} SDLXLIFF files")

    return files[:max_files]


@app.list_resources()
async def list_resources() -> list[Resource]:
    """
    List available SDLXLIFF files as resources.

    Discovers files in configured search directories and exposes them as
    resources that Claude Desktop can access.
    """
    logger.info("list_resources called - discovering files")

    files = discover_sdlxliff_files()

    resources = []
    for file_info in files:
        # Create a resource for each discovered file
        file_path = file_info["path"]
        resources.append(
            Resource(
                uri=f"sdlxliff:///{file_path}",
                name=file_info["name"],
                description=f"SDLXLIFF translation file ({file_info['size']} bytes, modified {file_info['modified']})",
                mimeType="application/xml",
            )
        )

    logger.info(f"list_resources returning {len(resources)} resources")
    return resources


@app.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    """
    List resource templates for dynamic file access.

    Allows Claude to access SDLXLIFF files by path even if not discovered.
    """
    return [
        ResourceTemplate(
            uriTemplate="sdlxliff:///{path}",
            name="SDLXLIFF File",
            description="Access an SDLXLIFF translation file by its full path",
            mimeType="application/xml",
        )
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    logger.info(f"read_resource called with URI: {uri}")

    # Extract file path from URI
    if uri.startswith("sdlxliff:///"):
        file_path = uri.replace("sdlxliff:///", "")
        parser = get_parser(file_path)

        # Get statistics for overview
        stats = parser.get_statistics()

        # Get first few segments as preview
        all_segments = parser.extract_segments()
        preview_segments = all_segments[:10]

        return json.dumps({
            "file": file_path,
            "statistics": stats,
            "preview_segments": preview_segments,
            "total_segments": len(all_segments),
            "note": "Use read_sdlxliff tool for full segment access with pagination"
        }, indent=2, ensure_ascii=False)

    raise ValueError(f"Unknown resource URI: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available SDLXLIFF tools."""
    return [
        Tool(
            name="list_sdlxliff_files",
            description=(
                "Discover and list SDLXLIFF files in configured directories. "
                "Use this first in Claude Desktop to find available translation files. "
                "Returns file paths, names, sizes, and modification times. "
                "Files are sorted by modification time (most recent first). "
                "Optionally specify a directory to search, otherwise uses configured directories "
                "(Documents, Downloads, Desktop, Translations by default)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": (
                            "Optional: Specific directory to search. "
                            "If not provided, searches all configured directories."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of files to return (default: 50, max: 100)",
                        "default": 50,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="read_sdlxliff",
            description=(
                "Extract translation segments from an SDLXLIFF file. "
                "Returns segment IDs, source text, target text, status, and locked state. "
                "Maximum 50 segments per request (enforced). Use offset parameter to paginate through large files. "
                "Use include_tags=true only when you need to UPDATE segments with formatting tags. "
                "ALWAYS use this tool to read SDLXLIFF files - DO NOT write Python code to parse XML."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the SDLXLIFF file",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Starting segment index (0-based). Use with limit for pagination. Default: 0",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            "Number of segments to return (max 50, enforced). Default: 50."
                        ),
                    },
                    "include_tags": {
                        "type": "boolean",
                        "description": (
                            "If true, includes source_tagged/target_tagged fields with tag placeholders. "
                            "Only needed when planning to update segments with formatting tags. "
                            "Default: false (smaller output)."
                        ),
                        "default": False,
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_sdlxliff_segment",
            description=(
                "Get a specific segment from an SDLXLIFF file by its segment ID. "
                "Returns the segment's source text, target text, status, locked state, and tag information. "
                "For segments with inline tags, both clean and tagged versions are provided."
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
                "IMPORTANT: For segments with formatting tags (has_tags=true), you MUST include "
                "tag placeholders in target_text to preserve formatting. "
                "Format: {id}text{/id} for paired tags, {x:id} for self-closing. "
                "Example: '{5}Acme{/5}{6}&{/6}{7} Events{/7}'. "
                "If tags are missing or malformed, the update will be rejected with an error. "
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
                        "description": (
                            "New target text for the segment. For segments with tags, "
                            "include placeholders like {5}text{/5} or {x:5}"
                        ),
                    },
                    "preserve_tags": {
                        "type": "boolean",
                        "description": (
                            "If true (default), validates and restores tags from placeholders. "
                            "If false, strips all tags and uses plain text."
                        ),
                        "default": True,
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
        Tool(
            name="validate_sdlxliff_segment",
            description=(
                "Validate proposed changes to a segment before updating. "
                "Checks that all required tags are present and properly formatted. "
                "Use this to pre-validate translations before calling update_sdlxliff_segment. "
                "Returns validation result with any errors or warnings."
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
                        "description": "The segment ID (mrk mid) to validate against",
                    },
                    "target_text": {
                        "type": "string",
                        "description": (
                            "Proposed target text with tag placeholders to validate. "
                            "Format: {id}text{/id} for paired tags, {x:id} for self-closing."
                        ),
                    },
                },
                "required": ["file_path", "segment_id", "target_text"],
            },
        ),
    ]


@app.list_prompts()
async def list_prompts() -> list[Prompt]:
    """
    List available prompts for common SDLXLIFF workflows.

    These prompts help Claude Desktop users get started quickly with
    common translation review tasks.
    """
    return [
        Prompt(
            name="review-translations",
            description="Review translations in an SDLXLIFF file for quality issues",
            arguments=[
                PromptArgument(
                    name="file_path",
                    description="Path to the SDLXLIFF file to review",
                    required=True,
                ),
                PromptArgument(
                    name="focus",
                    description="What to focus on: grammar, terminology, consistency, or all",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name="find-sdlxliff",
            description="Find SDLXLIFF files on your computer",
            arguments=[
                PromptArgument(
                    name="directory",
                    description="Optional: specific directory to search",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name="translation-status",
            description="Get a summary of translation progress for an SDLXLIFF file",
            arguments=[
                PromptArgument(
                    name="file_path",
                    description="Path to the SDLXLIFF file",
                    required=True,
                ),
            ],
        ),
    ]


@app.get_prompt()
async def get_prompt(name: str, arguments: Optional[dict] = None) -> GetPromptResult:
    """
    Get a specific prompt with its messages.
    """
    args = arguments or {}

    if name == "review-translations":
        file_path = args.get("file_path", "")
        focus = args.get("focus", "all")

        focus_instructions = {
            "grammar": "Focus specifically on grammar and spelling errors in the translations.",
            "terminology": "Focus on consistent use of terminology and domain-specific terms.",
            "consistency": "Focus on consistency between similar phrases and repeated content.",
            "all": "Check for grammar, terminology, consistency, and overall translation quality.",
        }

        return GetPromptResult(
            description=f"Review translations in {file_path or 'an SDLXLIFF file'}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please review the translations in this SDLXLIFF file for quality issues.

File: {file_path if file_path else "[Please provide the file path]"}

Instructions:
1. First, use get_sdlxliff_statistics to understand the file's language pair and segment counts
2. Then use read_sdlxliff to read the segments (use pagination if there are many)
3. {focus_instructions.get(focus, focus_instructions['all'])}
4. For any issues found, explain the problem and suggest corrections
5. If corrections are needed, use update_sdlxliff_segment to fix them
6. After all updates, use save_sdlxliff to save the changes

Please proceed with the review."""
                    ),
                )
            ],
        )

    elif name == "find-sdlxliff":
        directory = args.get("directory", "")

        return GetPromptResult(
            description="Find SDLXLIFF translation files",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please find SDLXLIFF translation files on my computer.

{f"Search in: {directory}" if directory else "Search in default locations (Documents, Downloads, Desktop, Translations)."}

Use the list_sdlxliff_files tool to discover available files. Show me a summary of what you find, including:
- File names
- File locations
- File sizes
- Last modified dates

If no files are found, suggest where I might look for SDLXLIFF files or how to configure search directories."""
                    ),
                )
            ],
        )

    elif name == "translation-status":
        file_path = args.get("file_path", "")

        return GetPromptResult(
            description=f"Get translation status for {file_path or 'an SDLXLIFF file'}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please give me a summary of the translation status for this SDLXLIFF file.

File: {file_path if file_path else "[Please provide the file path]"}

Use get_sdlxliff_statistics to get:
- Source and target languages
- Total number of segments
- Breakdown by status (Draft, Translated, Approved, etc.)
- Number of locked segments

Present this as a clear summary of translation progress."""
                    ),
                )
            ],
        )

    raise ValueError(f"Unknown prompt: {name}")


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""

    logger.info(f"call_tool: {name} with arguments: {arguments}")

    try:
        if name == "list_sdlxliff_files":
            directory = arguments.get("directory")
            max_results = min(arguments.get("max_results", 50), MAX_FILES_TO_LIST)

            search_dirs = None
            if directory:
                dir_path = Path(directory).expanduser().resolve()
                if not dir_path.exists():
                    return [TextContent(
                        type="text",
                        text=f"Directory not found: {directory}"
                    )]
                if not dir_path.is_dir():
                    return [TextContent(
                        type="text",
                        text=f"Path is not a directory: {directory}"
                    )]
                search_dirs = [dir_path]

            files = discover_sdlxliff_files(
                directories=search_dirs,
                max_files=max_results,
            )

            # Get the directories that were searched
            searched = search_dirs or get_search_directories()

            response = {
                "searched_directories": [str(d) for d in searched],
                "files_found": len(files),
                "files": files,
            }

            if not files:
                response["hint"] = (
                    "No SDLXLIFF files found. You can:\n"
                    "1. Specify a directory with the 'directory' parameter\n"
                    "2. Configure search directories when starting the server with -d flag\n"
                    "3. Set SDLXLIFF_SEARCH_DIRS environment variable\n"
                    "4. Place SDLXLIFF files in Documents, Downloads, Desktop, or Translations folders"
                )

            return [TextContent(
                type="text",
                text=json.dumps(response, indent=2, ensure_ascii=False),
            )]

        elif name == "read_sdlxliff":
            file_path = arguments["file_path"]
            include_tags = arguments.get("include_tags", False)
            offset = arguments.get("offset", 0)
            limit = arguments.get("limit")  # None means all
            logger.info(f"read_sdlxliff: file_path={file_path}, include_tags={include_tags}, offset={offset}, limit={limit}")
            logger.info(f"CWD: {os.getcwd()}")

            parser = get_parser(file_path)
            all_segments = parser.extract_segments()
            total_count = len(all_segments)
            logger.info(f"Extracted {total_count} segments")

            # Enforce maximum limit to prevent token overflow
            MAX_SEGMENTS_PER_REQUEST = 50
            if limit is None or limit > MAX_SEGMENTS_PER_REQUEST:
                limit = MAX_SEGMENTS_PER_REQUEST
                logger.info(f"Limit capped to {MAX_SEGMENTS_PER_REQUEST} segments")

            # Apply pagination
            segments = all_segments[offset:offset + limit]

            # Strip tagged fields to reduce output size
            for seg in segments:
                if not include_tags or not seg.get('has_tags', False):
                    seg.pop('source_tagged', None)
                    seg.pop('target_tagged', None)

            # Build response with pagination metadata
            response = {
                "total_segments": total_count,
                "offset": offset,
                "count": len(segments),
                "has_more": (offset + len(segments)) < total_count,
                "segments": segments,
            }

            return [
                TextContent(
                    type="text",
                    text=json.dumps(response, indent=2, ensure_ascii=False),
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
            preserve_tags = arguments.get("preserve_tags", True)

            parser = get_parser(file_path)
            result = parser.update_segment_with_tags(
                segment_id, target_text, preserve_tags=preserve_tags
            )

            if result['success']:
                response = {
                    "status": "success",
                    "message": f"Successfully updated segment '{segment_id}' (status set to RejectedTranslation). "
                               f"Remember to call save_sdlxliff to persist changes.",
                }
                if result.get('warnings'):
                    response["warnings"] = result['warnings']
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
                    )
                ]
            else:
                response = {
                    "status": "error",
                    "message": result['message'],
                }
                if result.get('validation'):
                    response["validation"] = result['validation']
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
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

        elif name == "validate_sdlxliff_segment":
            file_path = arguments["file_path"]
            segment_id = arguments["segment_id"]
            target_text = arguments["target_text"]

            parser = get_parser(file_path)
            validation = parser.validate_tagged_text(segment_id, target_text)

            # Get the original tagged text for reference
            segment = parser.get_segment_by_id(segment_id)
            if segment:
                validation['original_tagged'] = segment.get('target_tagged', '')
                validation['has_tags'] = segment.get('has_tags', False)

            return [
                TextContent(
                    type="text",
                    text=json.dumps(validation, indent=2, ensure_ascii=False),
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