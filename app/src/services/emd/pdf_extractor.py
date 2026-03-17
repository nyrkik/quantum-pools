"""EMD PDF Extractor — extracts inspection data, violations, and equipment from Sacramento County EMD PDFs.

Ported from Pool Scout Pro's pdf_extractor.py and rebuild_equipment_from_reports.py.
Uses PyMuPDF (fitz) for text extraction, then regex for structured parsing.
"""

import re
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class EMDPDFExtractor:
    """Extract structured data from Sacramento County EMD inspection report PDFs."""

    def extract_text(self, pdf_path: str) -> str:
        """Extract all text from a PDF file using PyMuPDF."""
        try:
            import fitz
            with fitz.open(pdf_path) as doc:
                return "".join(page.get_text() for page in doc)
        except Exception as e:
            logger.error(f"PDF text extraction failed for {pdf_path}: {e}")
            return ""

    def extract_all(self, pdf_path: str) -> dict:
        """Extract all structured data from an EMD inspection PDF.

        Returns dict with keys: inspection_date, violations, equipment, notes
        """
        text = self.extract_text(pdf_path)
        if not text:
            return {"inspection_date": None, "violations": [], "equipment": {}, "notes": None}

        return {
            "inspection_date": self._find_date(text),
            "violations": self._extract_violations(text),
            "equipment": self._extract_equipment(text),
            "notes": self._extract_notes(text),
        }

    def _find_date(self, text: str) -> Optional[str]:
        """Extract inspection date from PDF text. Returns YYYY-MM-DD or None."""
        match = re.search(r"Date\s+Entered\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
        if match:
            try:
                from dateutil.parser import parse as parse_date
                return parse_date(match.group(1)).strftime("%Y-%m-%d")
            except Exception:
                pass
        return None

    def _extract_violations(self, text: str) -> list[dict]:
        """Extract violations from PDF text.

        Returns list of dicts with: violation_code, violation_title, observations, is_major_violation
        """
        violations = []
        pattern = re.compile(
            r"(\d+[a-z]?)\.\s(.*?)\n\s*Observations:(.*?)(?=\n\s*Code Description:|\Z)",
            re.S,
        )
        for match in pattern.finditer(text):
            obs = match.group(3).strip()
            is_major = "MAJOR VIOLATION" in obs.upper() or "MAJOR" in obs.upper().split("\n")[0]
            violations.append({
                "violation_code": match.group(1),
                "violation_title": match.group(2).strip(),
                "observations": obs,
                "is_major_violation": is_major,
            })
        return violations

    def _extract_equipment(self, text: str) -> dict:
        """Extract equipment data from PDF text using comprehensive regex patterns.

        Ported from Pool Scout Pro's rebuild_equipment_from_reports.py patterns.
        """
        equip = {}

        # Pool capacity
        cap_match = re.search(r"(?:Pool\s+)?Capacity[:\s]*(\d[\d,]*)\s*(?:gal|gallons)?", text, re.I)
        if cap_match:
            equip["pool_capacity_gallons"] = int(cap_match.group(1).replace(",", ""))

        # Flow rate
        flow_match = re.search(r"(?:Flow\s+Rate|GPM)[:\s]*(\d+)\s*(?:gpm|GPM)?", text, re.I)
        if flow_match:
            equip["flow_rate_gpm"] = int(flow_match.group(1))

        # Filter pump 1
        pump_patterns = [
            (r"(?:Filter\s+Pump|Recirc\.?\s+Pump)\s*#?\s*1?[:\s]*(?:Make[:\s]*)?(\w[\w\s-]*?)(?:\s+Model[:\s]*)?(\w[\w\s-]*?)(?:\s+HP[:\s]*)?(\d+\.?\d*)", re.I),
            (r"(?:Pump|Motor)\s*(?:Make)?[:\s]*(Pentair|Hayward|Sta-Rite|Jandy|Waterway)[\s,]*(?:Model)?[:\s]*([\w-]+)[\s,]*(?:HP)?[:\s]*(\d+\.?\d*)", re.I),
        ]
        for pattern, flags in pump_patterns:
            m = re.search(pattern, text, flags)
            if m:
                equip["filter_pump_1_make"] = m.group(1).strip()
                equip["filter_pump_1_model"] = m.group(2).strip() if m.group(2) else None
                equip["filter_pump_1_hp"] = m.group(3).strip() if m.lastindex >= 3 and m.group(3) else None
                break

        # Filter 1
        filter_patterns = [
            (r"Filter\s*#?\s*1?[:\s]*(?:Make[:\s]*)?(\w[\w\s-]*?)(?:\s+Model[:\s]*)?(\w[\w\s/-]*?)(?:\s+(?:Cap|GPM)[:\s]*)?(\d+)", re.I),
            (r"Filter[:\s]*(Pentair|Hayward|Sta-Rite|Jandy|Waterway)[\s,]*([\w-]+)[\s,]*(\d+)\s*(?:gpm|GPM)", re.I),
        ]
        for pattern, flags in filter_patterns:
            m = re.search(pattern, text, flags)
            if m:
                equip["filter_1_make"] = m.group(1).strip()
                equip["filter_1_model"] = m.group(2).strip() if m.group(2) else None
                break

        # Filter type (DE, Sand, Cartridge)
        ftype_match = re.search(r"Filter\s+Type[:\s]*(DE|Sand|Cartridge|Diatomaceous)", text, re.I)
        if ftype_match:
            equip["filter_1_type"] = ftype_match.group(1).strip()

        # Sanitizer
        san_patterns = [
            (r"(?:Sanitizer|Chlorinator|Chemical\s+Feeder)\s*#?\s*1?[:\s]*([\w\s-]+?)(?:\n|$)", re.I),
            (r"(Liquid\s+Chlorine|Gas\s+Chlorine|Salt\s+(?:Chlorinator|Generator)|Erosion\s+Feeder|UV|Ozone)", re.I),
        ]
        for pattern, flags in san_patterns:
            m = re.search(pattern, text, flags)
            if m:
                equip["sanitizer_1_details"] = m.group(1).strip()[:200]
                break

        # Main drain
        drain_match = re.search(
            r"Main\s+Drain[:\s]*(?:Cover)?[:\s]*([\w\s-]+?)(?:\n|Install)", text, re.I
        )
        if drain_match:
            equip["main_drain_model"] = drain_match.group(1).strip()[:100]
            equip["main_drain_type"] = "Main Drain"

        drain_date = re.search(
            r"Main\s+Drain.*?Install(?:ed)?(?:\s+Date)?[:\s]*(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
            text, re.I | re.S,
        )
        if drain_date:
            equip["main_drain_install_date"] = drain_date.group(1).strip()

        # Equalizer
        eq_match = re.search(r"Equalizer[:\s]*([\w\s-]+?)(?:\n|Install)", text, re.I)
        if eq_match:
            equip["equalizer_model"] = eq_match.group(1).strip()[:100]

        eq_date = re.search(
            r"Equalizer.*?Install(?:ed)?(?:\s+Date)?[:\s]*(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
            text, re.I | re.S,
        )
        if eq_date:
            equip["equalizer_install_date"] = eq_date.group(1).strip()

        return equip

    def _extract_notes(self, text: str) -> Optional[str]:
        """Extract general notes from the inspection report."""
        # Look for Note sections
        notes = []
        note_pattern = re.compile(r"Note\s*[-–—]?\s*(.*?)(?=\nNote\s*[-–—]?|\n\d+[a-z]?\.\s|\Z)", re.S | re.I)
        for m in note_pattern.finditer(text):
            note_text = m.group(1).strip()
            if note_text and len(note_text) > 10:
                notes.append(note_text)
        return "\n\n".join(notes) if notes else None
