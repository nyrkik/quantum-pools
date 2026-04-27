"""Tests the single-letter-brand reassembly that fixes the EMD PDF extractor's
mid-word brand-splitting bug.

Captured patterns from Sapphire data 2026-04-26:
  brand='P' model='urex Triton CC'  → Purex Triton CC
  brand='P' model='ENTAIR TR-'      → Pentair TR-
  brand='H' model='ayward C-'       → Hayward C-
  brand='S' model='ta-Rite S'       → Sta-Rite S
"""

from src.services.equipment.brand_reassembler import reassemble


def test_purex_split():
    assert reassemble("P", "urex Triton CC") == ("Purex", "Triton CC")


def test_pentair_split_uppercase_remainder():
    """Extractor sometimes uppercases the remainder — match should still hit."""
    assert reassemble("P", "ENTAIR TR-") == ("Pentair", "TR-")


def test_hayward_split():
    assert reassemble("H", "ayward C-") == ("Hayward", "C-")
    assert reassemble("H", "ayward C") == ("Hayward", "C")


def test_sta_rite_split():
    """Sta-Rite has a hyphen in canonical form; reassembly should preserve it."""
    assert reassemble("S", "ta-Rite S") == ("Sta-Rite", "S")


def test_no_change_on_full_brand():
    """Full brand names already in `brand` field should NOT trigger reassembly."""
    assert reassemble("Pentair", "WhisperFlo") is None
    assert reassemble("Hayward", "Super II") is None
    assert reassemble("Rolachem", "RC103SC") is None


def test_no_change_when_no_match():
    """Single-letter brands that don't combine to a known prefix → leave alone."""
    assert reassemble("X", "ylophone") is None
    assert reassemble("Z", "abc 123") is None


def test_no_change_on_empty_inputs():
    assert reassemble(None, "anything") is None
    assert reassemble("P", None) is None
    assert reassemble("P", "") is None
    assert reassemble("", "urex") is None


def test_remainder_strips_separators():
    """Leftover punctuation/whitespace at the start of remainder should be stripped."""
    assert reassemble("P", "entair: 3HP")[1] == "3HP"
    assert reassemble("H", "ayward - C")[1] == "C"


def test_longest_prefix_wins():
    """`Pentair Purex` should win over plain `Purex` for the same combined string."""
    # Note: "Pentair Purex" canonical is multi-word; the reassembler looks at the
    # combined string after concat. If brand="P" model="entair Purex 5800", the
    # combined "Pentair Purex 5800" should match "Pentair Purex" (longer prefix)
    # rather than just "Pentair".
    result = reassemble("P", "entair Purex 5800")
    assert result == ("Pentair Purex", "5800")
