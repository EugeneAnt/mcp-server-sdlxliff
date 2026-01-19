"""Manual test to verify server path resolution works."""

from pathlib import Path
import os

# Test path resolution like the server does
test_paths = [
    "sample/russian_sample.sdlxliff",  # Relative path
    "/Users/yevgeniyantonov/PycharmProjects/CCDesktopXliffTool/sample/russian_sample.sdlxliff",  # Absolute path
    "./sample/russian_sample.sdlxliff",  # Explicit relative
]

print(f"Current working directory: {os.getcwd()}\n")

for test_path in test_paths:
    print(f"Testing: {test_path}")
    resolved = str(Path(test_path).resolve())
    exists = Path(resolved).exists()
    print(f"  Resolved to: {resolved}")
    print(f"  Exists: {exists}")
    print()