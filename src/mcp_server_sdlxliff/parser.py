"""
SDLXLIFF Parser Module

Handles parsing, reading, and writing SDLXLIFF files.
SDLXLIFF is an extension of XLIFF used by SDL Trados Studio.
"""

from lxml import etree
from typing import Dict, List, Optional, Any
from pathlib import Path


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
        self._load_file()

    def _load_file(self):
        """Load and parse the SDLXLIFF file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
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

        Args:
            trans_unit: The trans-unit XML element

        Returns:
            List of dictionaries with segment information
        """
        segments = []
        tu_id = trans_unit.get('id')

        # Get source text (usually not segmented in SDLXLIFF)
        source_elem = trans_unit.find('xliff:source', self.namespaces)
        source_text = self._get_text_content(source_elem) if source_elem is not None else ""

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
                    mrk_text = self._get_mrk_text(mrk)

                    # Get status from seg-defs
                    seg_info = seg_map.get(mid, {})

                    segments.append({
                        'segment_id': mid,  # Use mrk mid as segment ID
                        'trans_unit_id': tu_id,  # Keep trans-unit ID for reference
                        'source': source_text,  # Source is shared across mrks in same TU
                        'target': mrk_text,
                        'status': seg_info.get('conf'),
                        'locked': seg_info.get('locked', False),
                    })
            else:
                # No mrk segments - treat whole target as single segment
                segments.append({
                    'segment_id': tu_id,
                    'trans_unit_id': tu_id,
                    'source': source_text,
                    'target': self._get_text_content(target_elem),
                    'status': seg_map.get('1', {}).get('conf'),
                    'locked': seg_map.get('1', {}).get('locked', False),
                })
        else:
            # No target - return segment with empty target
            segments.append({
                'segment_id': tu_id,
                'trans_unit_id': tu_id,
                'source': source_text,
                'target': '',
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
        """
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

    def save(self, output_path: Optional[str] = None):
        """
        Save the modified SDLXLIFF file.

        Args:
            output_path: Optional output path. If None, overwrites the original file.
        """
        if output_path is None:
            output_path = str(self.file_path)

        # Write with proper XML declaration and encoding
        self.tree.write(
            output_path,
            encoding='utf-8',
            xml_declaration=True,
            pretty_print=False,  # Don't change formatting
        )

    def get_segment_by_id(self, segment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific segment by its mrk mid.

        Args:
            segment_id: The mrk mid to retrieve

        Returns:
            Dictionary with segment information or None if not found
        """
        result = self._find_mrk_by_mid(segment_id)
        if result is None:
            return None

        trans_unit, mrk = result

        # Get source text
        source_elem = trans_unit.find('xliff:source', self.namespaces)
        source_text = self._get_text_content(source_elem) if source_elem is not None else ""

        # Get status from sdl:seg
        sdl_seg = self._find_sdl_seg_by_id(segment_id)
        status = sdl_seg.get('conf') if sdl_seg is not None else None
        locked = sdl_seg.get('locked') == 'true' if sdl_seg is not None else False

        return {
            'segment_id': segment_id,
            'trans_unit_id': trans_unit.get('id'),
            'source': source_text,
            'target': self._get_mrk_text(mrk),
            'status': status,
            'locked': locked,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the SDLXLIFF file.

        Counts each mrk segment (not trans-units) for accurate statistics.

        Returns:
            Dictionary with statistics:
            - total_segments: Total number of mrk segments
            - status_counts: Count of segments by SDL confirmation level
            - locked_count: Number of locked segments
        """
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
            'total_segments': total,
            'status_counts': status_counts,
            'locked_count': locked_count,
        }