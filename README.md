# mcp-server-sdlxliff

A Model Context Protocol (MCP) server for parsing, reading, and modifying SDLXLIFF translation files. Enables AI assistants like Claude to work directly with SDL Trados Studio translation files.

## Features

- **Read SDLXLIFF files** - Extract all segments with source text, target text, status, and metadata
- **Update translations** - Modify target text for specific segments (automatically sets status to `RejectedTranslation`)
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

### Claude Cowork

Add a folder containing your SDLXLIFF files to Claude Cowork and the MCP tools will be available automatically.

## Available Tools

### `read_sdlxliff`

Extract all translation segments from an SDLXLIFF file.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file

**Returns:** JSON array of segments with:
- `segment_id`: Unique segment identifier (mrk mid)
- `trans_unit_id`: Parent trans-unit ID
- `source`: Source text
- `target`: Target text
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
- `target_text` (string, required): New target text

**Note:** Changes are kept in memory until `save_sdlxliff` is called.

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

## Usage Example

In Claude Desktop or Claude Cowork:

```
Read the SDLXLIFF file and check the translations for grammar errors
```

Claude will:
1. Use `read_sdlxliff` to extract all segments
2. Analyze translations for issues
3. Use `update_sdlxliff_segment` to correct problematic segments
4. Use `save_sdlxliff` to persist changes

## SDLXLIFF Format

SDLXLIFF is SDL's extension of the XLIFF 1.2 standard, used by SDL Trados Studio. Key characteristics:

- Each `<mrk mtype="seg">` element is a separate translatable segment
- Segment IDs are the `mid` attribute values (globally unique numbers)
- Status is stored in `<sdl:seg conf="...">` (not the XLIFF `state` attribute)
- Valid SDL confirmation levels: `Draft`, `Translated`, `RejectedTranslation`, `ApprovedTranslation`, `RejectedSignOff`, `ApprovedSignOff`

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