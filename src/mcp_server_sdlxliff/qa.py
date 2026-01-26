"""
Quality Assurance checks for SDLXLIFF segments.

Provides stateless QA check functions that detect common translation issues:
- Trailing punctuation mismatches
- Missing/extra numbers
- Double spaces
- Leading/trailing whitespace mismatches
- Bracket/parenthesis mismatches
- Inconsistent repetitions
- Terminology/glossary compliance
- Spelling (opt-in, requires explicit check selection)
"""

import json
import re
import urllib.request
import urllib.parse
import urllib.error
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from spellchecker import SpellChecker
    SPELLCHECKER_AVAILABLE = True
except ImportError:
    SPELLCHECKER_AVAILABLE = False

from .languages import get_spellcheck_config, BACKEND_YANDEX, BACKEND_PYSPELLCHECKER


@dataclass
class QAIssue:
    """Represents a single QA issue found in a segment."""
    segment_id: str
    check: str
    severity: str  # "warning" or "error"
    message: str
    source_excerpt: str = ""
    target_excerpt: str = ""


@dataclass
class QAReport:
    """Complete QA report for a file."""
    total_segments: int
    segments_checked: int
    segments_with_issues: int
    issues: List[QAIssue] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)


# Trailing punctuation pattern - covers common punctuation across languages
TRAILING_PUNCT_PATTERN = re.compile(r'[.!?:;،。！？：；]+$')

# Number extraction pattern - matches integers and decimals with , or . separators
NUMBER_PATTERN = re.compile(r'\d+(?:[.,]\d+)?')

# Double space pattern
DOUBLE_SPACE_PATTERN = re.compile(r'[ ]{2,}')

# Bracket characters to check
BRACKET_PAIRS = {
    '(': ')',
    '[': ']',
    '{': '}',
    '（': '）',  # Full-width
    '【': '】',
    '「': '」',
    '『': '』',
}
ALL_BRACKETS = set(BRACKET_PAIRS.keys()) | set(BRACKET_PAIRS.values())


def check_trailing_punctuation(
    segment_id: str,
    source: str,
    target: str
) -> Optional[QAIssue]:
    """
    Check if source and target have matching trailing punctuation.

    Returns an issue if:
    - Source ends with punctuation but target doesn't
    - Target ends with punctuation but source doesn't
    """
    if not source or not target:
        return None

    source_punct = TRAILING_PUNCT_PATTERN.search(source)
    target_punct = TRAILING_PUNCT_PATTERN.search(target)

    source_has = source_punct is not None
    target_has = target_punct is not None

    if source_has != target_has:
        if source_has:
            message = f"Source ends with '{source_punct.group()}' but target does not"
        else:
            message = f"Target ends with '{target_punct.group()}' but source does not"

        return QAIssue(
            segment_id=segment_id,
            check="trailing_punctuation",
            severity="warning",
            message=message,
            source_excerpt=_excerpt(source, tail=True),
            target_excerpt=_excerpt(target, tail=True),
        )

    return None


def check_numbers(
    segment_id: str,
    source: str,
    target: str
) -> Optional[QAIssue]:
    """
    Check if all numbers from source appear in target with same frequency.

    Returns an issue if numbers don't match (missing, extra, or wrong count).
    Uses Counter to detect duplicate number mismatches (e.g., "50 50" vs "50").
    """
    if not source or not target:
        return None

    source_numbers = Counter(NUMBER_PATTERN.findall(source))
    target_numbers = Counter(NUMBER_PATTERN.findall(target))

    if source_numbers != target_numbers:
        parts = []

        # Find missing numbers (in source but not enough in target)
        for num, count in source_numbers.items():
            target_count = target_numbers.get(num, 0)
            if target_count < count:
                diff = count - target_count
                if diff == count:
                    parts.append(f"missing: {num}" + (f" (x{count})" if count > 1 else ""))
                else:
                    parts.append(f"missing: {num} (need {count}, have {target_count})")

        # Find extra numbers (in target but not enough in source)
        for num, count in target_numbers.items():
            source_count = source_numbers.get(num, 0)
            if count > source_count:
                diff = count - source_count
                if source_count == 0:
                    parts.append(f"extra: {num}" + (f" (x{count})" if count > 1 else ""))
                else:
                    parts.append(f"extra: {num} (have {count}, need {source_count})")

        return QAIssue(
            segment_id=segment_id,
            check="numbers",
            severity="warning",
            message=f"Number mismatch - {'; '.join(parts)}",
            source_excerpt=_excerpt(source),
            target_excerpt=_excerpt(target),
        )

    return None


def check_double_spaces(
    segment_id: str,
    target: str
) -> Optional[QAIssue]:
    """
    Check if target contains consecutive spaces.

    Only checks target since double spaces in source are usually intentional
    or part of the source document.
    """
    if not target:
        return None

    match = DOUBLE_SPACE_PATTERN.search(target)
    if match:
        # Find position for context
        pos = match.start()
        context_start = max(0, pos - 10)
        context_end = min(len(target), pos + 15)
        context = target[context_start:context_end]

        return QAIssue(
            segment_id=segment_id,
            check="double_spaces",
            severity="warning",
            message=f"Target contains double spaces",
            source_excerpt="",
            target_excerpt=f"...{context}...",
        )

    return None


def check_whitespace(
    segment_id: str,
    source: str,
    target: str
) -> Optional[QAIssue]:
    """
    Check if leading/trailing whitespace matches between source and target.

    Important for UI strings where spacing affects layout.
    """
    if not source and not target:
        return None

    # Handle empty strings
    source = source or ""
    target = target or ""

    source_leading = source != source.lstrip()
    source_trailing = source != source.rstrip()
    target_leading = target != target.lstrip()
    target_trailing = target != target.rstrip()

    issues = []

    if source_leading != target_leading:
        if source_leading:
            issues.append("source has leading whitespace, target doesn't")
        else:
            issues.append("target has leading whitespace, source doesn't")

    if source_trailing != target_trailing:
        if source_trailing:
            issues.append("source has trailing whitespace, target doesn't")
        else:
            issues.append("target has trailing whitespace, source doesn't")

    if issues:
        return QAIssue(
            segment_id=segment_id,
            check="whitespace",
            severity="warning",
            message=f"Whitespace mismatch: {'; '.join(issues)}",
            source_excerpt=_excerpt(source),
            target_excerpt=_excerpt(target),
        )

    return None


def check_brackets(
    segment_id: str,
    source: str,
    target: str
) -> Optional[QAIssue]:
    """
    Check if bracket/parenthesis counts match between source and target.

    Checks: () [] {} and their full-width equivalents.
    """
    if not source or not target:
        return None

    def count_brackets(text: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for char in text:
            if char in ALL_BRACKETS:
                counts[char] = counts.get(char, 0) + 1
        return counts

    source_counts = count_brackets(source)
    target_counts = count_brackets(target)

    if source_counts != target_counts:
        mismatches = []
        all_brackets = set(source_counts.keys()) | set(target_counts.keys())

        for bracket in sorted(all_brackets):
            src = source_counts.get(bracket, 0)
            tgt = target_counts.get(bracket, 0)
            if src != tgt:
                mismatches.append(f"'{bracket}': {src} vs {tgt}")

        return QAIssue(
            segment_id=segment_id,
            check="brackets",
            severity="warning",
            message=f"Bracket count mismatch - {', '.join(mismatches)}",
            source_excerpt=_excerpt(source),
            target_excerpt=_excerpt(target),
        )

    return None


def check_inconsistent_repetitions(
    segments: List[Dict[str, Any]]
) -> List[QAIssue]:
    """
    Check for segments with identical source text but different translations.

    Segments marked as repetitions (repetitions > 1) should generally have
    identical translations for consistency.

    Note: May have false positives in rare cases where intentional variation
    is desired.
    """
    issues = []

    # Group segments by source text
    source_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for segment in segments:
        # Only check segments that are marked as repetitions
        if segment.get('repetitions', 0) > 1:
            source = segment.get('source', '')
            if source:  # Skip empty sources
                source_groups[source].append(segment)

    # Check each group for inconsistent translations
    for source, group in source_groups.items():
        if len(group) < 2:
            continue

        # Get unique non-empty targets
        targets: Dict[str, List[str]] = defaultdict(list)
        for seg in group:
            target = seg.get('target', '')
            if target:  # Only consider non-empty targets
                targets[target].append(seg['segment_id'])

        # If we have multiple different translations, report it
        if len(targets) > 1:
            # Sort targets by frequency (most common first)
            sorted_targets = sorted(targets.items(), key=lambda x: -len(x[1]))

            # The most common translation
            most_common_target, most_common_ids = sorted_targets[0]

            # Report issues for less common translations
            for target, segment_ids in sorted_targets[1:]:
                for seg_id in segment_ids:
                    issues.append(QAIssue(
                        segment_id=seg_id,
                        check="inconsistent_repetitions",
                        severity="warning",
                        message=(
                            f"Repetition has different translation than {len(most_common_ids)} "
                            f"other segment(s) with same source"
                        ),
                        source_excerpt=_excerpt(source),
                        target_excerpt=_excerpt(target),
                    ))

    return issues


def load_glossary(glossary_path: str) -> List[Tuple[str, str]]:
    """
    Load terminology from a glossary file.

    Supports tab-delimited format: source_term<TAB>target_term
    Lines starting with # are comments. Empty lines are skipped.

    Args:
        glossary_path: Path to the glossary file

    Returns:
        List of (source_term, target_term) tuples
    """
    terms: List[Tuple[str, str]] = []
    path = Path(glossary_path)

    if not path.exists():
        return terms

    try:
        content = path.read_text(encoding='utf-8')
        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Parse tab-delimited format
            parts = line.split('\t')
            if len(parts) >= 2:
                source_term = parts[0].strip()
                target_term = parts[1].strip()
                if source_term and target_term:
                    terms.append((source_term, target_term))
            elif len(parts) == 1 and parts[0].strip():
                # Single term = must appear unchanged in target
                term = parts[0].strip()
                terms.append((term, term))

    except (IOError, UnicodeDecodeError):
        # If we can't read the file, return empty list
        pass

    return terms


def discover_glossary(sdlxliff_path: str) -> Optional[str]:
    """
    Auto-discover a glossary file near the SDLXLIFF file.

    Looks for common glossary filenames in the same directory:
    - glossary.tsv
    - glossary.txt
    - terminology.tsv
    - terminology.txt

    Args:
        sdlxliff_path: Path to the SDLXLIFF file

    Returns:
        Path to glossary file if found, None otherwise
    """
    sdlxliff_dir = Path(sdlxliff_path).parent

    candidates = [
        'glossary.tsv',
        'glossary.txt',
        'terminology.tsv',
        'terminology.txt',
    ]

    for candidate in candidates:
        glossary_path = sdlxliff_dir / candidate
        if glossary_path.exists():
            return str(glossary_path)

    return None


def check_terminology(
    segment_id: str,
    source: str,
    target: str,
    terms: List[Tuple[str, str]]
) -> List[QAIssue]:
    """
    Check that glossary terms from source appear correctly in target.

    Verifies both presence and frequency - if a term appears twice in source,
    it should appear twice in target.

    Args:
        segment_id: The segment ID
        source: Source text
        target: Target text
        terms: List of (source_term, target_term) tuples from glossary

    Returns:
        List of QAIssue for any missing or mismatched terms
    """
    issues: List[QAIssue] = []

    if not source or not target or not terms:
        return issues

    for source_term, target_term in terms:
        # Count occurrences of source term in source text
        source_count = source.count(source_term)
        if source_count > 0:
            # Count occurrences of target term in target text
            target_count = target.count(target_term)

            if target_count == 0:
                # Term completely missing
                msg = f"Term '{source_term}' found in source but '{target_term}' missing in target"
                if source_count > 1:
                    msg = f"Term '{source_term}' appears {source_count}x in source but '{target_term}' missing in target"
                issues.append(QAIssue(
                    segment_id=segment_id,
                    check="terminology",
                    severity="warning",
                    message=msg,
                    source_excerpt=_excerpt(source),
                    target_excerpt=_excerpt(target),
                ))
            elif target_count < source_count:
                # Term present but not enough times
                issues.append(QAIssue(
                    segment_id=segment_id,
                    check="terminology",
                    severity="warning",
                    message=f"Term count mismatch: '{source_term}' appears {source_count}x in source but '{target_term}' only {target_count}x in target",
                    source_excerpt=_excerpt(source),
                    target_excerpt=_excerpt(target),
                ))

    return issues


# Module-level cache for spellcheckers (one per language)
_spellcheckers: Dict[str, Any] = {}


def get_spellchecker(lang_code: str) -> Any:
    """
    Get or create a cached SpellChecker for the given language.

    Args:
        lang_code: pyspellchecker language code (e.g., 'de', 'en')

    Returns:
        SpellChecker instance for the language
    """
    if not SPELLCHECKER_AVAILABLE:
        return None

    if lang_code not in _spellcheckers:
        _spellcheckers[lang_code] = SpellChecker(language=lang_code)
    return _spellcheckers[lang_code]


def load_custom_dictionary(dict_path: str) -> Set[str]:
    """
    Load custom words from file (one word per line, # for comments).

    Args:
        dict_path: Path to the dictionary file

    Returns:
        Set of lowercase custom words
    """
    words: Set[str] = set()
    path = Path(dict_path)

    if not path.exists():
        return words

    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                words.add(line.lower())
    except (IOError, UnicodeDecodeError):
        pass

    return words


def discover_custom_dictionary(sdlxliff_path: str) -> Optional[str]:
    """
    Auto-discover custom dictionary file near the SDLXLIFF file.

    Looks for common dictionary filenames in the same directory:
    - dictionary.txt
    - custom_words.txt
    - spelling.txt

    Args:
        sdlxliff_path: Path to the SDLXLIFF file

    Returns:
        Path to dictionary file if found, None otherwise
    """
    sdlxliff_dir = Path(sdlxliff_path).parent

    candidates = [
        'dictionary.txt',
        'custom_words.txt',
        'spelling.txt',
    ]

    for candidate in candidates:
        dict_path = sdlxliff_dir / candidate
        if dict_path.exists():
            return str(dict_path)

    return None


def _check_spelling_yandex(
    segment_id: str,
    target: str,
    lang_code: str,
    custom_words: Optional[Set[str]] = None,
) -> List[QAIssue]:
    """
    Check spelling using Yandex Speller API.

    Yandex Speller has proper morphological dictionaries for Russian, Ukrainian,
    and English, providing much better accuracy than frequency-based spellcheckers.

    Args:
        segment_id: The segment ID
        target: Target text to check
        lang_code: Yandex language code ('ru', 'uk', 'en')
        custom_words: Optional set of custom words to ignore (lowercase)

    Returns:
        List of QAIssue for any misspelled words
    """
    issues: List[QAIssue] = []

    if not target:
        return issues

    # Yandex Speller API endpoint
    url = "https://speller.yandex.net/services/spellservice.json/checkText"

    # Yandex Speller options (additive bitmask):
    # IGNORE_DIGITS = 2 (skip words with numbers like "авп17х4534")
    # IGNORE_URLS = 4 (skip URLs, emails, filenames)
    # FIND_REPEAT_WORDS = 8 (flag repeated words)
    # IGNORE_CAPITALIZATION = 512 (ignore case errors)
    options = 2 + 4  # IGNORE_DIGITS + IGNORE_URLS

    # Sanitize text: replace special Unicode punctuation that breaks Yandex API
    # «» (Russian quotes) and — (em-dash) cause empty responses
    sanitized_target = target.replace('«', '"').replace('»', '"').replace('—', '-').replace('–', '-')

    # Prepare request
    params = urllib.parse.urlencode({
        'text': sanitized_target,
        'lang': lang_code,
        'options': options,
    })

    try:
        # Make API request (timeout 5 seconds)
        req = urllib.request.Request(f"{url}?{params}")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        # If API fails, return empty (don't block QA)
        return issues

    # Process response - array of error objects
    # Each error: {"code": 1, "pos": 0, "len": 14, "word": "синхрафазатрон", "s": ["синхрофазотрон"]}
    for error in data:
        word = error.get('word', '')
        suggestions = error.get('s', [])[:3]

        # Filter out custom dictionary words
        if custom_words and word.lower() in custom_words:
            continue

        suggestion_text = f" (suggestions: {', '.join(suggestions)})" if suggestions else ""
        issues.append(QAIssue(
            segment_id=segment_id,
            check="spelling",
            severity="warning",
            message=f"Possible misspelling: '{word}'{suggestion_text}",
            source_excerpt="",
            target_excerpt=_excerpt(target),
        ))

    return issues


def _check_spelling_pyspellchecker(
    segment_id: str,
    target: str,
    lang_code: str,
    custom_words: Optional[Set[str]] = None,
) -> List[QAIssue]:
    """
    Check spelling using pyspellchecker library.

    Works adequately for languages with simpler morphology (German, Spanish, etc.)
    but has limitations with highly inflected languages.

    Args:
        segment_id: The segment ID
        target: Target text to check
        lang_code: pyspellchecker language code ('de', 'es', 'fr', etc.)
        custom_words: Optional set of custom words to ignore (lowercase)

    Returns:
        List of QAIssue for any misspelled words
    """
    issues: List[QAIssue] = []

    if not target:
        return issues

    if not SPELLCHECKER_AVAILABLE:
        return issues

    spell = get_spellchecker(lang_code)
    if not spell:
        return issues

    # Extract words (Unicode-aware, skip single chars and pure numbers)
    words = re.findall(r'\b\w+\b', target, re.UNICODE)
    words = [w for w in words if len(w) > 1 and not w.isdigit()]

    # Find misspelled words
    misspelled = spell.unknown(words)

    # Filter out custom dictionary words
    if custom_words:
        misspelled = {w for w in misspelled if w.lower() not in custom_words}

    for word in misspelled:
        suggestions = list(spell.candidates(word) or [])[:3]
        suggestion_text = f" (suggestions: {', '.join(suggestions)})" if suggestions else ""
        issues.append(QAIssue(
            segment_id=segment_id,
            check="spelling",
            severity="warning",
            message=f"Possible misspelling: '{word}'{suggestion_text}",
            source_excerpt="",
            target_excerpt=_excerpt(target),
        ))

    return issues


def check_spelling(
    segment_id: str,
    target: str,
    target_lang: str,
    custom_words: Optional[Set[str]] = None,
) -> List[QAIssue]:
    """
    Check spelling in target text.

    Routes to appropriate spellcheck backend based on language:
    - Yandex Speller: Russian, Ukrainian, English (proper morphology)
    - pyspellchecker: German, Spanish, French, Italian, Portuguese, Dutch

    Args:
        segment_id: The segment ID
        target: Target text to check
        target_lang: BCP-47 language code (e.g., 'de-DE', 'ru-RU')
        custom_words: Optional set of custom words to ignore (lowercase)

    Returns:
        List of QAIssue for any misspelled words
    """
    if not target or not target_lang:
        return []

    config = get_spellcheck_config(target_lang)
    if not config:
        return []  # Language not supported

    backend, lang_code = config

    if backend == BACKEND_YANDEX:
        return _check_spelling_yandex(segment_id, target, lang_code, custom_words)
    elif backend == BACKEND_PYSPELLCHECKER:
        return _check_spelling_pyspellchecker(segment_id, target, lang_code, custom_words)
    else:
        return []


def run_qa_checks(
    segments: List[Dict[str, Any]],
    checks: Optional[List[str]] = None,
    glossary_terms: Optional[List[Tuple[str, str]]] = None,
    target_lang: Optional[str] = None,
    custom_words: Optional[Set[str]] = None,
) -> QAReport:
    """
    Run all QA checks on a list of segments.

    Args:
        segments: List of segment dictionaries from SDLXLIFFParser.extract_segments()
        checks: Optional list of check names to run. If None, runs default checks
                (spelling is OPT-IN and must be explicitly requested).
                Valid names: trailing_punctuation, numbers, double_spaces,
                            whitespace, brackets, inconsistent_repetitions,
                            terminology, spelling
        glossary_terms: Optional list of (source_term, target_term) tuples for
                       terminology checking. If provided and 'terminology' check
                       is enabled, verifies terms are preserved.
        target_lang: Optional target language code (e.g., 'de-DE') for spelling check.
                    Only needed if 'spelling' check is enabled.
        custom_words: Optional set of custom words to ignore during spelling check.
                     Words should be lowercase.

    Returns:
        QAReport with all issues found
    """
    # Default checks (spelling is OPT-IN, not included here)
    default_checks = {
        'trailing_punctuation',
        'numbers',
        'double_spaces',
        'whitespace',
        'brackets',
        'inconsistent_repetitions',
        'terminology',
    }

    # All available checks (includes opt-in checks)
    all_checks = default_checks | {'spelling'}

    if checks is None:
        enabled_checks = default_checks  # Use defaults (no spelling)
    else:
        enabled_checks = set(checks) & all_checks  # Use specified checks

    issues: List[QAIssue] = []
    segments_with_issues: Set[str] = set()

    # Per-segment checks
    for segment in segments:
        segment_id = segment.get('segment_id', '')
        source = segment.get('source', '')
        target = segment.get('target', '')

        segment_issues: List[QAIssue] = []

        if 'trailing_punctuation' in enabled_checks:
            issue = check_trailing_punctuation(segment_id, source, target)
            if issue:
                segment_issues.append(issue)

        if 'numbers' in enabled_checks:
            issue = check_numbers(segment_id, source, target)
            if issue:
                segment_issues.append(issue)

        if 'double_spaces' in enabled_checks:
            issue = check_double_spaces(segment_id, target)
            if issue:
                segment_issues.append(issue)

        if 'whitespace' in enabled_checks:
            issue = check_whitespace(segment_id, source, target)
            if issue:
                segment_issues.append(issue)

        if 'brackets' in enabled_checks:
            issue = check_brackets(segment_id, source, target)
            if issue:
                segment_issues.append(issue)

        if 'terminology' in enabled_checks and glossary_terms:
            term_issues = check_terminology(segment_id, source, target, glossary_terms)
            segment_issues.extend(term_issues)

        if 'spelling' in enabled_checks and target_lang:
            spelling_issues = check_spelling(segment_id, target, target_lang, custom_words)
            segment_issues.extend(spelling_issues)

        if segment_issues:
            segments_with_issues.add(segment_id)
            issues.extend(segment_issues)

    # Cross-segment checks
    if 'inconsistent_repetitions' in enabled_checks:
        rep_issues = check_inconsistent_repetitions(segments)
        for issue in rep_issues:
            segments_with_issues.add(issue.segment_id)
        issues.extend(rep_issues)

    # Build summary
    summary: Dict[str, int] = defaultdict(int)
    for issue in issues:
        summary[issue.check] += 1

    return QAReport(
        total_segments=len(segments),
        segments_checked=len(segments),
        segments_with_issues=len(segments_with_issues),
        issues=issues,
        summary=dict(summary),
    )


def _excerpt(text: str, max_len: int = 50, tail: bool = False) -> str:
    """
    Create a short excerpt from text for display in QA issues.

    Args:
        text: Full text
        max_len: Maximum length of excerpt
        tail: If True, show end of text; if False, show beginning

    Returns:
        Truncated text with ellipsis if needed
    """
    if not text:
        return ""

    if len(text) <= max_len:
        return text

    if tail:
        return "..." + text[-(max_len - 3):]
    else:
        return text[:max_len - 3] + "..."
