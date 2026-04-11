"""EMD PDF Extractor — extracts all inspection data from Sacramento County EMD PDFs.

Uses PyMuPDF (fitz) for text extraction, then line-by-line parsing for structured fields.
The PDF has a consistent structure: labeled fields followed by values on the next line(s).
"""

import re
import logging
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
        """Extract all structured data from an EMD inspection PDF."""
        text = self.extract_text(pdf_path)
        if not text:
            return {"inspection_date": None, "violations": [], "equipment": {}, "notes": None}

        lines = text.split("\n")
        fields = self._parse_labeled_fields(lines)

        # Some older / alternate-format PDFs don't use labeled fields — values
        # appear in a fixed sequence on consecutive lines. For those, fall
        # back to regex (FA, PR, date) and position-based field extraction.
        unlabeled = self._extract_unlabeled_fields(lines) if not fields else {}

        return {
            "inspection_date": self._find_date(text),
            "program_identifier": self._extract_program_identifier(lines) or unlabeled.get("program_identifier"),
            "permit_id": self._extract_permit_id(text),
            "facility_id": self._extract_field(fields, "Establishment ID") or self._extract_facility_id_regex(text),
            "permit_holder": self._extract_field(fields, "Permit Holder") or unlabeled.get("permit_holder"),
            "facility_name": self._extract_field(fields, "Facility Name") or unlabeled.get("facility_name"),
            "facility_address": self._extract_field(fields, "Facility Address") or unlabeled.get("facility_address"),
            "facility_city": self._extract_field(fields, "Facility City") or unlabeled.get("facility_city"),
            "facility_zip": self._extract_field(fields, "Facility ZIP") or unlabeled.get("facility_zip"),
            "phone_number": self._extract_field(fields, "Phone Number") or unlabeled.get("phone_number"),
            "inspection_type": self._extract_field(fields, "Type") or self._extract_field(fields, "Purpose") or unlabeled.get("inspection_type"),
            # Inspector section
            "inspector_name": self._extract_field(fields, "Inspector"),
            "co_inspector": self._extract_field(fields, "Co-Inspector"),
            "inspector_phone": self._extract_field(fields, "Insp Phone"),
            "accepted_by": self._extract_field(fields, "Accepted By"),
            "reviewed_by": self._extract_field(fields, "Reviewed"),
            # Chemistry readings
            "free_chlorine": self._parse_float(self._extract_field(fields, "Free Chlorine")),
            "combined_chlorine": self._parse_float(self._extract_field(fields, "Combined Chlorine")),
            "ph": self._parse_float(self._extract_field(fields, "pH")),
            "cyanuric_acid_ppm": self._parse_float(self._extract_field(fields, "CYA")),
            "pool_spa_temp": self._parse_float(self._extract_field(fields, "Pool/Spa Temp")),
            "flow_rate": self._parse_float(self._extract_field(fields, "Flow rate")),
            # Gauge readings
            "rp_gauge": self._parse_float(self._extract_field(fields, "RP Gauge")),
            "rv_gauge": self._parse_float(self._extract_field(fields, "RV Gauge")),
            "bp_gauge": self._parse_float(self._extract_field(fields, "BP Gauge")),
            "bv_gauge": self._parse_float(self._extract_field(fields, "BV Gauge")),
            "uv_output": self._extract_field(fields, "UV Output"),
            # Structured pump/filter fields
            "rp_make": self._extract_field(fields, "RP-Make"),
            "rp_model": self._extract_field(fields, "RP-Model"),
            "rp_hp": self._extract_field(fields, "RP-HP"),
            "bp_make": self._extract_field(fields, "BP-Make"),
            "bp_model": self._extract_field(fields, "BP-Model"),
            "bp_hp": self._extract_field(fields, "BP-HP"),
            "filter_type": self._extract_field(fields, "Filter - Type"),
            "filter_make": self._extract_field(fields, "Filter-Make"),
            "filter_model": self._extract_field(fields, "Filter-Model"),
            "filter_cleaning_method": self._extract_field(fields, "Filter-Cleaning Method"),
            "df_type": self._extract_field(fields, "DF-Type"),
            "df_make": self._extract_field(fields, "DF-Make"),
            # Equipment blob + parsed
            "equipment": self._extract_equipment(text),
            # Violations
            "violations": self._extract_violations(text),
            # Notes
            "notes": self._extract_notes(text),
        }

    def _parse_labeled_fields(self, lines: list[str]) -> dict[str, str]:
        """Parse the PDF's label/value structure into a dict.

        The PDF has patterns like:
            Label Name
            Value
        where the label is a known field name and the next non-empty line is the value.
        """
        known_labels = {
            "Date Entered", "Permit Holder", "Facility Name", "Facility Address",
            "Facility City", "Facility ZIP", "Phone Number", "Establishment ID",
            "Permit ID", "Type", "Purpose", "Prog Identifier",
            "Free Chlorine", "Combined Chlorine", "pH", "CYA",
            "Pool/Spa Temp", "Flow rate", "RP Gauge", "RV Gauge",
            "BP Gauge", "BV Gauge", "UV Output",
            "RP-Make", "RP-Model", "RP-HP", "BP-Make", "BP-Model", "BP-HP",
            "Filter - Type", "Filter-Make", "Filter-Model", "Filter-Cleaning Method",
            "DF-Type", "DF-Make",
            "Inspector", "Co-Inspector", "Insp Phone", "Accepted By", "Reviewed",
            "Pool Equipment",
        }
        # Build lookup (case-insensitive)
        label_map = {l.lower(): l for l in known_labels}

        fields: dict[str, str] = {}
        for i, line in enumerate(lines):
            stripped = line.strip()
            key = label_map.get(stripped.lower())
            if key and key not in fields:
                # Value is on the next non-empty line
                for j in range(i + 1, min(i + 4, len(lines))):
                    val = lines[j].strip()
                    if not val:
                        continue
                    # Skip if the next line is another known label
                    if val.lower() in label_map:
                        break
                    # Skip page markers
                    if val.startswith("Pag") or val.startswith("Tota"):
                        break
                    fields[key] = val
                    break

        return fields

    @staticmethod
    def _extract_field(fields: dict, key: str) -> Optional[str]:
        val = fields.get(key)
        if val and val.strip():
            return val.strip()
        return None

    @staticmethod
    def _parse_float(val: Optional[str]) -> Optional[float]:
        if not val:
            return None
        try:
            return float(val.replace(",", ""))
        except (ValueError, TypeError):
            return None

    def _extract_program_identifier(self, lines: list[str]) -> Optional[str]:
        """Extract Program Identifier (POOL, SPA, LAP POOL, etc.)."""
        for i, line in enumerate(lines):
            if "prog identifier" in line.lower():
                for j in range(i + 1, min(i + 3, len(lines))):
                    val = lines[j].strip()
                    if not val:
                        continue
                    if val.startswith("Pag") or val.startswith("Iteration") or val.startswith("Tota"):
                        continue
                    if re.match(r"^\d+[a-zA-Z]?\.\s", val):
                        continue
                    # Skip other known labels
                    if val.lower() in {"free chlorine", "notes", "iteration violation"}:
                        continue
                    return val.upper()
                break
        return None

    def _extract_permit_id(self, text: str) -> Optional[str]:
        """Extract Permit ID (PR number)."""
        match = re.search(r"\bPR\d{4,}\b", text)
        return match.group(0) if match else None

    def _extract_facility_id_regex(self, text: str) -> Optional[str]:
        """Regex fallback for the EMD Establishment ID (FA number).

        Used when the PDF doesn't have labeled fields (older/alternate
        layout where values appear in a fixed sequence without 'Establishment
        ID:' labels). Picks the first FA######-style token in the text.
        """
        match = re.search(r"\bFA\d{4,8}\b", text)
        return match.group(0) if match else None

    def _extract_unlabeled_fields(self, lines: list[str]) -> dict:
        """Position-based extraction for PDFs that lack 'Permit Holder',
        'Facility Address', etc. labels.

        Sample of a known unlabeled layout:
            06/13/2024
            LAUREL OAKS APARTMENTS         <- facility name
            SR95 SMOKETREE LLC & LINCOLN   <- permit holder
            3334 Smoketree Dr              <- street address
            Sacramento                     <- city
            95834                          <- zip
            (916) 927-2200                 <- phone
            FA0005982                      <- FA
            PR0007458                      <- PR
            1                              <- numeric noise
            REINSPECTION                   <- inspection type
            OFFICE MAIN SPA                <- program identifier

        Anchors on the FA line: walks backwards to find the address block,
        and forwards for the inspection type / program identifier.
        """
        out: dict = {}
        # Find the FA line as the anchor
        fa_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*FA\d{4,8}\s*$", line):
                fa_idx = i
                break
        if fa_idx is None:
            return out

        # Walk backwards from FA: phone, zip, city, address, holder, name, date
        slots = []
        j = fa_idx - 1
        while j >= 0 and len(slots) < 7:
            stripped = lines[j].strip()
            if stripped:
                slots.append(stripped)
            j -= 1
        slots.reverse()
        # We expect (most-recent → oldest):
        #   [date, name, holder, address, city, zip, phone]
        # Take the last 7 if we have at least that many
        if len(slots) >= 7:
            tail = slots[-7:]
            out["facility_name"] = tail[1]
            out["permit_holder"] = tail[2]
            out["facility_address"] = tail[3]
            out["facility_city"] = tail[4]
            # ZIP often comes through as "95834" or "CA 95834"
            zip_match = re.search(r"\b(\d{5}(?:-\d{4})?)\b", tail[5])
            if zip_match:
                out["facility_zip"] = zip_match.group(1)
            phone_match = re.search(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", tail[6])
            if phone_match:
                out["phone_number"] = phone_match.group(0)

        # Walk forwards from FA for: PR, count, inspection type, program identifier
        forward = []
        j = fa_idx + 1
        while j < len(lines) and len(forward) < 5:
            stripped = lines[j].strip()
            if stripped:
                forward.append(stripped)
            j += 1
        # forward should look like: ['PR0007458', '1', 'REINSPECTION', 'OFFICE MAIN SPA', ...]
        # Skip items that are pure numbers (page indicators) and pure PR####
        meaningful = [
            f for f in forward
            if not re.fullmatch(r"\d+", f) and not re.fullmatch(r"PR\d+", f)
        ]
        if meaningful:
            # First non-numeric is the inspection type (REINSPECTION, ROUTINE, etc.)
            out["inspection_type"] = meaningful[0]
            # Next is the program identifier
            if len(meaningful) > 1:
                # Skip "Recreational Health" boilerplate
                for m in meaningful[1:]:
                    if m.lower() != "recreational health":
                        out["program_identifier"] = m
                        break

        return out

    def _find_date(self, text: str) -> Optional[str]:
        """Extract inspection date. Returns YYYY-MM-DD or None.

        Tries the labeled form first ("Date Entered MM/DD/YYYY"); falls back
        to the first standalone MM/DD/YYYY token in the text for PDFs that
        don't use labeled fields.
        """
        match = re.search(r"Date\s+Entered\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
        if match:
            try:
                from dateutil.parser import parse as parse_date
                return parse_date(match.group(1)).strftime("%Y-%m-%d")
            except Exception:
                pass
        # Fallback: first MM/DD/YYYY anywhere in the text
        match = re.search(r"\b(\d{1,2}/\d{1,2}/20\d{2})\b", text)
        if match:
            try:
                from dateutil.parser import parse as parse_date
                return parse_date(match.group(1)).strftime("%Y-%m-%d")
            except Exception:
                pass
        return None

    def _extract_violations(self, text: str) -> list[dict]:
        """Extract violations with observations and code descriptions."""
        violations = []

        # Pattern: "CODE. TITLE\nObservations: ...\nCode Description: ..."
        # Match violation blocks
        pattern = re.compile(
            r"(\d+[a-z]?)\.\s(.*?)\n\s*Observations:\s*(.*?)(?=\nCode Description:|(?=\n\d+[a-z]?\.\s)|\Z)",
            re.S | re.I,
        )
        code_desc_pattern = re.compile(
            r"Code Description:\s*(.*?)(?=\n\d+[a-z]?\.\s|\nTota|\nDate Entered|\Z)",
            re.S | re.I,
        )

        # Find all violations
        for match in pattern.finditer(text):
            code = match.group(1)
            title = match.group(2).strip()
            obs = match.group(3).strip()
            is_major = bool(re.search(r"MAJOR", obs.upper().split("\n")[0]))

            # Try to find code description after this violation
            code_desc = None
            after_obs = text[match.end():]
            cd_match = code_desc_pattern.match(after_obs.lstrip())
            if cd_match:
                code_desc = cd_match.group(1).strip()
                # Clean up: remove page breaks and repeated headers
                code_desc = re.sub(r"\nPag\n\d+\n.*?(?:Recreational Health|Permit Holder).*?\n", "\n", code_desc, flags=re.S)
                code_desc = code_desc.strip()

            violations.append({
                "violation_code": code,
                "violation_title": title,
                "observations": obs,
                "is_major_violation": is_major,
                "code_description": code_desc,
            })

        return violations

    def _extract_equipment(self, text: str) -> dict:
        """Extract equipment data from both the text blob and structured fields."""
        equip = {}

        # Find the equipment text blob (line after "Pool Equipment")
        eq_match = re.search(r"Pool Equipment\n(.*?)(?:\nRP-Make|\nTota|\Z)", text, re.S)
        if eq_match:
            eq_text = eq_match.group(1).strip()
            equip["equipment_text"] = eq_text

            # Parse capacity from blob: "22,500 gal" or "22500 GAL"
            cap = re.search(r"([\d,]+)\s*gal", eq_text, re.I)
            if cap:
                equip["pool_capacity_gallons"] = int(cap.group(1).replace(",", ""))

            # Flow rate from blob: "47 gpm" or "47GPM"
            flow = re.search(r"(\d+)\s*gpm", eq_text, re.I)
            if flow:
                equip["flow_rate_gpm"] = int(flow.group(1))

            # Filter from blob: "FILTER: CART., Sta-Rite S8M150 (124 GPM)"
            filt = re.search(r"FILTER:\s*(.*?)(?:;|\Z)", eq_text, re.I)
            if filt:
                filt_text = filt.group(1).strip()
                # Type
                if re.search(r"CART", filt_text, re.I):
                    equip["filter_1_type"] = "Cartridge"
                elif re.search(r"SAND|HIGH RATE", filt_text, re.I):
                    equip["filter_1_type"] = "Sand"
                elif re.search(r"DE|DIATOM", filt_text, re.I):
                    equip["filter_1_type"] = "DE"
                # Make/model — extract what follows the type
                parts = re.split(r"CART\.?,?|SAND,?|DE,?|HIGH RATE SAND,?", filt_text, flags=re.I)
                if len(parts) > 1:
                    remainder = parts[-1].strip().rstrip(",")
                    # Try to split into make model
                    tokens = remainder.split()
                    if tokens:
                        equip["filter_1_make"] = tokens[0]
                        if len(tokens) > 1:
                            equip["filter_1_model"] = " ".join(tokens[1:]).split("(")[0].strip()
                    # Capacity from parentheses
                    cap_match = re.search(r"\((\d+)\s*GPM\)", remainder, re.I)
                    if cap_match:
                        equip["filter_1_capacity_gpm"] = int(cap_match.group(1))

            # Pump from blob: "PUMP: STA RITE INTELLIPRO VSF 013004, 3HP (126GPM@60'TDH)"
            pump = re.search(r"PUMP:\s*(.*?)(?:;|\Z)", eq_text, re.I)
            if pump:
                pump_text = pump.group(1).strip()
                # Extract HP
                hp_match = re.search(r"(\d+\.?\d*)\s*HP", pump_text, re.I)
                if hp_match:
                    equip["filter_pump_1_hp"] = hp_match.group(1)
                # Make/model — everything before HP or comma
                make_model = re.split(r",\s*\d+\.?\d*\s*HP|\(", pump_text)[0].strip().rstrip(",")
                tokens = make_model.split()
                if tokens:
                    equip["filter_pump_1_make"] = tokens[0]
                    if len(tokens) > 1:
                        equip["filter_pump_1_model"] = " ".join(tokens[1:])

            # Jet pump: "JET: Acapulco 4280 4x3x10, 7.5hp"
            jet = re.search(r"JET:\s*(.*?)(?:;|\Z)", eq_text, re.I)
            if jet:
                jet_text = jet.group(1).strip()
                hp_match = re.search(r"(\d+\.?\d*)\s*(?:HP|hp|gpm)", jet_text, re.I)
                if hp_match:
                    equip["jet_pump_1_hp"] = hp_match.group(1)
                make_model = re.split(r",\s*\d+\.?\d*\s*(?:HP|hp)|\(", jet_text)[0].strip().rstrip(",")
                tokens = make_model.split()
                if tokens:
                    equip["jet_pump_1_make"] = tokens[0]
                    if len(tokens) > 1:
                        equip["jet_pump_1_model"] = " ".join(tokens[1:])

            # Sanitizer: "SAN; LIQ; ROLACHEM RC303MC" or "SAN: LIQUID CHLORINE"
            san = re.search(r"SAN[;:\s]+(.*?)(?:;{2}|\Z|\n)", eq_text, re.I)
            if san:
                san_text = san.group(1).strip().rstrip(";")
                if re.search(r"LIQ", san_text, re.I):
                    equip["sanitizer_1_type"] = "Liquid"
                elif re.search(r"GAS", san_text, re.I):
                    equip["sanitizer_1_type"] = "Gas"
                elif re.search(r"SALT", san_text, re.I):
                    equip["sanitizer_1_type"] = "Salt"
                elif re.search(r"EROSION|TAB", san_text, re.I):
                    equip["sanitizer_1_type"] = "Erosion"
                # Details — model/make after type
                details = re.sub(r"^(LIQ|GAS|SALT|EROSION|TAB)[;,\s]*", "", san_text, flags=re.I).strip()
                if details:
                    equip["sanitizer_1_details"] = details[:200]

            # Main drain: "MD: SINGLE: AQUASTAR 32CDFL (316GPM), INSTALLED: 07/31/2022"
            md = re.search(r"MD:\s*(.*?)(?:;{2}|EQ:|\Z|\n)", eq_text, re.I)
            if md:
                md_text = md.group(1).strip().rstrip(";")
                # Config (single/split)
                if "SINGLE" in md_text.upper():
                    equip["main_drain_config"] = "Single"
                elif "SPLIT" in md_text.upper():
                    equip["main_drain_config"] = "Split"
                # Model
                model_match = re.search(r"(?:SINGLE|SPLIT)[:\s]*([\w\s-]+?)(?:\(|,|INSTALL)", md_text, re.I)
                if model_match:
                    equip["main_drain_model"] = model_match.group(1).strip()
                # Capacity
                cap_match = re.search(r"\((\d+)\s*GPM\)", md_text, re.I)
                if cap_match:
                    equip["main_drain_capacity_gpm"] = int(cap_match.group(1))
                # Install date
                date_match = re.search(r"INSTALL(?:ED)?[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})", md_text, re.I)
                if date_match:
                    equip["main_drain_install_date"] = date_match.group(1)

            # Equalizer: "EQ: AQUASTAR 32CDFL (208GPM) INSTALLED: 07/31/2022"
            eq = re.search(r"EQ:\s*(.*?)(?:;{2}|SK|\Z|\n)", eq_text, re.I)
            if eq:
                eq_text_val = eq.group(1).strip().rstrip(";")
                if "NONE" not in eq_text_val.upper() and "AUTOFILL" not in eq_text_val.upper():
                    model_match = re.search(r"([\w\s-]+?)(?:\(|,|INSTALL|\Z)", eq_text_val, re.I)
                    if model_match:
                        equip["equalizer_model"] = model_match.group(1).strip()
                    cap_match = re.search(r"\((\d+)\s*GPM\)", eq_text_val, re.I)
                    if cap_match:
                        equip["equalizer_capacity_gpm"] = int(cap_match.group(1))
                    date_match = re.search(r"INSTALL(?:ED)?[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})", eq_text_val, re.I)
                    if date_match:
                        equip["equalizer_install_date"] = date_match.group(1)

            # Skimmer count: "SK#2" or "SK# 3"
            sk = re.search(r"SK\s*#\s*(\d+)", eq_text, re.I)
            if sk:
                equip["skimmer_count"] = int(sk.group(1))

        return equip

    def _extract_notes(self, text: str) -> Optional[str]:
        """Extract general notes from the inspection report."""
        notes = []
        # Find text after "Notes" label on the notes page
        lines = text.split("\n")
        in_notes = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "Notes":
                in_notes = True
                continue
            if in_notes:
                # Stop at known labels
                if stripped in ("Accepted By", "Reviewed", "Insp Phone", "Inspector", "Co-Inspector", "Tota"):
                    break
                if stripped.startswith("Note - "):
                    notes.append(stripped)
                elif stripped and not stripped.startswith("Pag"):
                    notes.append(stripped)

        return "\n".join(notes).strip() if notes else None
