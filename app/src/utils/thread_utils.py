"""Shared thread utilities — normalize subjects, generate thread keys.

The normalizer strips two classes of leading noise so a single
conversation hashes to one thread_key regardless of how many corporate
mail systems sit between sender and recipient:

1. Reply/forward prefixes: `Re:`, `Fwd:`, `Fw:` (any case, any depth).
2. Bracketed corporate tags: `[EXTERNAL]`, `[EXT]`, `[SECURE]`,
   `[ENCRYPTED]`, etc. — Exchange/Outlook security warnings,
   compliance flags, and encryption gateways add these to the subject
   line, breaking thread continuity if they're not stripped.

The two classes can stack arbitrarily:
  "Re: [EXTERNAL] Re: The Madison - Permit"
  "[EXT] Re: [SECURE] The Madison - Permit"
both normalize to "the madison - permit" (after the lowercase in
make_thread_key) and so route to the same thread.
"""

import re


# Strips ONE leading occurrence per call. The loop in normalize_subject
# applies it repeatedly until no more match.
_PREFIX_RE = re.compile(
    r"""^\s*
        (
            re\s*:                  # Re:  (with optional whitespace before colon)
          | fwd?\s*:                # Fwd: or Fw:
          | \[[^\]]{0,40}\]         # [...]  bracketed tag, capped at 40 chars
        )
        \s*
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes AND bracketed corporate tags
    ([EXTERNAL], [EXT], [SECURE], etc.) so the same conversation
    always hashes to the same thread_key.

    Iterates because prefixes stack:
      "Re: [EXTERNAL] Re: Subject" → "Subject"
    """
    if not subject:
        return ""
    s = subject.strip()
    while True:
        m = _PREFIX_RE.match(s)
        if not m:
            break
        s = s[m.end():].strip()
    return s


def make_thread_key(contact_email: str, subject: str) -> str:
    """Create a thread key from contact email and normalized subject."""
    return f"{normalize_subject(subject)}|{contact_email}".lower()
