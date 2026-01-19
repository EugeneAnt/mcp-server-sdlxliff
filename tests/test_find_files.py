"""Test the file finding functionality."""

from pathlib import Path

# Test finding SDLXLIFF files
directory = "sample"
dir_path = Path(directory).resolve()

print(f"Searching in: {dir_path}")
print(f"Directory exists: {dir_path.exists()}")
print(f"Is directory: {dir_path.is_dir()}")
print()

# Find files
files = list(dir_path.glob("*.sdlxliff"))
print(f"Files found: {len(files)}")

for file in files:
    print(f"  - {file.name} ({file.stat().st_size} bytes)")
    print(f"    Full path: {file}")