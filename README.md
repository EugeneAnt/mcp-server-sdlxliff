# mcp-server-sdlxliff

A Model Context Protocol (MCP) server for parsing, reading, and modifying SDLXLIFF translation files. Enables Claude to review and correct SDL Trados Studio translation files directly.

## Compatibility

This MCP server works with both **Claude Cowork** and **Claude Desktop**:

| Product | Works? | Notes |
|---------|--------|-------|
| **Claude Cowork** | Yes | Primary use case. Add a folder with SDLXLIFF files and Claude can discover, read, modify, and save them. |
| **Claude Desktop** | Yes | Use `list_sdlxliff_files` to discover files, or configure search directories (see below). Resources and prompts are available. |
| **Claude.ai (web)** | No | Web interface supports connectors, but they don't provide local filesystem access. |

## Features

- **Read SDLXLIFF files** - Extract all segments with source text, target text, status, and metadata
- **Update translations** - Modify target text for specific segments (automatically sets status to `RejectedTranslation`)
- **Inline tag preservation** - Safely handle formatting tags (`<g>`, `<x>`, etc.) during translation updates
- **Pagination support** - Read large files in chunks to avoid token limits
- **Save changes** - Persist modifications back to SDLXLIFF files
- **Get statistics** - View translation progress and segment counts by status

## Installation

### Using uv (Recommended)

```bash
uv pip install mcp-server-sdlxliff
```

### Using pip

```bash
pip install mcp-server-sdlxliff
```

### From source

```bash
git clone https://github.com/EugeneAnt/mcp-server-sdlxliff.git
cd mcp-server-sdlxliff
uv pip install -e .
```

## Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

#### Basic Configuration

```json
{
  "mcpServers": {
    "sdlxliff": {
      "command": "mcp-server-sdlxliff"
    }
  }
}
```

Or if using uv:

```json
{
  "mcpServers": {
    "sdlxliff": {
      "command": "uvx",
      "args": ["mcp-server-sdlxliff"]
    }
  }
}
```

#### With Custom Search Directories (Recommended)

For Claude Desktop, configure directories where the server should look for SDLXLIFF files:

```json
{
  "mcpServers": {
    "sdlxliff": {
      "command": "mcp-server-sdlxliff",
      "args": ["-d", "/path/to/translations", "-d", "/another/path"]
    }
  }
}
```

Or using environment variables:

```json
{
  "mcpServers": {
    "sdlxliff": {
      "command": "mcp-server-sdlxliff",
      "env": {
        "SDLXLIFF_SEARCH_DIRS": "/path/to/translations:/another/path"
      }
    }
  }
}
```

**Default search directories** (used if none specified):
- `~/Documents`
- `~/Downloads`
- `~/Desktop`
- `~/Translations`

### Claude Cowork

Add a folder containing your SDLXLIFF files to Claude Cowork and the MCP tools will be available automatically.

### Command-Line Options

```
mcp-server-sdlxliff [-d DIRECTORY] ...

Options:
  -d, --directory PATH    Directory to search for SDLXLIFF files.
                          Can be specified multiple times.

Environment Variables:
  SDLXLIFF_SEARCH_DIRS    Colon-separated (Unix) or semicolon-separated (Windows)
                          list of directories to search.
```

## Available Tools

### `list_sdlxliff_files`

Discover and list SDLXLIFF files in configured directories. **Use this first in Claude Desktop** to find available translation files.

**Parameters:**
- `directory` (string, optional): Specific directory to search. If not provided, searches all configured directories.
- `max_results` (integer, optional): Maximum number of files to return (default: 50, max: 100)

**Returns:** JSON object with:
- `searched_directories`: List of directories that were searched
- `files_found`: Number of files found
- `files`: Array of file information (path, name, size, modified date, directory)

**Example response:**
```json
{
  "searched_directories": ["/Users/me/Documents", "/Users/me/Downloads"],
  "files_found": 2,
  "files": [
    {
      "path": "/Users/me/Documents/project/file.sdlxliff",
      "name": "file.sdlxliff",
      "size": 125000,
      "modified": "2025-01-15T10:30:00",
      "directory": "/Users/me/Documents/project"
    }
  ]
}
```

### `read_sdlxliff`

Extract translation segments from an SDLXLIFF file.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file
- `offset` (integer, optional): Starting segment index for pagination (default: 0)
- `limit` (integer, optional): Maximum segments to return (default: all). Use 50 for large files.
- `include_tags` (boolean, optional): Include tagged text fields for segments with formatting tags (default: false)

**Returns:** JSON object with pagination metadata and segments:
```json
{
  "total_segments": 184,
  "offset": 0,
  "count": 50,
  "has_more": true,
  "segments": [...]
}
```

Each segment contains:
- `segment_id`: Unique segment identifier (mrk mid)
- `trans_unit_id`: Parent trans-unit ID
- `source`: Source text (clean, without tags)
- `target`: Target text (clean, without tags)
- `has_tags`: Whether segment contains inline formatting tags
- `source_tagged`: Source with tag placeholders (only if `has_tags=true` and `include_tags=true`)
- `target_tagged`: Target with tag placeholders (only if `has_tags=true` and `include_tags=true`)
- `status`: SDL confirmation level (e.g., `Translated`, `RejectedTranslation`)
- `locked`: Whether segment is locked

### `get_sdlxliff_segment`

Get a specific segment by its ID.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file
- `segment_id` (string, required): The segment ID (mrk mid) to retrieve

### `update_sdlxliff_segment`

Update a segment's target text. Automatically sets status to `RejectedTranslation`.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file
- `segment_id` (string, required): The segment ID (mrk mid) to update
- `target_text` (string, required): New target text. For segments with tags, include placeholders.
- `preserve_tags` (boolean, optional): Validate and restore tags from placeholders (default: true)

**Note:** Changes are kept in memory until `save_sdlxliff` is called. For segments with formatting tags (`has_tags=true`), you must include tag placeholders in the target text. See [Tag Handling](#tag-handling) below.

### `validate_sdlxliff_segment`

Pre-validate proposed changes to a segment before updating.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file
- `segment_id` (string, required): The segment ID to validate against
- `target_text` (string, required): Proposed target text with tag placeholders

**Returns:** Validation result with errors, warnings, and missing/extra tag information.

### `save_sdlxliff`

Save changes to the SDLXLIFF file.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file
- `output_path` (string, optional): Alternative output path (default: overwrites original)

### `get_sdlxliff_statistics`

Get statistics about the translation file.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file

**Returns:** JSON object with:
- `total_segments`: Total number of segments
- `status_counts`: Count of segments by SDL confirmation level
- `locked_count`: Number of locked segments

## MCP Prompts

The server provides built-in prompts for common workflows. In Claude Desktop, these appear as slash commands:

### `/find-sdlxliff`
Find SDLXLIFF files on your computer. Useful when you don't know where your files are located.

### `/review-translations`
Review translations in an SDLXLIFF file for quality issues. Supports focusing on:
- `grammar` - Grammar and spelling errors
- `terminology` - Consistent use of terms
- `consistency` - Consistency between similar phrases
- `all` - All of the above (default)

### `/translation-status`
Get a summary of translation progress for an SDLXLIFF file.

## Usage Examples

### Claude Desktop

**Find your SDLXLIFF files:**
```
Find SDLXLIFF files on my computer
```
Claude will use `list_sdlxliff_files` to discover available files.

**Review a specific file:**
```
Review the translations in /path/to/file.sdlxliff for grammar issues
```

**Using prompts:**
```
/find-sdlxliff
/review-translations file_path=/path/to/file.sdlxliff focus=grammar
/translation-status file_path=/path/to/file.sdlxliff
```

### Claude Cowork

In Cowork, simply add a folder containing your SDLXLIFF files and ask:
```
Read the SDLXLIFF file and check the translations for grammar errors
```

### Workflow

Claude will:
1. Use `list_sdlxliff_files` to discover files (or you provide a path)
2. Use `get_sdlxliff_statistics` to understand the file
3. Use `read_sdlxliff` to extract segments (with pagination for large files)
4. Analyze translations for issues
5. Use `update_sdlxliff_segment` to correct problematic segments
6. Use `save_sdlxliff` to persist changes

## SDLXLIFF Format

SDLXLIFF is SDL's extension of the XLIFF 1.2 standard, used by SDL Trados Studio. Key characteristics:

- Each `<mrk mtype="seg">` element is a separate translatable segment
- Segment IDs are the `mid` attribute values (globally unique numbers)
- Status is stored in `<sdl:seg conf="...">` (not the XLIFF `state` attribute)
- Valid SDL confirmation levels: `Draft`, `Translated`, `RejectedTranslation`, `ApprovedTranslation`, `RejectedSignOff`, `ApprovedSignOff`

## Tag Handling

SDLXLIFF files often contain inline formatting tags (`<g>`, `<x>`, `<bpt>`, `<ept>`, etc.) that control bold, italic, colors, line breaks, and other formatting in the final document. **These tags must be preserved during translation updates** or the formatting will be lost.

### How It Works

The MCP server converts XML tags to readable placeholders:

| XML Tag | Placeholder | Description |
|---------|-------------|-------------|
| `<g id="5">text</g>` | `{5}text{/5}` | Paired formatting tag |
| `<x id="5"/>` | `{x:5}` | Self-closing tag (e.g., line break) |
| `<bpt id="5">` | `{5}` | Begin paired tag |
| `<ept id="5">` | `{/5}` | End paired tag |

### Example

**Original XML:**
```xml
<mrk mid="3"><g id="5">Acme</g><g id="6">&amp;</g><g id="7"> Events</g></mrk>
```

**Extracted as:**
```json
{
  "source": "Acme& Events",
  "source_tagged": "{5}Acme{/5}{6}&{/6}{7} Events{/7}",
  "has_tags": true
}
```

**To update this segment**, you must include all tags:
```
{5}Acme{/5}{6}&{/6}{7} Мероприятия{/7}
```

### Validation Rules

When updating segments with tags:

1. **All original tags must be present** - Missing tags will cause the update to be rejected
2. **No extra tags allowed** - Only tags from the original segment can be used
3. **Tags must be properly paired** - Opening `{5}` must have matching `{/5}`
4. **Tag order can change** - Word order differences between languages are allowed (with a warning)

### Workflow for Tagged Segments

1. Read segments with `read_sdlxliff` - check `has_tags` field
2. For segments with `has_tags=true`, use `get_sdlxliff_segment` to get the `source_tagged`/`target_tagged` fields
3. Include all placeholders when calling `update_sdlxliff_segment`
4. If validation fails, the error message shows which tags are missing

## Development

```bash
# Clone the repository
git clone https://github.com/EugeneAnt/mcp-server-sdlxliff.git
cd mcp-server-sdlxliff

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.