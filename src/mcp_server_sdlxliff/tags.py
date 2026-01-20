"""
Tag handling for SDLXLIFF segments.

Provides functions for extracting, validating, and reconstructing inline
formatting tags in translation segments.

Tag placeholder format:
- Paired tags: {id}text{/id}  (e.g., <g id="5">text</g> → {5}text{/5})
- Self-closing: {x:id}        (e.g., <x id="5"/> → {x:5})
"""

import re
from copy import deepcopy
from typing import Any, Dict, List, Tuple

from lxml import etree

from .constants import INLINE_TAG_NAMES, SELF_CLOSING_TAG_NAMES


def extract_content_with_tags(mrk: etree._Element) -> Dict[str, Any]:
    """
    Extract both clean text and tagged text with placeholders from an mrk element.

    Args:
        mrk: The mrk XML element

    Returns:
        Dictionary with:
        - clean_text: Plain text without any tags
        - tagged_text: Text with placeholders for tags
        - tag_map: Mapping of tag IDs to their original elements
        - has_tags: Whether any inline tags were found
    """
    tag_map: Dict[str, Dict[str, Any]] = {}

    def process_element(elem: etree._Element) -> Tuple[str, str]:
        """Process an element recursively, returning (clean_text, tagged_text)."""
        clean_parts = []
        tagged_parts = []

        # Get element's direct text
        if elem.text:
            clean_parts.append(elem.text)
            tagged_parts.append(elem.text)

        # Process children
        for child in elem:
            # Skip x-sdl-location markers (they don't contain translatable text)
            if child.get('mtype') == 'x-sdl-location':
                if child.tail:
                    clean_parts.append(child.tail)
                    tagged_parts.append(child.tail)
                continue

            # Get tag ID for inline formatting elements
            tag_id = child.get('id')
            local_name = etree.QName(child.tag).localname if child.tag else None

            if tag_id and local_name in INLINE_TAG_NAMES:
                # Store original element in tag map
                tag_map[tag_id] = {
                    'element': deepcopy(child),
                    'tag_name': local_name,
                    'is_self_closing': local_name in SELF_CLOSING_TAG_NAMES,
                }

                if local_name in SELF_CLOSING_TAG_NAMES:
                    # Self-closing tags
                    tagged_parts.append(f'{{x:{tag_id}}}')
                    # Self-closing tags don't have content but might have tail
                else:
                    # Paired tags (g, bpt, ept, it)
                    child_clean, child_tagged = process_element(child)
                    clean_parts.append(child_clean)
                    tagged_parts.append(f'{{{tag_id}}}{child_tagged}{{/{tag_id}}}')
            else:
                # Other elements - process recursively
                child_clean, child_tagged = process_element(child)
                clean_parts.append(child_clean)
                tagged_parts.append(child_tagged)

            # Add tail text (text after the child element)
            if child.tail:
                clean_parts.append(child.tail)
                tagged_parts.append(child.tail)

        return ''.join(clean_parts), ''.join(tagged_parts)

    clean_text, tagged_text = process_element(mrk)

    return {
        'clean_text': clean_text.strip(),
        'tagged_text': tagged_text.strip(),
        'tag_map': tag_map,
        'has_tags': len(tag_map) > 0,
    }


def parse_tagged_text(tagged_text: str) -> List[Dict[str, Any]]:
    """
    Parse tagged text with placeholders into a structured list.

    Args:
        tagged_text: Text with placeholders like {5}text{/5} or {x:5}

    Returns:
        List of parsed elements, each with:
        - type: 'text', 'tag_open', 'tag_close', or 'self_closing'
        - content: The text content (for 'text' type)
        - tag_id: The tag ID (for tag types)
    """
    result = []
    # Pattern matches: {id}, {/id}, {x:id}, or plain text
    pattern = r'\{(/?\d+|x:\d+)\}|([^{}]+)'

    for match in re.finditer(pattern, tagged_text):
        tag_match, text_match = match.groups()

        if text_match:
            result.append({'type': 'text', 'content': text_match})
        elif tag_match:
            if tag_match.startswith('/'):
                # Closing tag
                result.append({'type': 'tag_close', 'tag_id': tag_match[1:]})
            elif tag_match.startswith('x:'):
                # Self-closing tag
                result.append({'type': 'self_closing', 'tag_id': tag_match[2:]})
            else:
                # Opening tag
                result.append({'type': 'tag_open', 'tag_id': tag_match})

    return result


def validate_tags(
    tagged_text: str,
    original_tag_map: Dict[str, Dict[str, Any]],
    original_tagged_text: str = ""
) -> Dict[str, Any]:
    """
    Validate that tagged text contains all required tags from the original.

    Args:
        tagged_text: The new text with placeholders
        original_tag_map: Tag map from the original segment
        original_tagged_text: Original tagged text (for order comparison)

    Returns:
        Dictionary with:
        - valid: True if validation passed
        - errors: List of validation error messages
        - warnings: List of warning messages (e.g., tag order changes)
        - missing_tags: List of tag IDs that are missing
        - extra_tags: List of tag IDs that weren't in original
    """
    result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'missing_tags': [],
        'extra_tags': [],
    }

    original_tag_ids = set(original_tag_map.keys())

    # Parse the new tagged text
    parsed = parse_tagged_text(tagged_text)

    # Collect tags from parsed text
    new_tag_ids = set()
    tag_stack = []  # Track open/close pairing

    for item in parsed:
        if item['type'] == 'tag_open':
            tag_id = item['tag_id']
            new_tag_ids.add(tag_id)
            tag_stack.append(tag_id)
        elif item['type'] == 'tag_close':
            tag_id = item['tag_id']
            new_tag_ids.add(tag_id)
            if tag_stack and tag_stack[-1] == tag_id:
                tag_stack.pop()
            else:
                result['errors'].append(f"Mismatched closing tag {{/{tag_id}}}")
                result['valid'] = False
        elif item['type'] == 'self_closing':
            tag_id = item['tag_id']
            new_tag_ids.add(tag_id)

    # Check for unclosed tags
    if tag_stack:
        result['errors'].append(
            f"Unclosed tags: {', '.join('{' + t + '}' for t in tag_stack)}"
        )
        result['valid'] = False

    # Check for missing tags
    missing = original_tag_ids - new_tag_ids
    if missing:
        result['missing_tags'] = list(missing)
        result['errors'].append(
            f"Missing tags: {', '.join('{' + t + '}' for t in sorted(missing))}. "
            f"All original tags must be preserved in the translation."
        )
        result['valid'] = False

    # Check for extra tags (not in original)
    extra = new_tag_ids - original_tag_ids
    if extra:
        result['extra_tags'] = list(extra)
        result['errors'].append(
            f"Unknown tags: {', '.join('{' + t + '}' for t in sorted(extra))}. "
            f"Only tags from the original segment can be used."
        )
        result['valid'] = False

    # Check tag order (warning only, as order can legitimately change)
    if original_tagged_text and result['valid']:
        original_order = []
        new_order = []

        for item in parse_tagged_text(original_tagged_text):
            if item['type'] in ('tag_open', 'self_closing'):
                original_order.append(item['tag_id'])

        for item in parsed:
            if item['type'] in ('tag_open', 'self_closing'):
                new_order.append(item['tag_id'])

        if original_order != new_order:
            result['warnings'].append(
                f"Tag order changed from original. This may be intentional for "
                f"word order differences. "
                f"Original: {' '.join('{' + t + '}' for t in original_order)}, "
                f"New: {' '.join('{' + t + '}' for t in new_order)}"
            )

    return result


def build_mrk_with_tags(
    tagged_text: str,
    original_mrk: etree._Element,
    tag_map: Dict[str, Dict[str, Any]]
) -> etree._Element:
    """
    Build a new mrk element from tagged text using original element structure.

    Args:
        tagged_text: Text with placeholders
        original_mrk: The original mrk element (for attributes)
        tag_map: Mapping of tag IDs to original element info

    Returns:
        New mrk element with reconstructed tags
    """
    # Create new mrk element with same attributes
    new_mrk = etree.Element(
        original_mrk.tag,
        attrib=dict(original_mrk.attrib),
        nsmap=original_mrk.nsmap
    )

    # Parse the tagged text
    parsed = parse_tagged_text(tagged_text)

    # Build tree structure
    current_element = new_mrk
    element_stack = [new_mrk]

    for item in parsed:
        if item['type'] == 'text':
            # Add text to current element
            if len(current_element) == 0:
                # No children yet, add to element's text
                current_element.text = (current_element.text or '') + item['content']
            else:
                # Has children, add to last child's tail
                last_child = current_element[-1]
                last_child.tail = (last_child.tail or '') + item['content']

        elif item['type'] == 'tag_open':
            tag_id = item['tag_id']
            if tag_id in tag_map:
                # Create new element based on original
                orig_elem = tag_map[tag_id]['element']
                new_elem = etree.SubElement(
                    current_element,
                    orig_elem.tag,
                    attrib=dict(orig_elem.attrib),
                    nsmap=orig_elem.nsmap
                )
                element_stack.append(new_elem)
                current_element = new_elem

        elif item['type'] == 'tag_close':
            if len(element_stack) > 1:
                element_stack.pop()
                current_element = element_stack[-1]

        elif item['type'] == 'self_closing':
            tag_id = item['tag_id']
            if tag_id in tag_map:
                orig_elem = tag_map[tag_id]['element']
                etree.SubElement(
                    current_element,
                    orig_elem.tag,
                    attrib=dict(orig_elem.attrib),
                    nsmap=orig_elem.nsmap
                )

    return new_mrk