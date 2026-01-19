# SDLXLIFF MCP Server

A Model Context Protocol (MCP) server that enables Claude Desktop to parse, read, and write SDLXLIFF files. This tool allows Claude to work with SDL Trados Studio translation files directly.

## Features

- **Read SDLXLIFF files**: Extract all segments with source text, target text, status, and metadata
- **Get specific segments**: Retrieve individual segments by their ID
- **Update translations**: Modify target text and status for specific segments
- **Reject segments**: Mark translations for rework with the appropriate status
- **Save changes**: Persist modifications back to SDLXLIFF files
- **Get statistics**: View translation progress and segment counts by status

## Installation

### 1. Install Dependencies

From the project directory:

```bash
# Make sure you're using Python 3.13+
python --version

# Install the project dependencies
pip install -e .
```

Or install dependencies manually:

```bash
pip install lxml mcp
```

### 2. Configure Claude Desktop

You need to add this MCP server to Claude Desktop's configuration file.

**Configuration file location on macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Add the following to your `claude_desktop_config.json`:**

```json
{
  "mcpServers": {
    "sdlxliff": {
      "command": "/Users/yevgeniyantonov/PycharmProjects/CCDesktopXliffTool/.venv/bin/python",
      "args": [
        "/Users/yevgeniyantonov/PycharmProjects/CCDesktopXliffTool/server.py"
      ]
    }
  }
}
```

**Note:** Adjust the paths above to match your actual virtual environment and project location if different.

### 3. Restart Claude Desktop

After updating the configuration, completely quit and restart Claude Desktop for the changes to take effect.

### 4. Test the Integration

Open Claude Desktop and start a new conversation. Test that the MCP server is working:

1. First, verify tools are available:
   ```
   Find all SDLXLIFF files
   ```

2. If files are found, test reading one:
   ```
   Read segments from [use the path from step 1]
   ```

3. If you encounter issues, see [DEBUGGING.md](DEBUGGING.md) for troubleshooting steps.

**Important**: The server logs all activity to `/tmp/sdlxliff_mcp_server.log`. Check this file if things aren't working.

## Available Tools

Once configured, Claude Desktop will have access to these tools:

### `find_sdlxliff_files`
Discover SDLXLIFF files in a directory. Use this when you want Claude to automatically find files.

**Parameters:**
- `directory` (string, optional): Directory to search (default: current directory)
- `recursive` (boolean, optional): Search subdirectories (default: false)

**Returns:** JSON object with:
- `directory_searched`: The directory that was searched
- `files_found`: Number of files found
- `files`: Array of file information (path, name, size)

**Example usage in Claude:**
```
Find all SDLXLIFF files in the current directory
```

### `read_sdlxliff`
Extract all translation segments from an SDLXLIFF file.

**Parameters:**
- `file_path` (string, required): Absolute path to the SDLXLIFF file

**Returns:** JSON array of segments with:
- `segment_id`: Unique segment identifier
- `source`: Source text
- `target`: Target text
- `status`: Translation status
- `locked`: Whether segment is locked

**Example usage in Claude:**
```
Please read the segments from /path/to/file.sdlxliff
```

### `get_sdlxliff_segment`
Get a specific segment by its ID.

**Parameters:**
- `file_path` (string, required): Absolute path to the SDLXLIFF file
- `segment_id` (string, required): The segment ID to retrieve

**Example usage in Claude:**
```
Get segment "123" from /path/to/file.sdlxliff
```

### `update_sdlxliff_segment`
Update a segment's target text and status.

**Parameters:**
- `file_path` (string, required): Absolute path to the SDLXLIFF file
- `segment_id` (string, required): The segment ID to update
- `target_text` (string, required): New target text
- `status` (string, optional): Status to set (default: "needs-translation")

**Common status values:**
- `translated`: Translation complete
- `needs-translation`: Needs translation or re-translation
- `needs-review-translation`: Needs review
- `final`: Approved/final
- `new`: New segment

**Example usage in Claude:**
```
Update segment "123" in /path/to/file.sdlxliff with target text "Bonjour le monde" and status "translated"
```

### `reject_sdlxliff_segment`
Mark a segment as rejected and optionally update its text.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file
- `segment_id` (string, required): The segment ID to reject
- `target_text` (string, optional): Corrected target text
- `status` (string, optional): Status to set (default: "needs-translation")

**Common status values:**
- `needs-translation`: Segment needs (re)translation
- `needs-review-translation`: Needs review
- `rejected`: Translation rejected
- Or any custom status your workflow requires

**Example usage in Claude:**
```
Reject segment "123" with corrected text "Bonjour le monde" and status "needs-translation"
```

### `save_sdlxliff`
Save changes to the SDLXLIFF file.

**Parameters:**
- `file_path` (string, required): Absolute path to the SDLXLIFF file
- `output_path` (string, optional): Alternative output path (default: overwrites original)

**Important:** Changes made with `update_sdlxliff_segment` and `reject_sdlxliff_segment` are kept in memory until you call `save_sdlxliff`.

**Example usage in Claude:**
```
Save changes to /path/to/file.sdlxliff
```

### `get_sdlxliff_statistics`
Get statistics about the translation file.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file

**Returns:** JSON object with:
- `total_segments`: Total number of segments
- `status_counts`: Count of segments by status
- `locked_count`: Number of locked segments

**Example usage in Claude:**
```
Get statistics for /path/to/file.sdlxliff
```

### `debug_sdlxliff_path`
Debug tool to troubleshoot path resolution issues.

**Parameters:**
- `file_path` (string, required): Path to check

**Returns:** JSON object with:
- `current_working_directory`: Where the MCP server is running from
- `requested_path`: The path you provided
- `resolved_path`: The absolute path after resolution
- `file_exists`: Whether the file exists at the resolved path
- `is_absolute`: Whether the requested path was absolute

**Example usage in Claude:**
```
Use debug_sdlxliff_path to check "sample/russian_sample.sdlxliff"
```

## Usage Workflow

### Example: Review and Update Translations

1. **Read the file:**
   ```
   Read all segments from /path/to/translation.sdlxliff
   ```

2. **Review specific segments:**
   ```
   Review the translations according to these instructions:
   - Check for grammar errors
   - Ensure terminology consistency
   - Verify formatting
   ```

3. **Update problematic translations:**
   ```
   Update segment "45" with corrected translation "..." and mark as translated
   ```

4. **Reject segments that need rework:**
   ```
   Reject segment "67" because it contains grammatical errors
   ```

5. **Save changes:**
   ```
   Save all changes to /path/to/translation.sdlxliff
   ```

### Example: Batch Processing with Claude Cowork

In Claude Cowork mode, you can select a folder containing multiple SDLXLIFF files and ask Claude to:

```
Review all SDLXLIFF files in this folder. For each file:
1. Read all segments
2. Check translations for [specific criteria]
3. Update any segments that need corrections
4. Save the file with changes
```

Claude will use these tools to process each file automatically.

### Example: Simple Workflow (Recommended)

This is the easiest way to use the tools:

**1. Add a directory** to Claude Cowork (e.g., your `sample/` folder)

**2. Ask Claude to review:**
```
Read the xliff file and check the translation for grammar and accuracy
```

Claude will:
- Automatically find SDLXLIFF files using `find_sdlxliff_files`
- Read segments using `read_sdlxliff`
- Analyze the translations

**3. Review Claude's findings and ask to apply changes:**
```
Update the segments with your corrections and set their status to "needs-translation"
```

Claude will:
- Update each problematic segment using `update_sdlxliff_segment` or `reject_sdlxliff_segment`
- Set status to "needs-translation" (or custom status like "rejected")
- Save the file using `save_sdlxliff`

**No need to specify file paths!** Claude figures it out from the directory context.

## Troubleshooting

### Claude Desktop doesn't show the tools

1. Check that the configuration file path is correct
2. Verify the Python path points to your virtual environment's Python
3. Verify the server.py path is correct
4. Completely quit and restart Claude Desktop (not just close the window)
5. Check Claude Desktop's logs for errors

### "File not found" or path resolution errors

If you get path resolution errors in Claude Cowork mode:

1. **Use the debug tool** to check what's happening:
   ```
   Use debug_sdlxliff_path to check the path "sample/file.sdlxliff"
   ```
   This will show you the current working directory and resolved path.

2. **Use absolute paths** when possible:
   - Instead of: `sample/file.sdlxliff`
   - Use: `/Users/yevgeniyantonov/PycharmProjects/CCDesktopXliffTool/sample/file.sdlxliff`

3. **Check the folder context**: When you add a folder to Claude Cowork, Claude should pass absolute paths to MCP tools. If it's passing relative paths, they will be resolved relative to where the MCP server process runs (not the selected folder).

### Changes aren't being saved

- Remember to call `save_sdlxliff` after making updates
- Check file permissions (the file must be writable)

### Parser errors

- Ensure the file is a valid SDLXLIFF file (not a different XLIFF variant)
- Check that the file isn't corrupted or locked by another application

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (when implemented)
pytest
```

### Project Structure

```
CCDesktopXliffTool/
├── server.py              # MCP server implementation
├── sdlxliff_parser.py     # SDLXLIFF parsing logic
├── pyproject.toml         # Project configuration
├── README.md              # This file
└── .venv/                 # Virtual environment
```

## Technical Details

### SDLXLIFF Format

SDLXLIFF is SDL's extension of the XLIFF 1.2 standard. It includes:
- Standard XLIFF elements (file, trans-unit, source, target)
- SDL-specific extensions (segment definitions, formatting, metadata)
- Multiple XML namespaces

### Parser Implementation

- Uses `lxml` for robust XML parsing
- Handles mixed content (text with inline tags)
- Preserves original formatting when saving
- Supports namespace-aware element lookup

## License

This project is provided as-is for use with Claude Desktop.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify your Claude Desktop and MCP configuration
3. Ensure your SDLXLIFF files are valid and accessible