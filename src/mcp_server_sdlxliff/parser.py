"""
SDLXLIFF Parser Module

Handles parsing, reading, and writing SDLXLIFF files.
SDLXLIFF is an extension of XLIFF used by SDL Trados Studio.
"""

from lxml import etree
from copy import deepcopy
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import re
import logging

logger = logging.getLogger("sdlxliff-parser")


class SDLXLIFFParser:
    """Parser for SDLXLIFF files."""

    # Common XLIFF and SDL namespaces (class-level defaults)
    DEFAULT_NAMESPACES = {
        'xliff': 'urn:oasis:names:tc:xliff:document:1.2',
        'sdl': 'http://sdl.com/FileTypes/SdlXliff/1.0',
    }

    def __init__(self, file_path: str):
        """
        Initialize the parser with a file path.

        Args:
            file_path: Path to the SDLXLIFF file
        """
        self.file_path = Path(file_path)
        self.tree: Optional[etree._ElementTree] = None
        self.root: Optional[etree._Element] = None
        # Instance-level copy to avoid mutating class attribute
        self.namespaces: Dict[str, str] = dict(self.DEFAULT_NAMESPACES)
        # Storage for original mrk elements (deep copies for tag restoration)
        # Key: segment_id (mrk mid), Value: (trans_unit_id, deep copy of mrk element)
        self._original_mrk_elements: Dict[str, Tuple[str, etree._Element]] = {}
        self._load_file()

    # Maximum file size (50MB) - SDLXLIFF files are typically much smaller
    MAX_FILE_SIZE = 50 * 1024 * 1024

    def _load_file(self):
        """Load and parse the SDLXLIFF file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # Check file size to prevent memory exhaustion
        file_size = self.file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File too large: {file_size / (1024*1024):.1f}MB "
                f"(max: {self.MAX_FILE_SIZE / (1024*1024):.0f}MB)"
            )

        # Secure XML parser configuration
        parser = etree.XMLParser(
            remove_blank_text=False,
            strip_cdata=False,
            resolve_entities=False,  # Prevent XXE attacks
            no_network=True,         # Block external network access
            huge_tree=False,         # Prevent billion laughs / memory exhaustion
        )
        self.tree = etree.parse(str(self.file_path), parser)
        self.root = self.tree.getroot()

        # Update namespaces from the actual file
        self._update_namespaces()

    def _update_namespaces(self):
        """Extract and update namespaces from the XML file."""
        if self.root is not None:
            # Get all namespaces used in the document
            nsmap = self.root.nsmap
            if nsmap:
                # Update instance-level namespaces (not class attribute)
                for prefix, uri in nsmap.items():
                    if prefix is not None:
                        self.namespaces[prefix] = uri

    @staticmethod
    def _escape_xpath_value(value: str) -> str:
        """
        Escape a value for safe use in XPath queries.

        Handles quotes by using concat() when both quote types are present.

        Args:
            value: The string value to escape

        Returns:
            Escaped string safe for XPath attribute matching
        """
        if '"' not in value:
            return f'"{value}"'
        elif "'" not in value:
            return f"'{value}'"
        else:
            # Contains both quotes - use concat()
            parts = value.split('"')
            escaped = "concat(" + ", '\"', ".join(f'"{p}"' for p in parts) + ")"
            return escaped

    def _find_trans_unit_by_id(self, segment_id: str) -> Optional[etree._Element]:
        """
        Find a trans-unit element by segment ID using safe XPath.

        Args:
            segment_id: The segment ID to find

        Returns:
            The trans-unit element or None if not found
        """
        # For simple IDs without special characters, use direct XPath
        # For complex IDs, iterate to avoid XPath injection
        if '"' not in segment_id and "'" not in segment_id:
            trans_units = self.root.findall(
                f'.//xliff:trans-unit[@id="{segment_id}"]',
                self.namespaces
            )
            return trans_units[0] if trans_units else None
        else:
            # Iterate for safety with complex IDs
            for trans_unit in self.root.findall('.//xliff:trans-unit', self.namespaces):
                if trans_unit.get('id') == segment_id:
                    return trans_unit
            return None

    def _extract_segments_from_trans_unit(self, trans_unit: etree._Element) -> List[Dict[str, Any]]:
        """
        Extract all segments from a trans-unit element.

        In SDLXLIFF, each <mrk mtype="seg"> within target is a separate segment.
        The mrk mid corresponds to sdl:seg id for status/metadata.
        Source text comes from <seg-source> (segmented) when available.

        Args:
            trans_unit: The trans-unit XML element

        Returns:
            List of dictionaries with segment information including:
            - segment_id: mrk mid
            - trans_unit_id: parent trans-unit ID
            - source: clean source text
            - source_tagged: source text with tag placeholders
            - target: clean target text
            - target_tagged: target text with tag placeholders
            - has_tags: whether the segment contains inline tags
            - status: SDL confirmation level
            - locked: whether segment is locked
        """
        segments = []
        tu_id = trans_unit.get('id')

        # Get segmented source (seg-source) - preferred for aligned source/target
        seg_source_elem = trans_unit.find('xliff:seg-source', self.namespaces)

        # Build source text map from seg-source mrk elements (clean and tagged)
        source_map: Dict[str, Dict[str, Any]] = {}
        if seg_source_elem is not None:
            for mrk in seg_source_elem.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces):
                mid = mrk.get('mid')
                content = self._get_mrk_content_with_tags(mrk)
                source_map[mid] = {
                    'clean': content['clean_text'],
                    'tagged': content['tagged_text'],
                    'has_tags': content['has_tags'],
                }

        # Fallback: get unsegmented source
        source_elem = trans_unit.find('xliff:source', self.namespaces)
        fallback_source = self._get_text_content(source_elem) if source_elem is not None else ""

        # Get target element
        target_elem = trans_unit.find('xliff:target', self.namespaces)

        # Get seg-defs for status lookup
        seg_defs = trans_unit.find('sdl:seg-defs', self.namespaces)
        seg_map = {}
        if seg_defs is not None:
            for seg in seg_defs.findall('sdl:seg', self.namespaces):
                seg_id = seg.get('id')
                seg_map[seg_id] = {
                    'conf': seg.get('conf'),
                    'locked': seg.get('locked') == 'true'
                }

        # Extract each mrk segment from target
        if target_elem is not None:
            mrk_segments = target_elem.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces)

            if mrk_segments:
                for mrk in mrk_segments:
                    mid = mrk.get('mid')

                    # Extract target content with tags
                    target_content = self._get_mrk_content_with_tags(mrk)

                    # Store original mrk element for later restoration
                    self._original_mrk_elements[mid] = (tu_id, deepcopy(mrk))

                    # Get matching source from seg-source, or fallback to full source
                    source_info = source_map.get(mid, {
                        'clean': fallback_source,
                        'tagged': fallback_source,
                        'has_tags': False,
                    })

                    # Determine if segment has tags (in either source or target)
                    has_tags = source_info['has_tags'] or target_content['has_tags']

                    # Get status from seg-defs
                    seg_info = seg_map.get(mid, {})

                    segments.append({
                        'segment_id': mid,  # Use mrk mid as segment ID
                        'trans_unit_id': tu_id,  # Keep trans-unit ID for reference
                        'source': source_info['clean'],  # Clean text (existing behavior)
                        'source_tagged': source_info['tagged'],  # With placeholders
                        'target': target_content['clean_text'],  # Clean text (existing behavior)
                        'target_tagged': target_content['tagged_text'],  # With placeholders
                        'has_tags': has_tags,
                        'status': seg_info.get('conf'),
                        'locked': seg_info.get('locked', False),
                    })
            else:
                # No mrk segments - treat whole target as single segment
                segments.append({
                    'segment_id': tu_id,
                    'trans_unit_id': tu_id,
                    'source': fallback_source,
                    'source_tagged': fallback_source,
                    'target': self._get_text_content(target_elem),
                    'target_tagged': self._get_text_content(target_elem),
                    'has_tags': False,
                    'status': seg_map.get('1', {}).get('conf'),
                    'locked': seg_map.get('1', {}).get('locked', False),
                })
        else:
            # No target - return segment with empty target
            segments.append({
                'segment_id': tu_id,
                'trans_unit_id': tu_id,
                'source': fallback_source,
                'source_tagged': fallback_source,
                'target': '',
                'target_tagged': '',
                'has_tags': False,
                'status': None,
                'locked': False,
            })

        return segments

    def _get_mrk_text(self, mrk: etree._Element) -> str:
        """
        Extract text content from an mrk element, excluding nested mrk elements.

        Args:
            mrk: The mrk XML element

        Returns:
            Text content of the mrk (excluding x-sdl-location markers)
        """
        # Get direct text
        text = mrk.text or ""

        # Get tail text from children (but not nested mrk content)
        for child in mrk:
            # Skip x-sdl-location markers (they don't contain translatable text)
            if child.get('mtype') == 'x-sdl-location':
                if child.tail:
                    text += child.tail
            else:
                # For other elements, get their text content
                text += self._get_text_content(child)
                if child.tail:
                    text += child.tail

        return text.strip()

    def _get_text_content(self, element: etree._Element) -> str:
        """
        Extract text content from an element, handling mixed content.

        Args:
            element: XML element to extract text from

        Returns:
            Concatenated text content
        """
        if element is None:
            return ""

        # Get all text, including from child elements
        text_parts = []

        # Get element's direct text
        if element.text:
            text_parts.append(element.text)

        # Get text from all descendants
        for child in element:
            # Add child's text content recursively
            text_parts.append(self._get_text_content(child))
            # Add tail text (text after the child element)
            if child.tail:
                text_parts.append(child.tail)

        return ''.join(text_parts)

    def _get_mrk_content_with_tags(self, mrk: etree._Element) -> Dict[str, Any]:
        """
        Extract both clean text and tagged text with placeholders from an mrk element.

        Tag placeholders use format:
        - Paired tags: {id}text{/id}  (e.g., <g id="5">text</g> → {5}text{/5})
        - Self-closing: {x:id}        (e.g., <x id="5"/> → {x:5})

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

        def process_element(elem: etree._Element, is_root: bool = False) -> Tuple[str, str]:
            """
            Process an element recursively, returning (clean_text, tagged_text).

            Args:
                elem: Element to process
                is_root: Whether this is the root mrk element
            """
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

                if tag_id and local_name in ('g', 'x', 'bx', 'ex', 'ph', 'bpt', 'ept', 'it'):
                    # Store original element in tag map
                    tag_map[tag_id] = {
                        'element': deepcopy(child),
                        'tag_name': local_name,
                        'is_self_closing': local_name in ('x', 'bx', 'ex', 'ph'),
                    }

                    if local_name in ('x', 'bx', 'ex', 'ph'):
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

        clean_text, tagged_text = process_element(mrk, is_root=True)

        return {
            'clean_text': clean_text.strip(),
            'tagged_text': tagged_text.strip(),
            'tag_map': tag_map,
            'has_tags': len(tag_map) > 0,
        }

    def _parse_tagged_text(self, tagged_text: str) -> List[Dict[str, Any]]:
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

    def validate_tagged_text(self, segment_id: str, tagged_text: str) -> Dict[str, Any]:
        """
        Validate that tagged text contains all required tags from the original segment.

        Args:
            segment_id: The mrk mid of the segment
            tagged_text: The new text with placeholders

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

        # Get original tag map
        if segment_id not in self._original_mrk_elements:
            # Need to extract original element first
            mrk_result = self._find_mrk_by_mid(segment_id)
            if mrk_result is None:
                result['valid'] = False
                result['errors'].append(f"Segment '{segment_id}' not found")
                return result
            trans_unit, mrk = mrk_result
            original_content = self._get_mrk_content_with_tags(mrk)
            self._original_mrk_elements[segment_id] = (trans_unit.get('id'), deepcopy(mrk))
        else:
            # Get from cache
            _, original_mrk = self._original_mrk_elements[segment_id]
            original_content = self._get_mrk_content_with_tags(original_mrk)

        original_tag_map = original_content['tag_map']
        original_tag_ids = set(original_tag_map.keys())

        # Parse the new tagged text
        parsed = self._parse_tagged_text(tagged_text)

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
            result['errors'].append(f"Unclosed tags: {', '.join('{' + t + '}' for t in tag_stack)}")
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
        original_order = []
        new_order = []

        for item in self._parse_tagged_text(original_content['tagged_text']):
            if item['type'] in ('tag_open', 'self_closing'):
                original_order.append(item['tag_id'])

        for item in parsed:
            if item['type'] in ('tag_open', 'self_closing'):
                new_order.append(item['tag_id'])

        if original_order != new_order and result['valid']:
            result['warnings'].append(
                f"Tag order changed from original. This may be intentional for word order differences. "
                f"Original: {' '.join('{' + t + '}' for t in original_order)}, "
                f"New: {' '.join('{' + t + '}' for t in new_order)}"
            )

        return result

    def _build_mrk_from_tagged_text(
        self,
        segment_id: str,
        tagged_text: str,
        original_mrk: etree._Element
    ) -> etree._Element:
        """
        Build a new mrk element from tagged text using original element structure.

        Args:
            segment_id: The mrk mid
            tagged_text: Text with placeholders
            original_mrk: The original mrk element (for tag templates)

        Returns:
            New mrk element with reconstructed tags
        """
        # Get original tag map
        original_content = self._get_mrk_content_with_tags(original_mrk)
        tag_map = original_content['tag_map']

        # Create new mrk element with same attributes
        new_mrk = etree.Element(original_mrk.tag, attrib=dict(original_mrk.attrib), nsmap=original_mrk.nsmap)

        # Parse the tagged text
        parsed = self._parse_tagged_text(tagged_text)

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

    def extract_segments(self) -> List[Dict[str, Any]]:
        """
        Extract all translation segments from the SDLXLIFF file.

        In SDLXLIFF, each <mrk mtype="seg"> is a separate segment.
        segment_id is the mrk mid (globally unique number).

        Returns:
            List of dictionaries containing segment information:
            - segment_id: The mrk mid (unique segment identifier)
            - trans_unit_id: The parent trans-unit ID
            - source: Source text (shared across segments in same trans-unit)
            - target: Target text for this segment
            - status: SDL confirmation level (e.g., 'Translated', 'RejectedTranslation')
            - locked: Whether the segment is locked
        """
        segments = []

        # Find all trans-unit elements
        trans_units = self.root.findall('.//xliff:trans-unit', self.namespaces)

        for trans_unit in trans_units:
            segments.extend(self._extract_segments_from_trans_unit(trans_unit))

        return segments

    def _find_mrk_by_mid(self, mid: str) -> Optional[tuple]:
        """
        Find an mrk element by its mid attribute.

        Args:
            mid: The mrk mid to find

        Returns:
            Tuple of (trans_unit, mrk_element) or None if not found
        """
        for trans_unit in self.root.findall('.//xliff:trans-unit', self.namespaces):
            target = trans_unit.find('xliff:target', self.namespaces)
            if target is not None:
                for mrk in target.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces):
                    if mrk.get('mid') == mid:
                        return (trans_unit, mrk)
        return None

    def _find_sdl_seg_by_id(self, seg_id: str) -> Optional[etree._Element]:
        """
        Find an sdl:seg element by its id attribute.

        Args:
            seg_id: The sdl:seg id to find

        Returns:
            The sdl:seg element or None if not found
        """
        for seg in self.root.findall('.//sdl:seg', self.namespaces):
            if seg.get('id') == seg_id:
                return seg
        return None

    # Maximum segment text size (100KB) - segments are typically much smaller
    MAX_SEGMENT_TEXT_SIZE = 100 * 1024

    def update_segment(self, segment_id: str, target_text: str) -> bool:
        """
        Update a specific segment's target text and set status to RejectedTranslation.

        In SDLXLIFF, segment_id is the mrk mid (e.g., "1", "2", "42").
        This updates only the specific mrk element, preserving other segments.

        Args:
            segment_id: The mrk mid of the segment to update
            target_text: New target text for this segment

        Returns:
            True if segment was found and updated, False otherwise

        Raises:
            ValueError: If target_text exceeds maximum allowed size
        """
        # Validate input size to prevent DoS
        if len(target_text) > self.MAX_SEGMENT_TEXT_SIZE:
            raise ValueError(
                f"Target text too large: {len(target_text)} characters "
                f"(max: {self.MAX_SEGMENT_TEXT_SIZE})"
            )

        result = self._find_mrk_by_mid(segment_id)
        if result is None:
            return False

        trans_unit, mrk = result

        # Update mrk text - clear children but preserve the element structure
        for child in list(mrk):
            mrk.remove(child)
        mrk.text = target_text

        # Update SDL confirmation level for this specific segment
        sdl_seg = self._find_sdl_seg_by_id(segment_id)
        if sdl_seg is not None:
            sdl_seg.set('conf', 'RejectedTranslation')

        return True

    def set_segment_status(self, segment_id: str, status: str = 'RejectedTranslation') -> bool:
        """
        Update a segment's SDL confirmation level only (without changing text).

        Args:
            segment_id: The mrk mid of the segment to update
            status: SDL confirmation level (default: 'RejectedTranslation').
                    Valid values: Draft, Translated, RejectedTranslation,
                    ApprovedTranslation, RejectedSignOff, ApprovedSignOff

        Returns:
            True if segment was found and updated, False otherwise
        """
        sdl_seg = self._find_sdl_seg_by_id(segment_id)
        if sdl_seg is None:
            return False

        sdl_seg.set('conf', status)
        return True

    def update_segment_with_tags(
        self,
        segment_id: str,
        target_text: str,
        preserve_tags: bool = True
    ) -> Dict[str, Any]:
        """
        Update a segment's target text with tag preservation and validation.

        If preserve_tags is True and the text contains placeholders, the tags
        are validated and restored in the XML. If validation fails, the update
        is rejected with a detailed error report.

        Args:
            segment_id: The mrk mid of the segment to update
            target_text: New target text (with or without tag placeholders)
            preserve_tags: If True, validate and restore tags from placeholders

        Returns:
            Dictionary with:
            - success: True if update succeeded
            - message: Success/error message
            - warnings: List of warning messages
            - validation: Validation details (if preserve_tags=True)
        """
        result = {
            'success': False,
            'message': '',
            'warnings': [],
            'validation': None,
        }

        # Validate input size
        if len(target_text) > self.MAX_SEGMENT_TEXT_SIZE:
            result['message'] = (
                f"Target text too large: {len(target_text)} characters "
                f"(max: {self.MAX_SEGMENT_TEXT_SIZE})"
            )
            return result

        # Find the mrk element
        mrk_result = self._find_mrk_by_mid(segment_id)
        if mrk_result is None:
            result['message'] = f"Segment '{segment_id}' not found"
            return result

        trans_unit, mrk = mrk_result

        # Check if segment has tags and we should preserve them
        if preserve_tags:
            # Ensure we have the original element cached
            if segment_id not in self._original_mrk_elements:
                self._original_mrk_elements[segment_id] = (trans_unit.get('id'), deepcopy(mrk))

            _, original_mrk = self._original_mrk_elements[segment_id]
            original_content = self._get_mrk_content_with_tags(original_mrk)

            # Check if the text appears to contain placeholder tags
            has_placeholders = bool(re.search(r'\{/?(\d+|x:\d+)\}', target_text))

            if original_content['has_tags']:
                if has_placeholders:
                    # Validate the tagged text
                    validation = self.validate_tagged_text(segment_id, target_text)
                    result['validation'] = validation
                    result['warnings'] = validation.get('warnings', [])

                    if not validation['valid']:
                        result['message'] = (
                            f"Tag validation failed: {'; '.join(validation['errors'])}. "
                            f"Original tagged text: {original_content['tagged_text']}"
                        )
                        return result

                    # Build new mrk element with restored tags
                    new_mrk = self._build_mrk_from_tagged_text(
                        segment_id, target_text, original_mrk
                    )

                    # Replace the mrk element in the tree
                    parent = mrk.getparent()
                    if parent is not None:
                        index = list(parent).index(mrk)
                        parent.remove(mrk)
                        parent.insert(index, new_mrk)

                    # Log warning if tag order changed
                    if validation.get('warnings'):
                        for warning in validation['warnings']:
                            logger.warning(f"Segment {segment_id}: {warning}")
                else:
                    # Original has tags but input doesn't have placeholders
                    result['message'] = (
                        f"Segment contains formatting tags but no placeholders were provided. "
                        f"Expected format: {original_content['tagged_text']}. "
                        f"If you want to remove all tags, set preserve_tags=False."
                    )
                    return result
            else:
                # No tags in original - just update text directly
                for child in list(mrk):
                    mrk.remove(child)
                mrk.text = target_text
        else:
            # preserve_tags=False - just replace with plain text
            for child in list(mrk):
                mrk.remove(child)
            mrk.text = target_text

        # Update SDL confirmation level
        sdl_seg = self._find_sdl_seg_by_id(segment_id)
        if sdl_seg is not None:
            sdl_seg.set('conf', 'RejectedTranslation')

        result['success'] = True
        result['message'] = f"Successfully updated segment '{segment_id}'"
        return result

    def save(self, output_path: Optional[str] = None):
        """
        Save the modified SDLXLIFF file.

        Preserves original file characteristics:
        - UTF-8 BOM if present in original
        - Original XML declaration format
        - Minimal structure changes

        Args:
            output_path: Optional output path. If None, overwrites the original file.
        """
        if output_path is None:
            output_path = str(self.file_path)

        # Check if original file had BOM
        has_bom = False
        try:
            with open(self.file_path, 'rb') as f:
                has_bom = f.read(3) == b'\xef\xbb\xbf'
        except (IOError, OSError):
            pass

        # Generate XML content
        xml_content = etree.tostring(
            self.root,
            encoding='unicode',
            pretty_print=False,
        )

        # Write with original XML declaration format and BOM
        with open(output_path, 'wb') as f:
            if has_bom:
                f.write(b'\xef\xbb\xbf')
            # Use original declaration format (double quotes, lowercase)
            f.write(b'<?xml version="1.0" encoding="utf-8"?>')
            f.write(xml_content.encode('utf-8'))

    def get_segment_by_id(self, segment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific segment by its mrk mid.

        Args:
            segment_id: The mrk mid to retrieve

        Returns:
            Dictionary with segment information including:
            - segment_id: mrk mid
            - trans_unit_id: parent trans-unit ID
            - source: clean source text
            - source_tagged: source text with tag placeholders
            - target: clean target text
            - target_tagged: target text with tag placeholders
            - has_tags: whether the segment contains inline tags
            - status: SDL confirmation level
            - locked: whether segment is locked
            Returns None if not found.
        """
        result = self._find_mrk_by_mid(segment_id)
        if result is None:
            return None

        trans_unit, mrk = result
        tu_id = trans_unit.get('id')

        # Get target content with tags
        target_content = self._get_mrk_content_with_tags(mrk)

        # Cache the original mrk if not already cached
        if segment_id not in self._original_mrk_elements:
            self._original_mrk_elements[segment_id] = (tu_id, deepcopy(mrk))

        # Get source from seg-source if available
        seg_source_elem = trans_unit.find('xliff:seg-source', self.namespaces)
        source_content = {
            'clean_text': '',
            'tagged_text': '',
            'has_tags': False,
        }

        if seg_source_elem is not None:
            for source_mrk in seg_source_elem.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces):
                if source_mrk.get('mid') == segment_id:
                    source_content = self._get_mrk_content_with_tags(source_mrk)
                    break

        # Fallback to unsegmented source
        if not source_content['clean_text']:
            source_elem = trans_unit.find('xliff:source', self.namespaces)
            if source_elem is not None:
                source_text = self._get_text_content(source_elem)
                source_content = {
                    'clean_text': source_text,
                    'tagged_text': source_text,
                    'has_tags': False,
                }

        # Determine if segment has tags
        has_tags = source_content['has_tags'] or target_content['has_tags']

        # Get status from sdl:seg
        sdl_seg = self._find_sdl_seg_by_id(segment_id)
        status = sdl_seg.get('conf') if sdl_seg is not None else None
        locked = sdl_seg.get('locked') == 'true' if sdl_seg is not None else False

        return {
            'segment_id': segment_id,
            'trans_unit_id': tu_id,
            'source': source_content['clean_text'],
            'source_tagged': source_content['tagged_text'],
            'target': target_content['clean_text'],
            'target_tagged': target_content['tagged_text'],
            'has_tags': has_tags,
            'status': status,
            'locked': locked,
        }

    def get_file_metadata(self) -> Dict[str, Any]:
        """
        Extract file-level metadata from the SDLXLIFF file.

        Returns:
            Dictionary with metadata:
            - source_language: Source language code (e.g., 'en-US')
            - target_language: Target language code (e.g., 'de-DE')
        """
        metadata: Dict[str, Any] = {
            'source_language': None,
            'target_language': None,
        }

        # Find the file element (there's usually one per SDLXLIFF)
        file_elem = self.root.find('.//xliff:file', self.namespaces)
        if file_elem is not None:
            metadata['source_language'] = file_elem.get('source-language')
            metadata['target_language'] = file_elem.get('target-language')

        return metadata

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the SDLXLIFF file.

        Counts each mrk segment (not trans-units) for accurate statistics.

        Returns:
            Dictionary with statistics:
            - source_language: Source language code
            - target_language: Target language code
            - total_segments: Total number of mrk segments
            - status_counts: Count of segments by SDL confirmation level
            - locked_count: Number of locked segments
        """
        # Get file metadata first
        metadata = self.get_file_metadata()

        status_counts: Dict[str, int] = {}
        locked_count = 0
        total = 0

        # Count each sdl:seg (corresponds to each mrk)
        for seg in self.root.findall('.//sdl:seg', self.namespaces):
            total += 1

            status = seg.get('conf')
            status_key = status or 'unknown'
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            if seg.get('locked') == 'true':
                locked_count += 1

        return {
            'source_language': metadata['source_language'],
            'target_language': metadata['target_language'],
            'total_segments': total,
            'status_counts': status_counts,
            'locked_count': locked_count,
        }