"""Quick test of the SDLXLIFF parser with the sample file."""

from sdlxliff_parser import SDLXLIFFParser
import json

# Test with sample file
sample_file = "sample/russian_sample.sdlxliff"

print("Testing SDLXLIFF Parser...")
print(f"Loading file: {sample_file}\n")

parser = SDLXLIFFParser(sample_file)

# Get statistics
print("File Statistics:")
stats = parser.get_statistics()
print(json.dumps(stats, indent=2))
print()

# Get first few segments
print("First 5 segments:")
segments = parser.extract_segments()
for segment in segments[:5]:
    print(f"\nSegment ID: {segment['segment_id']}")
    print(f"  Source: {segment['source'][:100]}...")  # First 100 chars
    print(f"  Target: {segment['target'][:100] if segment['target'] else '(empty)'}...")
    print(f"  Status: {segment['status']}")
    print(f"  Locked: {segment['locked']}")

print(f"\n\nTotal segments extracted: {len(segments)}")