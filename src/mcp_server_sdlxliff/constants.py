"""
Constants and configuration values for the SDLXLIFF MCP server.

Centralizes all magic numbers and configuration constants.
"""

# File size limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB - SDLXLIFF files are typically much smaller
MAX_SEGMENT_TEXT_SIZE = 100 * 1024  # 100KB - segments are typically much smaller

# Allowed file extensions
ALLOWED_EXTENSIONS = frozenset({'.sdlxliff'})

# Cache configuration
CACHE_MAX_SIZE = 10  # Maximum number of cached parsers

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