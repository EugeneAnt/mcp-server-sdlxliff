# mcp-server-sdlxliff

**Chat with your SDL Trados translation files using Claude.**

Review translations, find errors, and make corrections through simple natural conversation - no manual XML editing required.

## Two Ways to Use

| Option | Best For | Claude Access |
|--------|----------|---------------|
| **[XLIFF Chat Desktop App](#xliff-chat-desktop-app)** | Professional users who want a dedicated app | API key (pay per use) |
| **[Claude Desktop Extension](#claude-desktop-extension)** | Claude Pro/Team subscribers | Claude subscription |

Both options use the same MCP server under the hood - choose based on how you prefer to access Claude.

## What You Can Do

Just ask Claude in plain language:

- *"Check this file for grammar errors in the Russian translations"*
- *"Find segments where the translation is much longer than the source"*
- *"Fix segment 42 - change 'программа' to 'приложение'"*
- *"Show me all segments that are still in Draft status"*
- *"Run QA checks with my glossary"*
- *"Save my changes"*

Claude reads your SDLXLIFF files, understands the translation context, and can make corrections while preserving all formatting tags automatically.

## XLIFF Chat Desktop App

A standalone macOS app with a native file picker - no command line required.

### Installation

1. Install the MCP server **globally** (not in a virtual environment):
   ```bash
   pip3 install mcp-server-sdlxliff
   ```

   > **Note:** The desktop app looks for Python at `/opt/homebrew/bin/python3` (Apple Silicon) or `/usr/local/bin/python3` (Intel Mac). Make sure to install with the same `pip3` that corresponds to your Homebrew Python.

2. Download `XLIFF.Chat-1.0.0.dmg` from [Releases](https://github.com/EugeneAnt/mcp-server-sdlxliff/releases)

3. Open the `.dmg` and drag XLIFF Chat to your Applications folder

4. Launch XLIFF Chat and enter your [Anthropic API key](https://console.anthropic.com/)

### Usage

1. Click **File** or **Folder** button to select SDLXLIFF files
2. The MCP server connects automatically
3. Start chatting - ask Claude to review, check, or edit your translations

### Requirements

- macOS 10.15 or later
- Python 3.10+ with `mcp-server-sdlxliff` installed globally
- Anthropic API key

## Claude Desktop Extension

Use with your Claude Pro or Team subscription through Claude Cowork.

### Installation

**Option A: Desktop Extension (Recommended)**

1. Download `mcp-server-sdlxliff-1.0.0.mcpb` from [Releases](https://github.com/EugeneAnt/mcp-server-sdlxliff/releases)
2. Open Claude Desktop → Settings → Extensions
3. Click "Install Extension" and select the downloaded `.mcpb` file
4. The extension installs automatically (Python and dependencies are managed for you)

**Option B: Manual Installation**

```bash
pip install mcp-server-sdlxliff
```

Then add to your `claude_desktop_config.json`:

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

### Usage with Claude Cowork

1. Open Claude Cowork
2. Click "+ Add folder" and select a folder containing your SDLXLIFF files
3. The MCP tools will be available automatically
4. Ask Claude to review or edit translations

### Compatibility

| Product | Works? | Notes |
|---------|--------|-------|
| **Claude Cowork** | Yes | Add a folder with SDLXLIFF files and start chatting |
| **Claude Desktop (chat)** | No | [Sandbox limitation](#claude-desktop-chat-limitation) prevents file access |
| **Claude.ai (web)** | No | No local filesystem access |

## Features

- **Natural conversation** - Ask questions and request changes in plain language
- **Error detection** - Find grammar, spelling, consistency, and terminology issues
- **QA checks** - Automated quality assurance with glossary support
- **Safe corrections** - Edit translations while preserving all formatting tags
- **Batch review** - Process large files with automatic pagination
- **Change tracking** - Modified segments are marked as `RejectedTranslation` for easy review in Trados

## Human in the Loop

Claude's corrections are **suggestions, not final changes**. The workflow keeps you in control:

1. Claude marks all modified segments as `RejectedTranslation`
2. Open the file in SDL Trados Studio
3. Filter by status → `RejectedTranslation` to see only Claude's changes
4. Review each suggestion and **Confirm** or **Edit** as needed
5. Your approved changes become `Translated` or `ApprovedTranslation`

This ensures human oversight - you always have the final say on what goes into the translation.

## Available Tools

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
- `repetitions`: Number of times this source text appears in the file (only present when > 1)

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

### `qa_check_sdlxliff`

Run quality assurance checks on the translation file.

**Parameters:**
- `file_path` (string, required): Path to the SDLXLIFF file
- `segment_ids` (array of strings, optional): Specific segment IDs to check. If omitted, checks all segments.
- `checks` (array of strings, optional): Specific checks to run. If omitted, runs all checks.
- `glossary_path` (string, optional): Path to glossary file for terminology check. If omitted, auto-discovers `glossary.tsv`, `glossary.txt`, `terminology.tsv`, or `terminology.txt` in the same directory as the SDLXLIFF file.

**Available checks:**
| Check | Description |
|-------|-------------|
| `trailing_punctuation` | Source ends with `.!?:;` but target doesn't (or vice versa) |
| `numbers` | Numbers in source don't match numbers in target |
| `double_spaces` | Target contains consecutive spaces |
| `whitespace` | Leading/trailing whitespace mismatch between source and target |
| `brackets` | Different count of `()[]{}` between source and target |
| `inconsistent_repetitions` | Segments with same source text have different translations |
| `terminology` | Glossary terms from source must appear in target (requires glossary file) |

**Glossary file format:**
```
# Comment lines start with #
# Format: source_term<TAB>target_term
Galaxy	Galaxy
Settings	Настройки
Smart Switch	Smart Switch
```

Single terms (without tab) mean the term must appear unchanged in the target.

**Returns:** JSON object with:
```json
{
  "total_segments": 184,
  "segments_checked": 184,
  "segments_with_issues": 12,
  "glossary_used": "/path/to/glossary.tsv",
  "glossary_terms_count": 5,
  "issues": [
    {
      "segment_id": "42",
      "check": "trailing_punctuation",
      "severity": "warning",
      "message": "Source ends with '.' but target does not",
      "source_excerpt": "...end of sentence.",
      "target_excerpt": "...end of sentence"
    }
  ],
  "summary": {
    "trailing_punctuation": 5,
    "numbers": 3,
    "double_spaces": 2,
    "whitespace": 1,
    "brackets": 1,
    "terminology": 2
  }
}
```

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

## Claude Desktop Chat Limitation

Claude Desktop Chat runs Claude in a **gVisor sandboxed container** for security. When you attach files via "+ Add files", they are uploaded to `/mnt/user-data/uploads/` inside this container.

**The problem:** MCP servers run on your **host machine**, not inside the container. They cannot access the sandboxed filesystem where attached files are stored.

```
┌─────────────────────────────────────────┐
│          gVisor Container               │
│  ┌─────────────────────────────────┐    │
│  │  /mnt/user-data/uploads/        │    │
│  │    └── your_file.sdlxliff       │ ←── File uploaded here
│  └─────────────────────────────────┘    │
│              Claude                      │
└─────────────────────────────────────────┘
           ╳ No access ╳
┌─────────────────────────────────────────┐
│           Host Machine                   │
│  ┌─────────────────────────────────┐    │
│  │      MCP Server (sdlxliff)      │ ←── Cannot read container filesystem
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

**Workaround:** Use **Claude Cowork** or **XLIFF Chat** instead, which have direct access to your local files.

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

### Building the Desktop Extension

To create a `.mcpb` bundle for distribution:

```bash
# Install the MCPB CLI
npm install -g @anthropic-ai/mcpb

# Validate the manifest
mcpb validate manifest.json

# Create the bundle
mcpb pack .
```

This creates `mcp-server-sdlxliff-X.X.X.mcpb` ready for installation in Claude Desktop.

### Building the Desktop App

```bash
cd desktop

# Install dependencies
bun install

# Build for macOS
bun run tauri build
```

This creates `XLIFF Chat.dmg` in `desktop/src-tauri/target/release/bundle/dmg/`.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.