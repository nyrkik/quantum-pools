"""Extract phone numbers and names from email signatures."""

import re

# Patterns that indicate a phone number in a signature
_PHONE_LABELS = re.compile(
    r'(?:tel|telephone|phone|ph|cell|mobile|fax|office|direct|work|m|o|c|p)\s*[:.\-)\s]',
    re.IGNORECASE,
)

# Match US phone numbers in various formats
_PHONE_PATTERN = re.compile(
    r'(?<!\d)'                    # not preceded by digit
    r'(?:\+?1[\s.\-]?)?'         # optional country code
    r'(?:\(?\d{3}\)?[\s.\-]?)'   # area code
    r'(?:\d{3}[\s.\-]?)'         # exchange
    r'(?:\d{4})'                  # subscriber
    r'(?!\d)',                     # not followed by digit
)


def extract_phone_from_signature(body: str) -> str | None:
    """Extract the most likely phone number from an email signature block.

    Returns cleaned 10-digit US number or None.
    """
    # Signatures are typically in the last ~30 lines
    lines = body.strip().splitlines()
    sig_block = "\n".join(lines[-30:]) if len(lines) > 30 else body

    best = None
    best_score = 0

    for match in _PHONE_PATTERN.finditer(sig_block):
        raw = match.group()
        start = max(0, match.start() - 30)
        context = sig_block[start:match.start()]

        score = 1
        # Higher score if preceded by a label
        if _PHONE_LABELS.search(context):
            score += 3
        # Higher score if it's on a short line (likely a signature line)
        line_start = sig_block.rfind('\n', 0, match.start()) + 1
        line_end = sig_block.find('\n', match.end())
        if line_end == -1:
            line_end = len(sig_block)
        line = sig_block[line_start:line_end].strip()
        if len(line) < 60:
            score += 1

        if score > best_score:
            best = raw
            best_score = score

    if not best:
        return None

    return _clean_phone(best)


def extract_name_from_signature(body: str) -> tuple[str, str]:
    """Extract first and last name from an email signature block.

    Looks for a name-like line near the end of the email — typically the first
    short line after a blank line, containing 2-3 capitalized words with no
    special characters.

    Returns (first_name, last_name) or ("", "").
    """
    lines = body.strip().splitlines()
    # Scan the last 25 lines for signature patterns
    sig_lines = lines[-25:] if len(lines) > 25 else lines

    # Common signature separators
    _SEP = re.compile(r'^[-_=~]{2,}|^--|^—')
    # A line that looks like a name: 2-3 capitalized words, no digits, no URLs, no emails
    _NAME_LINE = re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})$')
    # Title/role keywords that appear on the line AFTER a name
    _TITLE_HINTS = re.compile(
        r'manager|director|coordinator|supervisor|president|owner|admin|assistant|associate|specialist|technician|maintenance',
        re.IGNORECASE,
    )

    found_blank = False
    for i, line in enumerate(sig_lines):
        stripped = line.strip()
        # Track blank lines and separators as sig entry points
        if not stripped or _SEP.match(stripped):
            found_blank = True
            continue
        if not found_blank:
            continue
        # Skip lines with emails, URLs, phone numbers, or too long
        if '@' in stripped or 'http' in stripped or 'www.' in stripped:
            continue
        if len(stripped) > 40:
            continue
        # Check for name pattern
        m = _NAME_LINE.match(stripped)
        if m:
            # Extra confidence: check if next line looks like a title
            next_line = sig_lines[i + 1].strip() if i + 1 < len(sig_lines) else ""
            if _TITLE_HINTS.search(next_line) or not next_line or _SEP.match(next_line):
                parts = m.group(1).split()
                if len(parts) == 2:
                    return parts[0], parts[1]
                elif len(parts) == 3:
                    return parts[0], parts[2]

    return "", ""


def _clean_phone(raw: str) -> str | None:
    """Clean a phone string to 10-digit format. Strip leading 1."""
    digits = re.sub(r'\D', '', raw)
    # Strip leading country code
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
