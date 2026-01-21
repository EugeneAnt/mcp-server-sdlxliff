"""
Tests for SDLXLIFF QA check functionality.

Tests the quality assurance checks:
- Trailing punctuation mismatches
- Missing/extra numbers
- Double spaces
- Leading/trailing whitespace mismatches
- Bracket/parenthesis mismatches
- Inconsistent repetitions
- Terminology/glossary compliance
"""

import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_server_sdlxliff.qa import (
    check_trailing_punctuation,
    check_numbers,
    check_double_spaces,
    check_whitespace,
    check_brackets,
    check_inconsistent_repetitions,
    check_terminology,
    load_glossary,
    discover_glossary,
    run_qa_checks,
    QAIssue,
    QAReport,
)


class TestTrailingPunctuation:
    """Tests for trailing punctuation check."""

    def test_matching_period(self):
        """No issue when both end with period."""
        issue = check_trailing_punctuation("1", "Hello.", "Привет.")
        assert issue is None

    def test_matching_no_punctuation(self):
        """No issue when neither has trailing punctuation."""
        issue = check_trailing_punctuation("1", "Hello", "Привет")
        assert issue is None

    def test_source_has_period_target_missing(self):
        """Issue when source has period but target doesn't."""
        issue = check_trailing_punctuation("1", "Hello.", "Привет")
        assert issue is not None
        assert issue.check == "trailing_punctuation"
        assert "Source ends with" in issue.message
        assert "target does not" in issue.message

    def test_target_has_period_source_missing(self):
        """Issue when target has period but source doesn't."""
        issue = check_trailing_punctuation("1", "Hello", "Привет.")
        assert issue is not None
        assert "Target ends with" in issue.message

    def test_question_mark(self):
        """Check works with question marks."""
        issue = check_trailing_punctuation("1", "How are you?", "Как дела")
        assert issue is not None

    def test_exclamation_mark(self):
        """Check works with exclamation marks."""
        issue = check_trailing_punctuation("1", "Hello!", "Привет!")
        assert issue is None

    def test_colon(self):
        """Check works with colons."""
        issue = check_trailing_punctuation("1", "Note:", "Примечание")
        assert issue is not None

    def test_multiple_punctuation(self):
        """Check handles multiple trailing punctuation."""
        issue = check_trailing_punctuation("1", "Really?!", "Правда?!")
        assert issue is None

    def test_empty_strings(self):
        """No issue for empty strings."""
        issue = check_trailing_punctuation("1", "", "")
        assert issue is None

    def test_arabic_comma(self):
        """Check recognizes Arabic comma."""
        issue = check_trailing_punctuation("1", "Text،", "Text")
        assert issue is not None

    def test_chinese_punctuation(self):
        """Check recognizes Chinese punctuation."""
        issue = check_trailing_punctuation("1", "Text。", "Text")
        assert issue is not None


class TestNumbers:
    """Tests for number matching check."""

    def test_matching_numbers(self):
        """No issue when numbers match."""
        issue = check_numbers("1", "Item 42 costs $99", "Товар 42 стоит $99")
        assert issue is None

    def test_missing_number(self):
        """Issue when number is missing in target."""
        issue = check_numbers("1", "Version 2.0", "Версия")
        assert issue is not None
        assert issue.check == "numbers"
        assert "missing" in issue.message
        assert "2" in issue.message or "2.0" in issue.message

    def test_extra_number(self):
        """Issue when target has extra number."""
        issue = check_numbers("1", "Item", "Товар 5")
        assert issue is not None
        assert "extra" in issue.message

    def test_decimal_numbers(self):
        """Check handles decimal numbers."""
        issue = check_numbers("1", "Price: 19.99", "Цена: 19.99")
        assert issue is None

    def test_comma_decimal(self):
        """Check handles European decimal format."""
        issue = check_numbers("1", "Price: 19,99", "Цена: 19,99")
        assert issue is None

    def test_multiple_numbers(self):
        """Check handles multiple numbers."""
        issue = check_numbers("1", "From 10 to 20", "От 10 до 20")
        assert issue is None

    def test_order_doesnt_matter(self):
        """Number order doesn't affect result."""
        issue = check_numbers("1", "10 and 20", "20 and 10")
        assert issue is None

    def test_no_numbers(self):
        """No issue when neither has numbers."""
        issue = check_numbers("1", "Hello world", "Привет мир")
        assert issue is None

    def test_empty_strings(self):
        """No issue for empty strings."""
        issue = check_numbers("1", "", "")
        assert issue is None


class TestDoubleSpaces:
    """Tests for double space check."""

    def test_no_double_spaces(self):
        """No issue for normal text."""
        issue = check_double_spaces("1", "Normal text here")
        assert issue is None

    def test_double_space_detected(self):
        """Issue when double space found."""
        issue = check_double_spaces("1", "Double  space here")
        assert issue is not None
        assert issue.check == "double_spaces"
        assert "double spaces" in issue.message.lower()

    def test_triple_space(self):
        """Issue when triple space found."""
        issue = check_double_spaces("1", "Triple   space")
        assert issue is not None

    def test_space_at_end(self):
        """Double space at end detected."""
        issue = check_double_spaces("1", "Text ends  ")
        assert issue is not None

    def test_space_at_start(self):
        """Double space at start detected."""
        issue = check_double_spaces("1", "  Starts with spaces")
        assert issue is not None

    def test_empty_string(self):
        """No issue for empty string."""
        issue = check_double_spaces("1", "")
        assert issue is None

    def test_single_spaces_ok(self):
        """Multiple single spaces are fine."""
        issue = check_double_spaces("1", "One two three four")
        assert issue is None


class TestWhitespace:
    """Tests for whitespace mismatch check."""

    def test_no_whitespace_issues(self):
        """No issue when whitespace matches."""
        issue = check_whitespace("1", "Normal text", "Обычный текст")
        assert issue is None

    def test_source_leading_whitespace(self):
        """Issue when source has leading whitespace but target doesn't."""
        issue = check_whitespace("1", " Leading space", "Без пробела")
        assert issue is not None
        assert issue.check == "whitespace"
        assert "leading" in issue.message.lower()

    def test_target_leading_whitespace(self):
        """Issue when target has leading whitespace but source doesn't."""
        issue = check_whitespace("1", "No space", " С пробелом")
        assert issue is not None
        assert "leading" in issue.message.lower()

    def test_source_trailing_whitespace(self):
        """Issue when source has trailing whitespace but target doesn't."""
        issue = check_whitespace("1", "Trailing space ", "Без пробела")
        assert issue is not None
        assert "trailing" in issue.message.lower()

    def test_target_trailing_whitespace(self):
        """Issue when target has trailing whitespace but source doesn't."""
        issue = check_whitespace("1", "No space", "С пробелом ")
        assert issue is not None
        assert "trailing" in issue.message.lower()

    def test_both_have_whitespace(self):
        """No issue when both have matching whitespace."""
        issue = check_whitespace("1", " Both have ", " Оба имеют ")
        assert issue is None

    def test_empty_strings(self):
        """No issue for empty strings."""
        issue = check_whitespace("1", "", "")
        assert issue is None

    def test_tabs_not_checked(self):
        """Tabs at edges are treated as whitespace."""
        issue = check_whitespace("1", "\tTab start", "No tab")
        assert issue is not None


class TestBrackets:
    """Tests for bracket mismatch check."""

    def test_matching_parentheses(self):
        """No issue when parentheses match."""
        issue = check_brackets("1", "Text (note)", "Текст (примечание)")
        assert issue is None

    def test_missing_parenthesis(self):
        """Issue when parenthesis is missing."""
        issue = check_brackets("1", "Text (note)", "Текст примечание")
        assert issue is not None
        assert issue.check == "brackets"
        assert "(" in issue.message

    def test_extra_parenthesis(self):
        """Issue when extra parenthesis in target."""
        issue = check_brackets("1", "Text", "Текст ()")
        assert issue is not None

    def test_square_brackets(self):
        """Check handles square brackets."""
        issue = check_brackets("1", "See [1]", "См. [1]")
        assert issue is None

    def test_curly_braces(self):
        """Check handles curly braces."""
        issue = check_brackets("1", "Value {x}", "Значение {x}")
        assert issue is None

    def test_mixed_brackets(self):
        """Check handles mixed bracket types."""
        issue = check_brackets("1", "(a) [b] {c}", "(а) [б] {в}")
        assert issue is None

    def test_nested_brackets(self):
        """Check handles nested brackets."""
        issue = check_brackets("1", "((nested))", "((вложенные))")
        assert issue is None

    def test_fullwidth_brackets(self):
        """Check handles full-width brackets."""
        issue = check_brackets("1", "Text（note）", "Text（примечание）")
        assert issue is None

    def test_empty_strings(self):
        """No issue for empty strings."""
        issue = check_brackets("1", "", "")
        assert issue is None


class TestInconsistentRepetitions:
    """Tests for inconsistent repetition check."""

    def test_consistent_repetitions(self):
        """No issue when repetitions have same translation."""
        segments = [
            {"segment_id": "1", "source": "Click here", "target": "Нажмите здесь", "repetitions": 3},
            {"segment_id": "2", "source": "Click here", "target": "Нажмите здесь", "repetitions": 3},
            {"segment_id": "3", "source": "Click here", "target": "Нажмите здесь", "repetitions": 3},
        ]
        issues = check_inconsistent_repetitions(segments)
        assert len(issues) == 0

    def test_inconsistent_repetitions(self):
        """Issue when repetitions have different translations."""
        segments = [
            {"segment_id": "1", "source": "Click here", "target": "Нажмите здесь", "repetitions": 3},
            {"segment_id": "2", "source": "Click here", "target": "Нажмите здесь", "repetitions": 3},
            {"segment_id": "3", "source": "Click here", "target": "Кликните тут", "repetitions": 3},
        ]
        issues = check_inconsistent_repetitions(segments)
        assert len(issues) == 1
        assert issues[0].segment_id == "3"
        assert issues[0].check == "inconsistent_repetitions"

    def test_no_repetitions(self):
        """No issues when no segments are marked as repetitions."""
        segments = [
            {"segment_id": "1", "source": "Hello", "target": "Привет"},
            {"segment_id": "2", "source": "World", "target": "Мир"},
        ]
        issues = check_inconsistent_repetitions(segments)
        assert len(issues) == 0

    def test_repetition_count_one(self):
        """No check for segments with repetitions=1."""
        segments = [
            {"segment_id": "1", "source": "Unique", "target": "Уникальный", "repetitions": 1},
        ]
        issues = check_inconsistent_repetitions(segments)
        assert len(issues) == 0

    def test_empty_target_ignored(self):
        """Empty targets are ignored in comparison."""
        segments = [
            {"segment_id": "1", "source": "Click here", "target": "Нажмите здесь", "repetitions": 2},
            {"segment_id": "2", "source": "Click here", "target": "", "repetitions": 2},
        ]
        issues = check_inconsistent_repetitions(segments)
        # No issue because empty target is ignored
        assert len(issues) == 0

    def test_multiple_inconsistent_groups(self):
        """Issues reported for multiple inconsistent groups."""
        segments = [
            {"segment_id": "1", "source": "Save", "target": "Сохранить", "repetitions": 2},
            {"segment_id": "2", "source": "Save", "target": "Сохранять", "repetitions": 2},
            {"segment_id": "3", "source": "Cancel", "target": "Отмена", "repetitions": 2},
            {"segment_id": "4", "source": "Cancel", "target": "Отменить", "repetitions": 2},
        ]
        issues = check_inconsistent_repetitions(segments)
        assert len(issues) == 2


class TestRunQAChecks:
    """Tests for the main run_qa_checks function."""

    def test_run_all_checks(self):
        """Test running all checks."""
        segments = [
            {"segment_id": "1", "source": "Hello.", "target": "Привет"},  # Punctuation
            {"segment_id": "2", "source": "Item 5", "target": "Товар"},  # Number
            {"segment_id": "3", "source": "Text", "target": "Текст  двойной"},  # Double space
        ]
        report = run_qa_checks(segments)

        assert isinstance(report, QAReport)
        assert report.total_segments == 3
        assert report.segments_checked == 3
        assert report.segments_with_issues >= 3
        assert len(report.issues) >= 3
        assert "trailing_punctuation" in report.summary
        assert "numbers" in report.summary
        assert "double_spaces" in report.summary

    def test_run_specific_checks(self):
        """Test running only specific checks."""
        segments = [
            {"segment_id": "1", "source": "Hello.", "target": "Привет"},  # Would trigger punctuation
            {"segment_id": "2", "source": "Item 5", "target": "Товар"},  # Would trigger number
        ]
        report = run_qa_checks(segments, checks=["numbers"])

        assert len(report.issues) == 1
        assert report.issues[0].check == "numbers"
        assert "trailing_punctuation" not in report.summary

    def test_empty_segments(self):
        """Test with empty segment list."""
        report = run_qa_checks([])
        assert report.total_segments == 0
        assert report.segments_checked == 0
        assert report.segments_with_issues == 0
        assert len(report.issues) == 0

    def test_clean_segments(self):
        """Test with segments that have no issues."""
        segments = [
            {"segment_id": "1", "source": "Hello.", "target": "Привет."},
            {"segment_id": "2", "source": "Item 5", "target": "Товар 5"},
        ]
        report = run_qa_checks(segments)
        assert report.segments_with_issues == 0
        assert len(report.issues) == 0

    def test_report_structure(self):
        """Test QAReport structure."""
        segments = [
            {"segment_id": "1", "source": "Test.", "target": "Тест"},
        ]
        report = run_qa_checks(segments)

        assert hasattr(report, "total_segments")
        assert hasattr(report, "segments_checked")
        assert hasattr(report, "segments_with_issues")
        assert hasattr(report, "issues")
        assert hasattr(report, "summary")

    def test_issue_structure(self):
        """Test QAIssue structure."""
        segments = [
            {"segment_id": "1", "source": "Test.", "target": "Тест"},
        ]
        report = run_qa_checks(segments)

        assert len(report.issues) > 0
        issue = report.issues[0]
        assert hasattr(issue, "segment_id")
        assert hasattr(issue, "check")
        assert hasattr(issue, "severity")
        assert hasattr(issue, "message")
        assert hasattr(issue, "source_excerpt")
        assert hasattr(issue, "target_excerpt")

    def test_invalid_check_names_ignored(self):
        """Test that invalid check names are ignored."""
        segments = [
            {"segment_id": "1", "source": "Test.", "target": "Тест"},
        ]
        # Include an invalid check name
        report = run_qa_checks(segments, checks=["invalid_check", "trailing_punctuation"])

        # Should only run the valid check
        assert len(report.issues) == 1
        assert report.issues[0].check == "trailing_punctuation"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_unicode_text(self):
        """Test with Unicode text."""
        issue = check_trailing_punctuation("1", "日本語。", "日本語")
        assert issue is not None

    def test_emoji_in_text(self):
        """Test with emoji in text."""
        issue = check_numbers("1", "Item 5 🎉", "Товар 5 🎉")
        assert issue is None

    def test_very_long_text(self):
        """Test with very long text."""
        long_text = "A" * 10000
        issue = check_double_spaces("1", long_text)
        assert issue is None

    def test_special_characters(self):
        """Test with special characters."""
        issue = check_brackets("1", "a < b > c", "a < b > c")
        # < and > are not in the bracket set
        assert issue is None

    def test_none_values(self):
        """Test handling of None-like values."""
        # Empty string is handled
        issue = check_trailing_punctuation("1", "", "test.")
        assert issue is None  # Empty source, no comparison


class TestLoadGlossary:
    """Tests for glossary loading functionality."""

    def test_load_valid_glossary(self):
        """Load a valid tab-delimited glossary."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False, encoding='utf-8') as f:
            f.write("Galaxy\tGalaxy\n")
            f.write("Settings\tНастройки\n")
            f.write("OK\tOK\n")
            glossary_path = f.name

        terms = load_glossary(glossary_path)
        assert len(terms) == 3
        assert ("Galaxy", "Galaxy") in terms
        assert ("Settings", "Настройки") in terms
        assert ("OK", "OK") in terms

        Path(glossary_path).unlink()

    def test_load_glossary_with_comments(self):
        """Comments are skipped."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False, encoding='utf-8') as f:
            f.write("# This is a comment\n")
            f.write("Galaxy\tGalaxy\n")
            f.write("# Another comment\n")
            f.write("Settings\tНастройки\n")
            glossary_path = f.name

        terms = load_glossary(glossary_path)
        assert len(terms) == 2

        Path(glossary_path).unlink()

    def test_load_glossary_with_empty_lines(self):
        """Empty lines are skipped."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False, encoding='utf-8') as f:
            f.write("Galaxy\tGalaxy\n")
            f.write("\n")
            f.write("   \n")
            f.write("Settings\tНастройки\n")
            glossary_path = f.name

        terms = load_glossary(glossary_path)
        assert len(terms) == 2

        Path(glossary_path).unlink()

    def test_load_glossary_single_term(self):
        """Single term means it should appear unchanged."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False, encoding='utf-8') as f:
            f.write("Galaxy\n")
            f.write("iPhone\n")
            glossary_path = f.name

        terms = load_glossary(glossary_path)
        assert len(terms) == 2
        assert ("Galaxy", "Galaxy") in terms
        assert ("iPhone", "iPhone") in terms

        Path(glossary_path).unlink()

    def test_load_nonexistent_glossary(self):
        """Return empty list for nonexistent file."""
        terms = load_glossary("/nonexistent/path/glossary.tsv")
        assert terms == []

    def test_load_glossary_strips_whitespace(self):
        """Whitespace around terms is stripped."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False, encoding='utf-8') as f:
            f.write("  Galaxy  \t  Galaxy  \n")
            glossary_path = f.name

        terms = load_glossary(glossary_path)
        assert len(terms) == 1
        assert ("Galaxy", "Galaxy") in terms

        Path(glossary_path).unlink()


class TestDiscoverGlossary:
    """Tests for glossary auto-discovery."""

    def test_discover_glossary_tsv(self):
        """Discover glossary.tsv in same directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sdlxliff_path = Path(tmpdir) / "document.sdlxliff"
            sdlxliff_path.touch()
            glossary_path = Path(tmpdir) / "glossary.tsv"
            glossary_path.write_text("Galaxy\tGalaxy\n")

            discovered = discover_glossary(str(sdlxliff_path))
            assert discovered == str(glossary_path)

    def test_discover_glossary_txt(self):
        """Discover glossary.txt when tsv not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sdlxliff_path = Path(tmpdir) / "document.sdlxliff"
            sdlxliff_path.touch()
            glossary_path = Path(tmpdir) / "glossary.txt"
            glossary_path.write_text("Galaxy\tGalaxy\n")

            discovered = discover_glossary(str(sdlxliff_path))
            assert discovered == str(glossary_path)

    def test_discover_terminology_tsv(self):
        """Discover terminology.tsv when glossary not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sdlxliff_path = Path(tmpdir) / "document.sdlxliff"
            sdlxliff_path.touch()
            glossary_path = Path(tmpdir) / "terminology.tsv"
            glossary_path.write_text("Galaxy\tGalaxy\n")

            discovered = discover_glossary(str(sdlxliff_path))
            assert discovered == str(glossary_path)

    def test_discover_no_glossary(self):
        """Return None when no glossary found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sdlxliff_path = Path(tmpdir) / "document.sdlxliff"
            sdlxliff_path.touch()

            discovered = discover_glossary(str(sdlxliff_path))
            assert discovered is None

    def test_discover_priority(self):
        """glossary.tsv takes priority over other filenames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sdlxliff_path = Path(tmpdir) / "document.sdlxliff"
            sdlxliff_path.touch()
            (Path(tmpdir) / "glossary.tsv").write_text("A\tB\n")
            (Path(tmpdir) / "glossary.txt").write_text("C\tD\n")
            (Path(tmpdir) / "terminology.tsv").write_text("E\tF\n")

            discovered = discover_glossary(str(sdlxliff_path))
            assert discovered.endswith("glossary.tsv")


class TestCheckTerminology:
    """Tests for terminology check."""

    def test_term_present_in_both(self):
        """No issue when term is in both source and target."""
        terms = [("Galaxy", "Galaxy")]
        issues = check_terminology("1", "My Galaxy phone", "Мой телефон Galaxy", terms)
        assert len(issues) == 0

    def test_term_missing_in_target(self):
        """Issue when source term found but target term missing."""
        terms = [("Galaxy", "Galaxy")]
        issues = check_terminology("1", "My Galaxy phone", "Мой телефон", terms)
        assert len(issues) == 1
        assert issues[0].check == "terminology"
        assert "Galaxy" in issues[0].message

    def test_term_not_in_source(self):
        """No issue when source term not in source text."""
        terms = [("Galaxy", "Galaxy")]
        issues = check_terminology("1", "My iPhone phone", "Мой телефон iPhone", terms)
        assert len(issues) == 0

    def test_multiple_terms(self):
        """Check multiple terms at once."""
        terms = [
            ("Galaxy", "Galaxy"),
            ("Smart Switch", "Smart Switch"),
            ("Settings", "Настройки"),
        ]
        issues = check_terminology(
            "1",
            "Open Galaxy Settings and use Smart Switch",
            "Откройте Настройки и используйте Smart Switch",  # Missing "Galaxy"
            terms
        )
        assert len(issues) == 1
        assert "Galaxy" in issues[0].message

    def test_case_sensitive(self):
        """Terminology check is case-sensitive."""
        terms = [("Galaxy", "Galaxy")]
        # "galaxy" (lowercase) doesn't match "Galaxy"
        issues = check_terminology("1", "My galaxy phone", "Мой телефон galaxy", terms)
        assert len(issues) == 0

    def test_translated_term(self):
        """Check that source term maps to translated target term."""
        terms = [("Settings", "Настройки")]
        issues = check_terminology("1", "Open Settings", "Откройте Настройки", terms)
        assert len(issues) == 0

    def test_translated_term_missing(self):
        """Issue when translated target term is missing."""
        terms = [("Settings", "Настройки")]
        issues = check_terminology("1", "Open Settings", "Откройте Settings", terms)
        assert len(issues) == 1
        assert "Settings" in issues[0].message
        assert "Настройки" in issues[0].message

    def test_empty_terms_list(self):
        """No issues with empty terms list."""
        issues = check_terminology("1", "Test source", "Test target", [])
        assert len(issues) == 0

    def test_empty_source_or_target(self):
        """No issues with empty source or target."""
        terms = [("Galaxy", "Galaxy")]
        assert check_terminology("1", "", "Target text", terms) == []
        assert check_terminology("1", "Source text", "", terms) == []


class TestRunQAChecksWithTerminology:
    """Tests for run_qa_checks with terminology."""

    def test_terminology_check_with_glossary(self):
        """Terminology check runs when glossary provided."""
        segments = [
            {"segment_id": "1", "source": "My Galaxy phone", "target": "Мой телефон"},
        ]
        glossary_terms = [("Galaxy", "Galaxy")]

        report = run_qa_checks(segments, checks=["terminology"], glossary_terms=glossary_terms)
        assert "terminology" in report.summary
        assert report.summary["terminology"] == 1

    def test_terminology_check_without_glossary(self):
        """Terminology check doesn't flag when no glossary."""
        segments = [
            {"segment_id": "1", "source": "My Galaxy phone", "target": "Мой телефон"},
        ]

        report = run_qa_checks(segments, checks=["terminology"])
        # No issues because no glossary terms provided
        assert "terminology" not in report.summary

    def test_terminology_check_clean(self):
        """No issues when all terms are correct."""
        segments = [
            {"segment_id": "1", "source": "My Galaxy phone", "target": "Мой телефон Galaxy"},
        ]
        glossary_terms = [("Galaxy", "Galaxy")]

        report = run_qa_checks(segments, checks=["terminology"], glossary_terms=glossary_terms)
        assert "terminology" not in report.summary

    def test_terminology_in_all_checks(self):
        """Terminology is included when running all checks with glossary."""
        segments = [
            {"segment_id": "1", "source": "My Galaxy phone.", "target": "Мой телефон"},  # Missing period + Galaxy
        ]
        glossary_terms = [("Galaxy", "Galaxy")]

        report = run_qa_checks(segments, glossary_terms=glossary_terms)
        assert "terminology" in report.summary
        assert "trailing_punctuation" in report.summary


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
