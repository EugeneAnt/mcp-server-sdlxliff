"""
SDLXLIFF Parser Module

Handles parsing, reading, and writing SDLXLIFF files.
SDLXLIFF is an extension of XLIFF used by SDL Trados Studio.
"""

import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

from .constants import DEFAULT_NAMESPACES, MAX_FILE_SIZE, MAX_SEGMENT_TEXT_SIZE
from .io import load_sdlxliff, save_sdlxliff
from .tags import (
    build_mrk_with_tags,
    extract_content_with_tags,
    parse_tagged_text,
    validate_tags,
)

logger = logging.getLogger("sdlxliff-parser")


class SDLXLIFFParser:
    """Parser for SDLXLIFF files."""

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
        self.namespaces: Dict[str, str] = dict(DEFAULT_NAMESPACES)
        # Storage for original mrk elements (deep copies for tag restoration)
        # Key: segment_id (mrk mid), Value: (trans_unit_id, deep copy of mrk element)
        self._original_mrk_elements: Dict[str, Tuple[str, etree._Element]] = {}
        # Segment indices for O(1) lookup (built after loading)
        # Maps mrk mid -> (trans_unit, mrk element)
        self._segment_index: Dict[str, Tuple[etree._Element, etree._Element]] = {}
        # Maps sdl:seg id -> sdl:seg element
        self._sdl_seg_index: Dict[str, etree._Element] = {}
        # Repetition index: maps (tu_id, seg_id) -> count of repetitions
        self._repetition_counts: Dict[Tuple[str, str], int] = {}
        self._load_file()
        self._build_segment_index()
        self._build_repetition_index()

    def _load_file(self):
        """Load and parse the SDLXLIFF file."""
        self.tree, self.root = load_sdlxliff(self.file_path)
        self._update_namespaces()

    def _update_namespaces(self):
        """Extract and update namespaces from the XML file."""
        if self.root is not None:
            nsmap = self.root.nsmap
            if nsmap:
                for prefix, uri in nsmap.items():
                    if prefix is not None:
                        self.namespaces[prefix] = uri

    def _build_segment_index(self):
        """
        Build O(1) lookup indices for segments.

        Creates two indices:
        - _segment_index: Maps mrk mid -> (trans_unit, mrk element) for target segments
        - _sdl_seg_index: Maps sdl:seg id -> sdl:seg element for status/metadata
        """
        self._segment_index.clear()
        self._sdl_seg_index.clear()

        # Build mrk segment index from trans-units
        for trans_unit in self.root.findall('.//xliff:trans-unit', self.namespaces):
            target = trans_unit.find('xliff:target', self.namespaces)
            if target is not None:
                for mrk in target.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces):
                    mid = mrk.get('mid')
                    if mid:
                        self._segment_index[mid] = (trans_unit, mrk)

        # Build sdl:seg index
        for seg in self.root.findall('.//sdl:seg', self.namespaces):
            seg_id = seg.get('id')
            if seg_id:
                self._sdl_seg_index[seg_id] = seg

        logger.debug(
            f"Built segment index: {len(self._segment_index)} mrk segments, "
            f"{len(self._sdl_seg_index)} sdl:seg elements"
        )

    def _build_repetition_index(self):
        """
        Build repetition count index from sdl:rep-defs.

        Parses the <rep-defs> section in <doc-info> to count how many segments
        share the same source text. The count is stored per (tu_id, seg_id) tuple.

        Structure in SDLXLIFF:
        <doc-info>
          <rep-defs>
            <rep-def id="hash123">
              <entry tu="tu-guid-1" seg="5"/>
              <entry tu="tu-guid-2" seg="14"/>
            </rep-def>
          </rep-defs>
        </doc-info>
        """
        self._repetition_counts.clear()

        # Find rep-defs section (inside doc-info)
        rep_defs = self.root.find('.//sdl:rep-defs', self.namespaces)
        if rep_defs is None:
            return

        # Process each repetition group
        for rep_def in rep_defs.findall('sdl:rep-def', self.namespaces):
            entries = rep_def.findall('sdl:entry', self.namespaces)
            count = len(entries)

            if count > 1:
                # Store count for each segment in the group
                for entry in entries:
                    tu_id = entry.get('tu')
                    seg_id = entry.get('seg')
                    if tu_id and seg_id:
                        self._repetition_counts[(tu_id, seg_id)] = count

        logger.debug(f"Built repetition index: {len(self._repetition_counts)} repeated segments")

    def _find_mrk_by_mid(self, mid: str) -> Optional[Tuple[etree._Element, etree._Element]]:
        """
        Find an mrk element by its mid attribute using O(1) index lookup.

        Args:
            mid: The mrk mid to find

        Returns:
            Tuple of (trans_unit, mrk_element) or None if not found
        """
        return self._segment_index.get(mid)

    def _find_sdl_seg_by_id(self, seg_id: str) -> Optional[etree._Element]:
        """
        Find an sdl:seg element by its id attribute using O(1) index lookup.

        Args:
            seg_id: The sdl:seg id to find

        Returns:
            The sdl:seg element or None if not found
        """
        return self._sdl_seg_index.get(seg_id)

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

        text_parts = []
        if element.text:
            text_parts.append(element.text)

        for child in element:
            text_parts.append(self._get_text_content(child))
            if child.tail:
                text_parts.append(child.tail)

        return ''.join(text_parts)

    def _get_base_segment_id(self, segment_id: str) -> str:
        """
        Extract the base segment ID for split segments.

        When a segment is manually split in Trados, it gets IDs like:
        - Original: "81"
        - Split: "81_x0020_a", "81_x0020_b", etc.

        The sdl:seg-defs only contains the original ID, so we need to
        extract it for status lookup.

        Args:
            segment_id: The mrk mid (may be split like "81_x0020_a")

        Returns:
            Base segment ID (e.g., "81" for both "81" and "81_x0020_a")
        """
        # Split segments have format: {id}_x0020_{letter}
        if '_x0020_' in segment_id:
            return segment_id.split('_x0020_')[0]
        return segment_id

    def _extract_segments_from_trans_unit(self, trans_unit: etree._Element) -> List[Dict[str, Any]]:
        """
        Extract all segments from a trans-unit element.

        In SDLXLIFF, each <mrk mtype="seg"> within target is a separate segment.
        The mrk mid corresponds to sdl:seg id for status/metadata.
        Source text comes from <seg-source> (segmented) when available.

        Args:
            trans_unit: The trans-unit XML element

        Returns:
            List of dictionaries with segment information
        """
        segments = []
        tu_id = trans_unit.get('id')

        # Get segmented source (seg-source) - preferred for aligned source/target
        seg_source_elem = trans_unit.find('xliff:seg-source', self.namespaces)

        # Build source text map from seg-source mrk elements
        source_map: Dict[str, Dict[str, Any]] = {}
        if seg_source_elem is not None:
            for mrk in seg_source_elem.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces):
                mid = mrk.get('mid')
                content = extract_content_with_tags(mrk)
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
                # Parse percent as integer if present
                percent_str = seg.get('percent')
                percent = int(percent_str) if percent_str else None
                # text-match="SourceAndTarget" indicates Context Match (CM)
                text_match = seg.get('text-match')
                seg_map[seg_id] = {
                    'conf': seg.get('conf'),
                    'locked': seg.get('locked') == 'true',
                    'percent': percent,
                    'origin': seg.get('origin'),
                    'text_match': text_match,
                }

        # Extract each mrk segment from target
        if target_elem is not None:
            mrk_segments = target_elem.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces)

            if mrk_segments:
                for mrk in mrk_segments:
                    mid = mrk.get('mid')

                    # Extract target content with tags
                    target_content = extract_content_with_tags(mrk)

                    # Store original mrk element for later restoration
                    self._original_mrk_elements[mid] = (tu_id, deepcopy(mrk))

                    # Get matching source from seg-source, or fallback to full source
                    source_info = source_map.get(mid, {
                        'clean': fallback_source,
                        'tagged': fallback_source,
                        'has_tags': False,
                    })

                    # Determine if segment has tags
                    has_tags = source_info['has_tags'] or target_content['has_tags']

                    # Get status from seg-defs (use base ID for split segments)
                    base_id = self._get_base_segment_id(mid)
                    seg_info = seg_map.get(mid) or seg_map.get(base_id, {})

                    segment_data = {
                        'segment_id': mid,
                        'trans_unit_id': tu_id,
                        'source': source_info['clean'],
                        'source_tagged': source_info['tagged'],
                        'target': target_content['clean_text'],
                        'target_tagged': target_content['tagged_text'],
                        'has_tags': has_tags,
                        'status': seg_info.get('conf'),
                        'locked': seg_info.get('locked', False),
                    }

                    # Add percent only when present (to minimize token overhead)
                    percent = seg_info.get('percent')
                    if percent is not None:
                        segment_data['percent'] = percent

                    # Add origin only when present (to minimize token overhead)
                    origin = seg_info.get('origin')
                    if origin:
                        segment_data['origin'] = origin

                    # Add text_match for Context Match detection (CM = "SourceAndTarget")
                    text_match = seg_info.get('text_match')
                    if text_match:
                        segment_data['text_match'] = text_match

                    # Add repetitions count only when > 1 (to minimize token overhead)
                    rep_count = self._repetition_counts.get((tu_id, mid))
                    if rep_count and rep_count > 1:
                        segment_data['repetitions'] = rep_count

                    segments.append(segment_data)
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

    def extract_segments(self) -> List[Dict[str, Any]]:
        """
        Extract all translation segments from the SDLXLIFF file.

        Filters out non-translatable trans-units:
        - Those with translate="no" attribute (explicitly non-translatable)
        - Those without sdl:seg-defs element (structural placeholders with no
          translation metadata, common in IDML-derived files)

        This matches Trados Studio behavior when "Display segments with
        translate='no' as locked content" setting is disabled.

        Returns:
            List of dictionaries containing segment information
        """
        segments = []
        trans_units = self.root.findall('.//xliff:trans-unit', self.namespaces)

        for trans_unit in trans_units:
            # Skip explicitly non-translatable trans-units
            if trans_unit.get('translate') == 'no':
                continue

            # Skip trans-units without translation metadata (structural elements)
            # These are IDML placeholders with no actual text content
            seg_defs = trans_unit.find('sdl:seg-defs', self.namespaces)
            if seg_defs is None:
                continue

            segments.extend(self._extract_segments_from_trans_unit(trans_unit))

        return segments

    def validate_tagged_text(self, segment_id: str, tagged_text: str) -> Dict[str, Any]:
        """
        Validate that tagged text contains all required tags from the original segment.

        Args:
            segment_id: The mrk mid of the segment
            tagged_text: The new text with placeholders

        Returns:
            Validation result dictionary
        """
        # Get original tag map
        if segment_id not in self._original_mrk_elements:
            mrk_result = self._find_mrk_by_mid(segment_id)
            if mrk_result is None:
                return {
                    'valid': False,
                    'errors': [f"Segment '{segment_id}' not found"],
                    'warnings': [],
                    'missing_tags': [],
                    'extra_tags': [],
                }
            trans_unit, mrk = mrk_result
            self._original_mrk_elements[segment_id] = (trans_unit.get('id'), deepcopy(mrk))

        _, original_mrk = self._original_mrk_elements[segment_id]
        original_content = extract_content_with_tags(original_mrk)

        return validate_tags(
            tagged_text,
            original_content['tag_map'],
            original_content['tagged_text']
        )

    def update_segment(self, segment_id: str, target_text: str) -> bool:
        """
        Update a specific segment's target text and set status to RejectedTranslation.

        Args:
            segment_id: The mrk mid of the segment to update
            target_text: New target text for this segment

        Returns:
            True if segment was found and updated, False otherwise

        Raises:
            ValueError: If target_text exceeds maximum allowed size
        """
        if len(target_text) > MAX_SEGMENT_TEXT_SIZE:
            raise ValueError(
                f"Target text too large: {len(target_text)} characters "
                f"(max: {MAX_SEGMENT_TEXT_SIZE})"
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
            status: SDL confirmation level

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

        Args:
            segment_id: The mrk mid of the segment to update
            target_text: New target text (with or without tag placeholders)
            preserve_tags: If True, validate and restore tags from placeholders

        Returns:
            Dictionary with success status, message, warnings, and validation details
        """
        result = {
            'success': False,
            'message': '',
            'warnings': [],
            'validation': None,
        }

        # Validate input size
        if len(target_text) > MAX_SEGMENT_TEXT_SIZE:
            result['message'] = (
                f"Target text too large: {len(target_text)} characters "
                f"(max: {MAX_SEGMENT_TEXT_SIZE})"
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
            original_content = extract_content_with_tags(original_mrk)

            # Check if the text appears to contain placeholder tags
            has_placeholders = bool(re.search(r'\{/?(\d+|x:\d+)\}', target_text))

            if original_content['has_tags']:
                if has_placeholders:
                    # Validate the tagged text
                    validation = validate_tags(
                        target_text,
                        original_content['tag_map'],
                        original_content['tagged_text']
                    )
                    result['validation'] = validation
                    result['warnings'] = validation.get('warnings', [])

                    if not validation['valid']:
                        result['message'] = (
                            f"Tag validation failed: {'; '.join(validation['errors'])}. "
                            f"Original tagged text: {original_content['tagged_text']}"
                        )
                        return result

                    # Build new mrk element with restored tags
                    new_mrk = build_mrk_with_tags(
                        target_text, original_mrk, original_content['tag_map']
                    )

                    # Replace the mrk element in the tree
                    parent = mrk.getparent()
                    if parent is not None:
                        index = list(parent).index(mrk)
                        parent.remove(mrk)
                        parent.insert(index, new_mrk)

                        # Update segment index to point to new element
                        self._segment_index[segment_id] = (trans_unit, new_mrk)

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

    def save(self, output_path: Optional[str] = None, create_backup: bool = True):
        """
        Save the modified SDLXLIFF file using atomic write.

        Args:
            output_path: Optional output path. If None, overwrites the original file.
            create_backup: If True and overwriting existing file, create .bak backup.
        """
        out_path = Path(output_path) if output_path else self.file_path
        save_sdlxliff(self.root, out_path, self.file_path, create_backup)

    def get_segment_by_id(self, segment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific segment by its mrk mid.

        Args:
            segment_id: The mrk mid to retrieve

        Returns:
            Dictionary with segment information or None if not found.
        """
        result = self._find_mrk_by_mid(segment_id)
        if result is None:
            return None

        trans_unit, mrk = result
        tu_id = trans_unit.get('id')

        # Get target content with tags
        target_content = extract_content_with_tags(mrk)

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
                    source_content = extract_content_with_tags(source_mrk)
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

        # Get status from sdl:seg (use base ID for split segments)
        base_id = self._get_base_segment_id(segment_id)
        sdl_seg = self._find_sdl_seg_by_id(segment_id)
        if sdl_seg is None:
            sdl_seg = self._find_sdl_seg_by_id(base_id)
        status = sdl_seg.get('conf') if sdl_seg is not None else None
        locked = sdl_seg.get('locked') == 'true' if sdl_seg is not None else False

        # Get percent, origin, and text_match
        percent_str = sdl_seg.get('percent') if sdl_seg is not None else None
        percent = int(percent_str) if percent_str else None
        origin = sdl_seg.get('origin') if sdl_seg is not None else None
        text_match = sdl_seg.get('text-match') if sdl_seg is not None else None

        segment_data = {
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

        # Add percent only when present (to minimize token overhead)
        if percent is not None:
            segment_data['percent'] = percent

        # Add origin only when present (to minimize token overhead)
        if origin:
            segment_data['origin'] = origin

        # Add text_match for Context Match detection (CM = "SourceAndTarget")
        if text_match:
            segment_data['text_match'] = text_match

        # Add repetitions count only when > 1 (to minimize token overhead)
        rep_count = self._repetition_counts.get((tu_id, segment_id))
        if rep_count and rep_count > 1:
            segment_data['repetitions'] = rep_count

        return segment_data

    def get_file_metadata(self) -> Dict[str, Any]:
        """
        Extract file-level metadata from the SDLXLIFF file.

        Returns:
            Dictionary with source_language and target_language
        """
        metadata: Dict[str, Any] = {
            'source_language': None,
            'target_language': None,
        }

        file_elem = self.root.find('.//xliff:file', self.namespaces)
        if file_elem is not None:
            metadata['source_language'] = file_elem.get('source-language')
            metadata['target_language'] = file_elem.get('target-language')

        return metadata

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the SDLXLIFF file.

        Returns:
            Dictionary with statistics about segments, statuses, and languages
        """
        metadata = self.get_file_metadata()

        status_counts: Dict[str, int] = {}
        locked_count = 0
        total = 0

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