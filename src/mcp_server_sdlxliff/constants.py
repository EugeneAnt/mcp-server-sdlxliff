"""
Constants and configuration values for the SDLXLIFF MCP server.

Centralizes all magic numbers and configuration constants.
"""

from pathlib import Path

# File size limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB - SDLXLIFF files are typically much smaller
MAX_SEGMENT_TEXT_SIZE = 100 * 1024  # 100KB - segments are typically much smaller

# Allowed file extensions
ALLOWED_EXTENSIONS = frozenset({'.sdlxliff'})

# Cache configuration
CACHE_MAX_SIZE = 10  # Maximum number of cached parsers

# Default search directories for file discovery (Claude Desktop mode)
def get_default_search_directories() -> list[Path]:
    """Get default directories to search for SDLXLIFF files."""
    home = Path.home()
    candidates = [
        home / "Documents",
        home / "Downloads",
        home / "Desktop",
        home / "Translations",  # Common folder for translators
    ]
    # Only return directories that exist
    return [d for d in candidates if d.exists() and d.is_dir()]

# Maximum depth for recursive file search
MAX_SEARCH_DEPTH = 5

# Maximum number of files to return in list_sdlxliff_files
MAX_FILES_TO_LIST = 100

# Default XML namespaces for SDLXLIFF files
DEFAULT_NAMESPACES = {
    'xliff': 'urn:oasis:names:tc:xliff:document:1.2',
    'sdl': 'http://sdl.com/FileTypes/SdlXliff/1.0',
}

# Inline tag element names that contain formatting
INLINE_TAG_NAMES = frozenset({'g', 'x', 'bx', 'ex', 'ph', 'bpt', 'ept', 'it'})

# Self-closing inline tag names
SELF_CLOSING_TAG_NAMES = frozenset({'x', 'bx', 'ex', 'ph'})

# SDL confirmation levels (valid status values)
SDL_CONFIRMATION_LEVELS = frozenset({
    'Draft',
    'Translated',
    'RejectedTranslation',
    'ApprovedTranslation',
    'RejectedSignOff',
    'ApprovedSignOff',
})