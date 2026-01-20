"""
Caching and path resolution for the SDLXLIFF MCP server.

Provides:
- LRU-style parser cache with modification time validation
- Sandbox path resolution for Cowork compatibility
- File extension validation
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .constants import ALLOWED_EXTENSIONS, CACHE_MAX_SIZE

if TYPE_CHECKING:
    from .parser import SDLXLIFFParser

logger = logging.getLogger("sdlxliff-server")


@dataclass
class CachedParser:
    """Cache entry for parser with modification time tracking."""
    parser: "SDLXLIFFParser"
    mtime: float


# Module-level cache state
_parser_cache: dict[str, CachedParser] = {}
_path_resolution_cache: dict[str, Path] = {}


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


def get_parser(file_path: str) -> "SDLXLIFFParser":
    """
    Get or create a parser instance for the given file.

    Uses LRU-style caching with modification time validation to ensure
    fresh data and bounded memory usage.

    Args:
        file_path: Path to the SDLXLIFF file

    Returns:
        SDLXLIFFParser instance
    """
    # Import here to avoid circular dependency
    from .parser import SDLXLIFFParser

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
    if len(_parser_cache) >= CACHE_MAX_SIZE:
        oldest_key = next(iter(_parser_cache))
        logger.debug(f"Evicting oldest cache entry: {oldest_key}")
        _parser_cache.pop(oldest_key)

    # Create new parser and cache it
    parser = SDLXLIFFParser(normalized_path)
    _parser_cache[normalized_path] = CachedParser(parser=parser, mtime=current_mtime)

    return parser


def clear_parser_cache(file_path: Optional[str] = None) -> None:
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