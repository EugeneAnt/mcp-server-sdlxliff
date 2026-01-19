"""Test the MCP server functions directly."""

import os
import sys
from pathlib import Path

# Add the current directory to path so we can import server modules
sys.path.insert(0, str(Path(__file__).parent))

# Import the server functions
from server import find_all_sdlxliff_files, get_parser

print("=" * 60)
print("Testing MCP Server Functions")
print("=" * 60)

# Test 1: Check current working directory
print(f"\n1. Current Working Directory: {os.getcwd()}")

# Test 2: Find SDLXLIFF files
print(f"\n2. Finding SDLXLIFF files...")
files = find_all_sdlxliff_files()
print(f"   Found {len(files)} files:")
for f in files:
    print(f"     - {f}")

# Test 3: Try to read a file if found
if files:
    print(f"\n3. Reading first file: {files[0]}")
    try:
        parser = get_parser(str(files[0]))
        segments = parser.extract_segments()
        print(f"   Successfully read {len(segments)} segments")
        print(f"   First segment ID: {segments[0]['segment_id']}")
        print(f"   First segment source (truncated): {segments[0]['source'][:80]}...")
    except Exception as e:
        print(f"   Error: {e}")
else:
    print(f"\n3. No files found to read")

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)