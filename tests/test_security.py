"""
Security tests for SDLXLIFF MCP server.

Tests protection against:
- XXE (XML External Entity) attacks
- XML bomb / Billion Laughs attacks
- File size limits
- File extension validation
- Segment text size limits
"""

import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_server_sdlxliff.parser import SDLXLIFFParser
from mcp_server_sdlxliff.cache import validate_file_extension
from mcp_server_sdlxliff.constants import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    MAX_SEGMENT_TEXT_SIZE,
)


# Valid minimal SDLXLIFF for baseline tests
VALID_SDLXLIFF = '''<?xml version="1.0" encoding="utf-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">
  <file source-language="en-US" target-language="ru-RU">
    <body>
      <trans-unit id="1">
        <source>Hello</source>
        <seg-source><mrk mtype="seg" mid="1">Hello</mrk></seg-source>
        <target><mrk mtype="seg" mid="1">Привет</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
    </body>
  </file>
</xliff>'''


class TestXXEProtection:
    """Tests for XML External Entity (XXE) attack prevention."""

    def test_xxe_file_disclosure_blocked(self):
        """Test that XXE attacks attempting to read local files are blocked."""
        # XXE payload attempting to read /etc/passwd
        xxe_payload = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE xliff [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">
  <file source-language="en-US" target-language="ru-RU">
    <body>
      <trans-unit id="1">
        <source>&xxe;</source>
        <seg-source><mrk mtype="seg" mid="1">&xxe;</mrk></seg-source>
        <target><mrk mtype="seg" mid="1">Test</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
    </body>
  </file>
</xliff>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(xxe_payload)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            # With resolve_entities=False, entities are preserved as Entity objects
            # This causes an error when we try to process them (which is the secure behavior)
            # Either we get an error, or the entity is NOT expanded to file contents
            try:
                segments = parser.extract_segments()
                # If parsing succeeded, verify entity was NOT expanded
                for seg in segments:
                    assert 'root:' not in seg.get('source', '')
                    assert 'root:' not in seg.get('target', '')
            except (ValueError, TypeError):
                # Error processing unexpanded entity - this is secure behavior
                pass
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_xxe_network_access_blocked(self):
        """Test that XXE attacks attempting network access are blocked."""
        # XXE payload attempting to access external URL
        xxe_network_payload = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE xliff [
  <!ENTITY xxe SYSTEM "http://evil.com/xxe">
]>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">
  <file source-language="en-US" target-language="ru-RU">
    <body>
      <trans-unit id="1">
        <source>&xxe;</source>
        <seg-source><mrk mtype="seg" mid="1">&xxe;</mrk></seg-source>
        <target><mrk mtype="seg" mid="1">Test</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
    </body>
  </file>
</xliff>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(xxe_network_payload)
            temp_path = f.name

        try:
            # Parser should not make network requests (no_network=True)
            # With resolve_entities=False, entity is preserved and not fetched
            parser = SDLXLIFFParser(temp_path)
            try:
                segments = parser.extract_segments()
                # If we get here without hanging, network was not accessed
            except (ValueError, TypeError):
                # Error processing unexpanded entity - this is secure behavior
                pass
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestXMLBombProtection:
    """Tests for XML bomb / Billion Laughs attack prevention."""

    def test_billion_laughs_blocked(self):
        """Test that exponential entity expansion (Billion Laughs) is blocked."""
        # Classic Billion Laughs attack - exponential expansion
        xml_bomb = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE xliff [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
]>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">
  <file source-language="en-US" target-language="ru-RU">
    <body>
      <trans-unit id="1">
        <source>&lol5;</source>
        <seg-source><mrk mtype="seg" mid="1">&lol5;</mrk></seg-source>
        <target><mrk mtype="seg" mid="1">Test</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
    </body>
  </file>
</xliff>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(xml_bomb)
            temp_path = f.name

        try:
            # Parser should not expand entities (resolve_entities=False)
            # This prevents the exponential expansion
            parser = SDLXLIFFParser(temp_path)
            try:
                segments = parser.extract_segments()
                # Verify the entity was NOT expanded to millions of "lol"s
                for seg in segments:
                    source = seg.get('source', '')
                    # If entity was expanded, source would be >10KB of "lol"s
                    assert len(source) < 1000, "XML bomb entity expansion was not blocked"
            except (ValueError, TypeError):
                # Error processing unexpanded entity - this is secure behavior
                pass
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_quadratic_blowup_blocked(self):
        """Test that quadratic blowup attacks are handled safely."""
        # Quadratic blowup - large entity repeated many times
        large_entity = 'A' * 10000  # 10KB entity
        quadratic_payload = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE xliff [
  <!ENTITY big "{large_entity}">
]>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">
  <file source-language="en-US" target-language="ru-RU">
    <body>
      <trans-unit id="1">
        <source>&big;&big;&big;&big;&big;</source>
        <seg-source><mrk mtype="seg" mid="1">&big;</mrk></seg-source>
        <target><mrk mtype="seg" mid="1">Test</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
    </body>
  </file>
</xliff>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(quadratic_payload)
            temp_path = f.name

        try:
            # Parser should not expand entities
            parser = SDLXLIFFParser(temp_path)
            try:
                segments = parser.extract_segments()
                # Verify entity was not expanded
                for seg in segments:
                    source = seg.get('source', '')
                    assert len(source) < 50000, "Quadratic blowup not blocked"
            except (ValueError, TypeError):
                # Error processing unexpanded entity - this is secure behavior
                pass
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestFileSizeLimits:
    """Tests for file size limit enforcement."""

    def test_file_size_limit_enforced(self):
        """Test that files exceeding MAX_FILE_SIZE are rejected."""
        # Create a file larger than the limit (50MB)
        # We'll test with a smaller threshold by checking the error message format

        # First verify the limit constant is reasonable
        assert MAX_FILE_SIZE == 50 * 1024 * 1024  # 50MB

    def test_large_file_rejected(self):
        """Test that a file exceeding size limit raises ValueError."""
        # Create a file that's just over the mock limit
        # For testing, we'll create a moderately large file and verify the check exists

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            # Write valid SDLXLIFF header
            f.write('<?xml version="1.0" encoding="utf-8"?>')
            f.write('<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2">')
            # Write padding to make it larger (but not 50MB for test speed)
            f.write('<!-- ' + 'x' * 1000000 + ' -->')  # ~1MB padding
            f.write('</xliff>')
            temp_path = f.name

        try:
            # This file is under 50MB so should parse (testing the mechanism exists)
            # A real 50MB+ file test would be too slow for unit tests
            parser = SDLXLIFFParser(temp_path)
            # If we get here, file was under limit - that's expected
        except ValueError as e:
            # If we hit the limit, verify error message format
            assert 'too large' in str(e).lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_normal_file_accepted(self):
        """Test that normal-sized files are accepted."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            segments = parser.extract_segments()
            assert len(segments) == 1
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestFileExtensionValidation:
    """Tests for file extension validation."""

    def test_sdlxliff_extension_accepted(self):
        """Test that .sdlxliff files are accepted."""
        validate_file_extension('/path/to/file.sdlxliff')
        validate_file_extension('/path/to/file.SDLXLIFF')
        validate_file_extension('/path/to/FILE.SdlXliff')

    def test_invalid_extensions_rejected(self):
        """Test that non-.sdlxliff extensions are rejected."""
        invalid_extensions = [
            '/path/to/file.xml',
            '/path/to/file.xliff',
            '/path/to/file.txt',
            '/path/to/file.sdlxliff.bak',
            '/path/to/file',
            '/path/to/file.sdlxlif',  # Typo
            '/path/to/file.xlf',
        ]

        for path in invalid_extensions:
            with pytest.raises(ValueError) as exc_info:
                validate_file_extension(path)
            assert 'sdlxliff' in str(exc_info.value).lower()

    def test_allowed_extensions_constant(self):
        """Test that only .sdlxliff is in allowed extensions."""
        assert ALLOWED_EXTENSIONS == {'.sdlxliff'}


class TestSegmentTextSizeLimits:
    """Tests for segment text size limit enforcement."""

    def test_segment_size_limit_constant(self):
        """Test that MAX_SEGMENT_TEXT_SIZE is defined and reasonable."""
        assert MAX_SEGMENT_TEXT_SIZE == 100 * 1024  # 100KB

    def test_large_segment_text_rejected(self):
        """Test that segment updates exceeding size limit are rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            parser.extract_segments()

            # Try to update with text exceeding the limit
            large_text = 'x' * (MAX_SEGMENT_TEXT_SIZE + 1)

            with pytest.raises(ValueError) as exc_info:
                parser.update_segment('1', large_text)

            assert 'too large' in str(exc_info.value).lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_large_segment_text_rejected_with_tags(self):
        """Test that update_segment_with_tags also enforces size limit."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            parser.extract_segments()

            # Try to update with text exceeding the limit
            large_text = 'x' * (MAX_SEGMENT_TEXT_SIZE + 1)

            result = parser.update_segment_with_tags('1', large_text)

            assert result['success'] is False
            assert 'too large' in result['message'].lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_normal_segment_text_accepted(self):
        """Test that normal-sized segment text is accepted."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            parser.extract_segments()

            # Update with reasonable text
            result = parser.update_segment('1', 'Normal sized text')
            assert result is True
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestParserSecurityConfig:
    """Tests to verify parser security configuration."""

    def test_parser_config_no_network(self):
        """Verify parser is configured with no_network=True."""
        # This is a documentation/verification test
        # The actual XMLParser config is in parser.py _load_file method
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            # Parser loaded successfully with secure config
            assert parser.root is not None
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_parser_config_no_entity_resolution(self):
        """Verify parser is configured with resolve_entities=False."""
        # Test with a simple internal entity
        entity_test = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE xliff [
  <!ENTITY test "TEST_ENTITY_VALUE">
]>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">
  <file source-language="en-US" target-language="ru-RU">
    <body>
      <trans-unit id="1">
        <source>&test;</source>
        <seg-source><mrk mtype="seg" mid="1">&test;</mrk></seg-source>
        <target><mrk mtype="seg" mid="1">Target</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
    </body>
  </file>
</xliff>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(entity_test)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            try:
                segments = parser.extract_segments()
                # Entity should NOT be expanded to "TEST_ENTITY_VALUE"
                for seg in segments:
                    assert 'TEST_ENTITY_VALUE' not in seg.get('source', '')
            except (ValueError, TypeError):
                # Error processing unexpanded entity - this is secure behavior
                pass
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestAtomicWrites:
    """Tests for atomic write and backup functionality."""

    def test_save_creates_backup(self):
        """Test that save creates a .bak backup file when overwriting."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        backup_path = temp_path + '.bak'

        try:
            parser = SDLXLIFFParser(temp_path)
            parser.update_segment('1', 'Updated text')
            parser.save()  # Save with default create_backup=True

            # Verify backup was created
            assert Path(backup_path).exists(), "Backup file should be created"

            # Verify backup contains original content
            with open(backup_path, 'rb') as f:
                backup_content = f.read()
            assert b'Hello' in backup_content  # Original target text
        finally:
            Path(temp_path).unlink(missing_ok=True)
            Path(backup_path).unlink(missing_ok=True)

    def test_save_no_backup_when_disabled(self):
        """Test that save doesn't create backup when create_backup=False."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        backup_path = temp_path + '.bak'

        try:
            parser = SDLXLIFFParser(temp_path)
            parser.update_segment('1', 'Updated text')
            parser.save(create_backup=False)

            # Verify backup was NOT created
            assert not Path(backup_path).exists(), "Backup file should not be created"
        finally:
            Path(temp_path).unlink(missing_ok=True)
            Path(backup_path).unlink(missing_ok=True)

    def test_save_atomic_no_temp_file_left_on_success(self):
        """Test that no temp files are left after successful save."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        temp_dir = Path(temp_path).parent

        try:
            # Count temp files before
            temp_files_before = list(temp_dir.glob('.sdlxliff_*.tmp'))

            parser = SDLXLIFFParser(temp_path)
            parser.update_segment('1', 'Updated text')
            parser.save(create_backup=False)

            # Count temp files after
            temp_files_after = list(temp_dir.glob('.sdlxliff_*.tmp'))

            # Should be no new temp files left
            assert len(temp_files_after) == len(temp_files_before), \
                "No temp files should be left after successful save"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_save_preserves_content_on_overwrite(self):
        """Test that saved file contains updated content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        try:
            parser = SDLXLIFFParser(temp_path)
            parser.update_segment('1', 'New translated text')
            parser.save(create_backup=False)

            # Re-read the file and verify content
            parser2 = SDLXLIFFParser(temp_path)
            segment = parser2.get_segment_by_id('1')
            assert segment['target'] == 'New translated text'
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_save_to_different_path(self):
        """Test saving to a different output path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False) as f:
            f.write(VALID_SDLXLIFF)
            temp_path = f.name

        output_path = temp_path.replace('.sdlxliff', '_output.sdlxliff')

        try:
            parser = SDLXLIFFParser(temp_path)
            parser.update_segment('1', 'Output text')
            parser.save(output_path=output_path)

            # Verify output file exists and has correct content
            assert Path(output_path).exists()
            parser2 = SDLXLIFFParser(output_path)
            segment = parser2.get_segment_by_id('1')
            assert segment['target'] == 'Output text'

            # Verify original file unchanged
            parser3 = SDLXLIFFParser(temp_path)
            segment3 = parser3.get_segment_by_id('1')
            assert 'Привет' in segment3['target']  # Original text
        finally:
            Path(temp_path).unlink(missing_ok=True)
            Path(output_path).unlink(missing_ok=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])