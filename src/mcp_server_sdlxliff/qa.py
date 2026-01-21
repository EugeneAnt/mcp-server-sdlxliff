"""
Quality Assurance checks for SDLXLIFF segments.

Provides stateless QA check functions that detect common translation issues:
- Trailing punctuation mismatches
- Missing/extra numbers
- Double spaces
- Leading/trailing whitespace mismatches
- Bracket/parenthesis mismatches
- Inconsistent repetitions
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


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
    Check if all numbers from source appear in target.

    Returns an issue if numbers don't match (missing or extra).
    Numbers are compared as sets, so order doesn't matter.
    """
    if not source or not target:
        return None

    source_numbers = set(NUMBER_PATTERN.findall(source))
    target_numbers = set(NUMBER_PATTERN.findall(target))

    if source_numbers != target_numbers:
        missing = source_numbers - target_numbers
        extra = target_numbers - source_numbers

        parts = []
        if missing:
            parts.append(f"missing: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"extra: {', '.join(sorted(extra))}")

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


def run_qa_checks(
    segments: List[Dict[str, Any]],
    checks: Optional[List[str]] = None
) -> QAReport:
    """
    Run all QA checks on a list of segments.

    Args:
        segments: List of segment dictionaries from SDLXLIFFParser.extract_segments()
        checks: Optional list of check names to run. If None, runs all checks.
                Valid names: trailing_punctuation, numbers, double_spaces,
                            whitespace, brackets, inconsistent_repetitions

    Returns:
        QAReport with all issues found
    """
    all_checks = {
        'trailing_punctuation',
        'numbers',
        'double_spaces',
        'whitespace',
        'brackets',
        'inconsistent_repetitions',
    }

    if checks is None:
        enabled_checks = all_checks
    else:
        enabled_checks = set(checks) & all_checks

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
