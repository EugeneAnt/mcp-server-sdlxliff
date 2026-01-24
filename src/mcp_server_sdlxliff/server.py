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
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent, Resource
from mcp.server.stdio import stdio_server
import logging

from .cache import (
    get_parser,
    clear_parser_cache,
    validate_file_extension,
)
from .qa import run_qa_checks, QAReport, load_glossary, discover_glossary


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
                    "max_percent": {
                        "type": "integer",
                        "description": (
                            "Filter to exclude high-match segments. Only returns segments with "
                            "match percent <= this value (or no percent). "
                            "Example: max_percent=99 excludes 100% TM matches. "
                            "Use when client requests not to touch pre-translated/approved 100% segments. "
                            "Default: no filtering (returns all segments)."
                        ),
                    },
                    "skip_cm": {
                        "type": "boolean",
                        "description": (
                            "Skip Context Matches (CM). CMs are 100% matches where both source, "
                            "target AND surrounding context match the TM. "
                            "Use when client says 'skip CMs' or 'don't touch context matches'. "
                            "Default: false."
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
        Tool(
            name="qa_check_sdlxliff",
            description=(
                "Run quality assurance checks on an SDLXLIFF file. "
                "ALWAYS use this tool (not custom scripts) for QA tasks. "
                "Checks include: trailing punctuation mismatches, missing/extra numbers, "
                "double spaces, whitespace mismatches, bracket mismatches, "
                "inconsistent repetitions (same source text translated differently), "
                "and terminology (glossary compliance). "
                "For terminology check: auto-discovers glossary.tsv/txt in same folder as SDLXLIFF, "
                "or specify explicit glossary_path. "
                "Use for: 'check translation quality', 'find errors', 'are translations consistent', "
                "'run QA', 'verify before delivery', 'check terminology', 'verify glossary'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the SDLXLIFF file",
                    },
                    "segment_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of segment IDs to check. "
                            "If not provided, checks all segments."
                        ),
                    },
                    "checks": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "trailing_punctuation",
                                "numbers",
                                "double_spaces",
                                "whitespace",
                                "brackets",
                                "inconsistent_repetitions",
                                "terminology",
                            ],
                        },
                        "description": (
                            "Optional list of specific checks to run. "
                            "If not provided, runs all checks. "
                            "Available: trailing_punctuation, numbers, double_spaces, "
                            "whitespace, brackets, inconsistent_repetitions, terminology."
                        ),
                    },
                    "glossary_path": {
                        "type": "string",
                        "description": (
                            "Optional path to glossary file (tab-delimited: source_term<TAB>target_term). "
                            "If not provided, auto-discovers glossary.tsv/glossary.txt/terminology.tsv/terminology.txt "
                            "in same directory as SDLXLIFF file."
                        ),
                    },
                    "max_percent": {
                        "type": "integer",
                        "description": (
                            "Filter to exclude high-match segments from QA. Only checks segments with "
                            "match percent <= this value (or no percent). "
                            "Example: max_percent=99 skips QA on 100% TM matches. "
                            "Use when client requests not to touch pre-translated segments."
                        ),
                    },
                    "skip_cm": {
                        "type": "boolean",
                        "description": (
                            "Skip Context Matches (CM) from QA. CMs are 100% matches where both source, "
                            "target AND surrounding context match the TM. "
                            "Use when client says 'skip CMs' or 'don't touch context matches'. "
                            "Default: false."
                        ),
                        "default": False,
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
            include_tags = arguments.get("include_tags", False)
            offset = arguments.get("offset", 0)
            limit = arguments.get("limit")  # None means all
            max_percent = arguments.get("max_percent")  # None means no filtering
            skip_cm = arguments.get("skip_cm", False)  # Skip Context Matches
            logger.info(f"read_sdlxliff: file_path={file_path}, include_tags={include_tags}, offset={offset}, limit={limit}, max_percent={max_percent}, skip_cm={skip_cm}")
            logger.info(f"CWD: {os.getcwd()}")

            parser = get_parser(file_path)
            all_segments = parser.extract_segments()
            total_count = len(all_segments)

            # Apply percent filter if specified
            if max_percent is not None:
                all_segments = [
                    seg for seg in all_segments
                    if seg.get('percent') is None or seg.get('percent') <= max_percent
                ]
                logger.info(f"After max_percent={max_percent} filter: {len(all_segments)} segments (was {total_count})")

            # Apply CM filter if specified (text_match="SourceAndTarget" indicates CM)
            if skip_cm:
                all_segments = [
                    seg for seg in all_segments
                    if seg.get('text_match') != 'SourceAndTarget'
                ]
                logger.info(f"After skip_cm filter: {len(all_segments)} segments")
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
            filtered_count = len(all_segments) if max_percent is not None else total_count
            response = {
                "total_segments": total_count,
                "filtered_segments": filtered_count if max_percent is not None else None,
                "offset": offset,
                "count": len(segments),
                "has_more": (offset + len(segments)) < filtered_count,
                "segments": segments,
            }
            # Remove null fields to save tokens
            response = {k: v for k, v in response.items() if v is not None}

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

            # Strip tagged fields if segment has no tags (saves tokens)
            if not segment.get('has_tags', False):
                segment.pop('source_tagged', None)
                segment.pop('target_tagged', None)

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

        elif name == "qa_check_sdlxliff":
            file_path = arguments["file_path"]
            segment_ids = arguments.get("segment_ids")
            checks = arguments.get("checks")
            glossary_path = arguments.get("glossary_path")
            max_percent = arguments.get("max_percent")
            skip_cm = arguments.get("skip_cm", False)

            parser = get_parser(file_path)
            all_segments = parser.extract_segments()
            total_count = len(all_segments)

            # Apply percent filter if specified
            if max_percent is not None:
                all_segments = [
                    seg for seg in all_segments
                    if seg.get('percent') is None or seg.get('percent') <= max_percent
                ]
                logger.info(f"QA: After max_percent={max_percent} filter: {len(all_segments)} segments (was {total_count})")

            # Apply CM filter if specified
            if skip_cm:
                all_segments = [
                    seg for seg in all_segments
                    if seg.get('text_match') != 'SourceAndTarget'
                ]
                logger.info(f"QA: After skip_cm filter: {len(all_segments)} segments")

            # Filter segments if specific IDs provided
            if segment_ids:
                segment_id_set = set(segment_ids)
                segments_to_check = [
                    s for s in all_segments
                    if s['segment_id'] in segment_id_set
                ]
            else:
                segments_to_check = all_segments

            # Load glossary for terminology check
            glossary_terms = None
            used_glossary_path = None

            # If glossary_path provided, use it; otherwise auto-discover
            if glossary_path:
                glossary_terms = load_glossary(glossary_path)
                if glossary_terms:
                    used_glossary_path = glossary_path
            else:
                discovered = discover_glossary(file_path)
                if discovered:
                    glossary_terms = load_glossary(discovered)
                    if glossary_terms:
                        used_glossary_path = discovered

            # Run QA checks with glossary terms
            report = run_qa_checks(segments_to_check, checks, glossary_terms)

            # Convert to JSON-serializable format
            response = {
                "total_segments": total_count,
                "segments_checked": report.segments_checked,
                "segments_with_issues": report.segments_with_issues,
                "issues": [
                    {
                        "segment_id": issue.segment_id,
                        "check": issue.check,
                        "severity": issue.severity,
                        "message": issue.message,
                        "source_excerpt": issue.source_excerpt,
                        "target_excerpt": issue.target_excerpt,
                    }
                    for issue in report.issues
                ],
                "summary": report.summary,
            }

            # Add filter info if applied
            if max_percent is not None or skip_cm:
                response["segments_excluded"] = total_count - len(all_segments)
                if max_percent is not None:
                    response["filtered_by_max_percent"] = max_percent
                if skip_cm:
                    response["skipped_context_matches"] = True

            # Add glossary info to response
            if used_glossary_path:
                response["glossary_used"] = used_glossary_path
                response["glossary_terms_count"] = len(glossary_terms) if glossary_terms else 0

            return [
                TextContent(
                    type="text",
                    text=json.dumps(response, indent=2, ensure_ascii=False),
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