"""
Tests for SDLXLIFF tag handling functionality.

Tests the placeholder-based tag preservation system:
- Tag extraction and placeholder conversion
- Tag validation
- Tag restoration during updates
- Round-trip integrity
"""

import pytest
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_server_sdlxliff.parser import SDLXLIFFParser


# Sample SDLXLIFF content with tags for testing
SAMPLE_SDLXLIFF_WITH_TAGS = '''<?xml version="1.0" encoding="utf-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">
  <file source-language="en-US" target-language="ru-RU">
    <body>
      <trans-unit id="1">
        <source><g id="1">Bold text</g> and <g id="2">more bold</g></source>
        <seg-source><mrk mtype="seg" mid="1"><g id="1">Bold text</g> and <g id="2">more bold</g></mrk></seg-source>
        <target><mrk mtype="seg" mid="1"><g id="1">Жирный текст</g> и <g id="2">ещё жирный</g></mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
      <trans-unit id="2">
        <source>Simple text without tags</source>
        <seg-source><mrk mtype="seg" mid="2">Simple text without tags</mrk></seg-source>
        <target><mrk mtype="seg" mid="2">Простой текст без тегов</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="2" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
      <trans-unit id="3">
        <source><g id="5">Acme</g><g id="6">&amp;</g><g id="7"> Events</g></source>
        <seg-source><mrk mtype="seg" mid="3"><g id="5">Acme</g><g id="6">&amp;</g><g id="7"> Events</g></mrk></seg-source>
        <target><mrk mtype="seg" mid="3"><g id="5">Acme</g><g id="6">&amp;</g><g id="7"> События</g></mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="3" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
      <trans-unit id="4">
        <source><g id="10"><g id="11">Nested</g> tags</g></source>
        <seg-source><mrk mtype="seg" mid="4"><g id="10"><g id="11">Nested</g> tags</g></mrk></seg-source>
        <target><mrk mtype="seg" mid="4"><g id="10"><g id="11">Вложенные</g> теги</g></mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="4" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
      <trans-unit id="5">
        <source><g id="20"></g>Empty tag test</source>
        <seg-source><mrk mtype="seg" mid="5"><g id="20"></g>Empty tag test</mrk></seg-source>
        <target><mrk mtype="seg" mid="5"><g id="20"></g>Тест пустого тега</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="5" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
      <trans-unit id="6">
        <source>Text with <x id="30"/> self-closing tag</source>
        <seg-source><mrk mtype="seg" mid="6">Text with <x id="30"/> self-closing tag</mrk></seg-source>
        <target><mrk mtype="seg" mid="6">Текст с <x id="30"/> самозакрывающимся тегом</mrk></target>
        <sdl:seg-defs>
          <sdl:seg id="6" conf="Translated"/>
        </sdl:seg-defs>
      </trans-unit>
    </body>
  </file>
</xliff>'''


@pytest.fixture
def sample_file():
    """Create a temporary SDLXLIFF file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sdlxliff', delete=False, encoding='utf-8') as f:
        f.write(SAMPLE_SDLXLIFF_WITH_TAGS)
        temp_path = f.name
    yield temp_path
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def parser(sample_file):
    """Create a parser instance for the sample file."""
    return SDLXLIFFParser(sample_file)


class TestTagExtraction:
    """Tests for tag extraction and placeholder conversion."""

    def test_extract_segment_with_paired_tags(self, parser):
        """Test extracting a segment with paired <g> tags."""
        segments = parser.extract_segments()
        segment = next(s for s in segments if s['segment_id'] == '1')

        assert segment['has_tags'] is True
        assert segment['source'] == 'Bold text and more bold'
        assert segment['source_tagged'] == '{1}Bold text{/1} and {2}more bold{/2}'
        assert segment['target'] == 'Жирный текст и ещё жирный'
        assert segment['target_tagged'] == '{1}Жирный текст{/1} и {2}ещё жирный{/2}'

    def test_extract_segment_without_tags(self, parser):
        """Test extracting a segment without any tags."""
        segments = parser.extract_segments()
        segment = next(s for s in segments if s['segment_id'] == '2')

        assert segment['has_tags'] is False
        assert segment['source'] == 'Simple text without tags'
        assert segment['source_tagged'] == 'Simple text without tags'
        assert segment['target'] == 'Простой текст без тегов'
        assert segment['target_tagged'] == 'Простой текст без тегов'

    def test_extract_segment_with_ampersand(self, parser):
        """Test extracting a segment with &amp; in tags."""
        segments = parser.extract_segments()
        segment = next(s for s in segments if s['segment_id'] == '3')

        assert segment['has_tags'] is True
        assert segment['source'] == 'Acme& Events'
        assert segment['source_tagged'] == '{5}Acme{/5}{6}&{/6}{7} Events{/7}'

    def test_extract_segment_with_nested_tags(self, parser):
        """Test extracting a segment with nested tags."""
        segments = parser.extract_segments()
        segment = next(s for s in segments if s['segment_id'] == '4')

        assert segment['has_tags'] is True
        assert segment['source'] == 'Nested tags'
        assert segment['source_tagged'] == '{10}{11}Nested{/11} tags{/10}'

    def test_extract_segment_with_empty_tag(self, parser):
        """Test extracting a segment with an empty tag."""
        segments = parser.extract_segments()
        segment = next(s for s in segments if s['segment_id'] == '5')

        assert segment['has_tags'] is True
        assert segment['source'] == 'Empty tag test'
        assert segment['source_tagged'] == '{20}{/20}Empty tag test'

    def test_extract_segment_with_self_closing_tag(self, parser):
        """Test extracting a segment with a self-closing <x> tag."""
        segments = parser.extract_segments()
        segment = next(s for s in segments if s['segment_id'] == '6')

        assert segment['has_tags'] is True
        assert segment['source'] == 'Text with  self-closing tag'
        assert segment['source_tagged'] == 'Text with {x:30} self-closing tag'


class TestTagValidation:
    """Tests for tag validation."""

    def test_validate_correct_tags(self, parser):
        """Test validation passes for correct tags."""
        # First extract to populate cache
        parser.extract_segments()

        result = parser.validate_tagged_text('1', '{1}Новый текст{/1} и {2}другой{/2}')
        assert result['valid'] is True
        assert len(result['errors']) == 0

    def test_validate_missing_tag(self, parser):
        """Test validation fails when a tag is missing."""
        parser.extract_segments()

        result = parser.validate_tagged_text('1', '{1}Текст только с первым тегом{/1}')
        assert result['valid'] is False
        assert '2' in result['missing_tags']
        assert any('Missing tags' in e for e in result['errors'])

    def test_validate_extra_tag(self, parser):
        """Test validation fails when an unknown tag is added."""
        parser.extract_segments()

        result = parser.validate_tagged_text('1', '{1}Текст{/1} и {2}другой{/2} и {99}лишний{/99}')
        assert result['valid'] is False
        assert '99' in result['extra_tags']
        assert any('Unknown tags' in e for e in result['errors'])

    def test_validate_unclosed_tag(self, parser):
        """Test validation fails for unclosed tags."""
        parser.extract_segments()

        result = parser.validate_tagged_text('1', '{1}Незакрытый тег и {2}другой{/2}')
        assert result['valid'] is False
        assert any('Unclosed tags' in e for e in result['errors'])

    def test_validate_mismatched_close(self, parser):
        """Test validation fails for mismatched closing tags."""
        parser.extract_segments()

        result = parser.validate_tagged_text('1', '{1}Текст{/2} и {2}другой{/1}')
        assert result['valid'] is False
        assert any('Mismatched' in e for e in result['errors'])

    def test_validate_tag_order_change_warning(self, parser):
        """Test validation warns when tag order changes."""
        parser.extract_segments()

        result = parser.validate_tagged_text('1', '{2}Сначала второй{/2} потом {1}первый{/1}')
        assert result['valid'] is True  # Order change is allowed
        assert len(result['warnings']) > 0
        assert any('order changed' in w for w in result['warnings'])

    def test_validate_segment_without_tags(self, parser):
        """Test validation passes for segments without tags."""
        parser.extract_segments()

        result = parser.validate_tagged_text('2', 'Любой текст без тегов')
        assert result['valid'] is True


class TestTagPreservationOnUpdate:
    """Tests for tag preservation when updating segments."""

    def test_update_with_correct_tags(self, parser):
        """Test successful update with correct tags."""
        parser.extract_segments()

        result = parser.update_segment_with_tags(
            '1',
            '{1}Обновлённый жирный{/1} и {2}ещё обновлённый{/2}'
        )
        assert result['success'] is True

        # Verify the update
        segment = parser.get_segment_by_id('1')
        assert segment['target'] == 'Обновлённый жирный и ещё обновлённый'
        assert segment['target_tagged'] == '{1}Обновлённый жирный{/1} и {2}ещё обновлённый{/2}'

    def test_update_reject_missing_tags(self, parser):
        """Test update is rejected when tags are missing."""
        parser.extract_segments()

        result = parser.update_segment_with_tags(
            '1',
            '{1}Только первый тег{/1}'
        )
        assert result['success'] is False
        assert 'Missing tags' in result['message']

    def test_update_reject_tags_not_provided(self, parser):
        """Test update is rejected when segment has tags but no placeholders provided."""
        parser.extract_segments()

        result = parser.update_segment_with_tags(
            '1',
            'Текст без тегов для сегмента с тегами'
        )
        assert result['success'] is False
        assert 'no placeholders were provided' in result['message']

    def test_update_segment_without_tags(self, parser):
        """Test update works for segments without tags."""
        parser.extract_segments()

        result = parser.update_segment_with_tags(
            '2',
            'Новый простой текст'
        )
        assert result['success'] is True

        segment = parser.get_segment_by_id('2')
        assert segment['target'] == 'Новый простой текст'

    def test_update_preserve_tags_false(self, parser):
        """Test update strips tags when preserve_tags=False."""
        parser.extract_segments()

        result = parser.update_segment_with_tags(
            '1',
            'Текст без тегов',
            preserve_tags=False
        )
        assert result['success'] is True

        segment = parser.get_segment_by_id('1')
        assert segment['target'] == 'Текст без тегов'
        # has_tags still True because SOURCE has tags (we only stripped target tags)
        assert segment['target_tagged'] == 'Текст без тегов'  # No placeholders in target now
        assert segment['source_tagged'] == '{1}Bold text{/1} and {2}more bold{/2}'  # Source still has tags

    def test_update_with_reordered_tags(self, parser):
        """Test update succeeds with reordered tags (warns but allows)."""
        parser.extract_segments()

        result = parser.update_segment_with_tags(
            '1',
            '{2}Второй сначала{/2} потом {1}первый{/1}'
        )
        assert result['success'] is True
        assert len(result['warnings']) > 0


class TestRoundTrip:
    """Tests for round-trip integrity (read -> modify -> save -> read)."""

    def test_roundtrip_with_tags(self, sample_file):
        """Test that tags survive a full round-trip."""
        # First read
        parser1 = SDLXLIFFParser(sample_file)
        parser1.extract_segments()

        # Update with new text but same tags
        parser1.update_segment_with_tags(
            '3',
            '{5}Acme{/5}{6}&{/6}{7} Новые События{/7}'
        )

        # Save
        parser1.save()

        # Read again with fresh parser
        parser2 = SDLXLIFFParser(sample_file)
        segment = parser2.get_segment_by_id('3')

        assert segment['has_tags'] is True
        assert segment['target'] == 'Acme& Новые События'
        assert segment['target_tagged'] == '{5}Acme{/5}{6}&{/6}{7} Новые События{/7}'

    def test_roundtrip_preserves_xml_structure(self, sample_file):
        """Test that original XML structure is preserved after update."""
        from lxml import etree

        # Update segment
        parser = SDLXLIFFParser(sample_file)
        parser.extract_segments()
        parser.update_segment_with_tags(
            '1',
            '{1}Новый текст{/1} и {2}другой{/2}'
        )
        parser.save()

        # Parse raw XML to verify structure
        tree = etree.parse(sample_file)
        ns = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

        # Find the updated mrk
        mrk = tree.find(".//xliff:trans-unit[@id='1']//xliff:target//xliff:mrk[@mid='1']", ns)
        assert mrk is not None

        # Verify g elements exist
        g_elements = mrk.findall('.//xliff:g', ns)
        assert len(g_elements) == 2

        # Verify IDs preserved
        ids = {g.get('id') for g in g_elements}
        assert ids == {'1', '2'}


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_nonexistent_segment(self, parser):
        """Test handling of non-existent segment ID."""
        result = parser.validate_tagged_text('999', 'any text')
        assert result['valid'] is False
        assert "not found" in result['errors'][0]

    def test_empty_text_update(self, parser):
        """Test updating with empty text."""
        parser.extract_segments()

        result = parser.update_segment_with_tags('2', '')
        assert result['success'] is True

    def test_large_text_validation(self, parser):
        """Test that very large text is rejected."""
        parser.extract_segments()

        large_text = 'x' * (parser.MAX_SEGMENT_TEXT_SIZE + 1)
        result = parser.update_segment_with_tags('2', large_text)
        assert result['success'] is False
        assert 'too large' in result['message']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
