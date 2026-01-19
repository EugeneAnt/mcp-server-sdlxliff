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

    def _extract_segment_from_trans_unit(self, trans_unit: etree._Element) -> Dict[str, Any]:
        """
        Extract segment data from a trans-unit element.

        Args:
            trans_unit: The trans-unit XML element

        Returns:
            Dictionary with segment information
        """
        segment_id = trans_unit.get('id')

        # Extract source text
        source_elem = trans_unit.find('xliff:source', self.namespaces)
        source_text = self._get_text_content(source_elem) if source_elem is not None else ""

        # Extract target text
        target_elem = trans_unit.find('xliff:target', self.namespaces)
        target_text = self._get_text_content(target_elem) if target_elem is not None else ""

        # Extract SDL confirmation level from seg-defs
        status = None
        locked = False
        seg_defs = trans_unit.find('sdl:seg-defs', self.namespaces)
        if seg_defs is not None:
            first_seg = seg_defs.find('sdl:seg', self.namespaces)
            if first_seg is not None:
                status = first_seg.get('conf')
                locked = first_seg.get('locked') == 'true'

        return {
            'segment_id': segment_id,
            'source': source_text,
            'target': target_text,
            'status': status,
            'locked': locked,
        }

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

        Returns:
            List of dictionaries containing segment information:
            - segment_id: Unique identifier for the segment
            - source: Source text
            - target: Target text
            - status: Translation status (e.g., 'translated', 'draft')
            - locked: Whether the segment is locked
        """
        segments = []

        # Find all trans-unit elements
        trans_units = self.root.findall('.//xliff:trans-unit', self.namespaces)

        for trans_unit in trans_units:
            segments.append(self._extract_segment_from_trans_unit(trans_unit))

        return segments

    def update_segment(self, segment_id: str, target_text: str, status: str = 'RejectedTranslation') -> bool:
        """
        Update a specific segment's target text and status.

        Args:
            segment_id: ID of the segment to update
            target_text: New target text
            status: SDL confirmation level (default: 'RejectedTranslation').
                    Valid values: Draft, Translated, RejectedTranslation,
                    ApprovedTranslation, RejectedSignOff, ApprovedSignOff

        Returns:
            True if segment was found and updated, False otherwise
        """
        # Find the trans-unit with the specified ID (using safe XPath)
        trans_unit = self._find_trans_unit_by_id(segment_id)

        if trans_unit is None:
            return False

        # Find or create target element
        target_elem = trans_unit.find('xliff:target', self.namespaces)

        if target_elem is None:
            # Create target element if it doesn't exist
            source_elem = trans_unit.find('xliff:source', self.namespaces)
            target_elem = etree.Element(f'{{{self.namespaces["xliff"]}}}target')
            if source_elem is not None:
                # Insert after source
                source_index = list(trans_unit).index(source_elem)
                trans_unit.insert(source_index + 1, target_elem)
            else:
                trans_unit.append(target_elem)

        # Update target text - need to handle mrk elements for SDLXLIFF
        # Find mrk elements with mtype="seg" (actual segment content)
        seg_mrks = target_elem.findall('.//xliff:mrk[@mtype="seg"]', self.namespaces)

        if seg_mrks:
            # Put new text in the first mrk, clear all others
            for i, mrk in enumerate(seg_mrks):
                # Clear all children (like x-sdl-location markers)
                for child in list(mrk):
                    mrk.remove(child)
                if i == 0:
                    # First mrk gets the new text
                    mrk.text = target_text
                else:
                    # Other mrks get cleared
                    mrk.text = None
                # Preserve tail (spacing between mrk elements)
        else:
            # Simple target without mrk - just set text directly
            for child in list(target_elem):
                target_elem.remove(child)
            target_elem.text = target_text

        # Update SDL confirmation level in seg-defs
        self._update_sdl_confirmation(trans_unit, status)

        return True

    def _update_sdl_confirmation(self, trans_unit: etree._Element, conf_level: str):
        """
        Update the SDL confirmation level for all segments in a trans-unit.

        Args:
            trans_unit: The trans-unit element
            conf_level: SDL confirmation level (Draft, Translated, RejectedTranslation, etc.)
        """
        seg_defs = trans_unit.find('sdl:seg-defs', self.namespaces)
        if seg_defs is not None:
            for seg in seg_defs.findall('sdl:seg', self.namespaces):
                seg.set('conf', conf_level)

    def set_segment_status(self, segment_id: str, status: str = 'RejectedTranslation') -> bool:
        """
        Update a segment's SDL confirmation level only (without changing text).

        Args:
            segment_id: ID of the segment to update
            status: SDL confirmation level (default: 'RejectedTranslation').
                    Valid values: Draft, Translated, RejectedTranslation,
                    ApprovedTranslation, RejectedSignOff, ApprovedSignOff

        Returns:
            True if segment was found and updated, False otherwise
        """
        trans_unit = self._find_trans_unit_by_id(segment_id)

        if trans_unit is None:
            return False

        # Update SDL confirmation level
        self._update_sdl_confirmation(trans_unit, status)
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
        Get a specific segment by its ID.

        Uses direct XPath lookup for O(1) performance instead of iterating all segments.

        Args:
            segment_id: The segment ID to retrieve

        Returns:
            Dictionary with segment information or None if not found
        """
        trans_unit = self._find_trans_unit_by_id(segment_id)
        if trans_unit is None:
            return None
        return self._extract_segment_from_trans_unit(trans_unit)

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the SDLXLIFF file.

        Efficiently counts statistics without extracting full text content.

        Returns:
            Dictionary with statistics:
            - total_segments: Total number of segments
            - status_counts: Count of segments by SDL confirmation level
            - locked_count: Number of locked segments
        """
        trans_units = self.root.findall('.//xliff:trans-unit', self.namespaces)

        status_counts: Dict[str, int] = {}
        locked_count = 0
        total = 0

        for trans_unit in trans_units:
            total += 1

            # Get SDL confirmation level from seg-defs
            seg_defs = trans_unit.find('sdl:seg-defs', self.namespaces)
            if seg_defs is not None:
                first_seg = seg_defs.find('sdl:seg', self.namespaces)
                if first_seg is not None:
                    status = first_seg.get('conf')
                    status_key = status or 'unknown'
                    status_counts[status_key] = status_counts.get(status_key, 0) + 1

                    # Check if locked
                    if first_seg.get('locked') == 'true':
                        locked_count += 1
                else:
                    status_counts['unknown'] = status_counts.get('unknown', 0) + 1
            else:
                status_counts['unknown'] = status_counts.get('unknown', 0) + 1

        return {
            'total_segments': total,
            'status_counts': status_counts,
            'locked_count': locked_count,
        }