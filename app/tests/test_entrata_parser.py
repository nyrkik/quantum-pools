"""Tests for the Entrata parser — Phase 1 payment reconciliation.

The parser is pure (no DB, no API). Tests use real Entrata-format
bodies pulled from Sapphire's dev DB on 2026-04-27.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.services.payments.parsers.entrata import EntrataParser


REAL_ENTRATA_BODY_CHECK = """
Payment Processed


  PAYMENT FOR Sapphire Pool Service
  Processed

  Payment #  3151
  Property   Arbor Ridge 2
  Type       Check
  Amount     $1,776.00
  Date       04/24/2026


  For payment details, see the attached documentation.

  Thank You,
"""


REAL_ENTRATA_BODY_ACH = """
Payment Processed

  PAYMENT FOR Sapphire Pool Service
  Processed

  Payment #  9981
  Property   Pointe on Bell
  Type       ACH
  Amount     $2,450.00
  Date       04/26/2026

  Thank You,
"""


# ---------------------------------------------------------------------------
# matches()
# ---------------------------------------------------------------------------


def test_matches_entrata_sender():
    p = EntrataParser()
    assert p.matches(from_email="system@entrata.com", subject="Payment Submitted")
    assert p.matches(from_email="notifications@entrata.com", subject=None)


def test_matches_subject_fallback():
    p = EntrataParser()
    assert p.matches(
        from_email="forwarder@example.com",
        subject="Forwarded — powered by entrata payment notice",
    )


def test_does_not_match_unrelated_sender():
    p = EntrataParser()
    assert not p.matches(from_email="notifications@stripe.com", subject="Payout")
    assert not p.matches(from_email="", subject=None)


# ---------------------------------------------------------------------------
# parse() — happy paths
# ---------------------------------------------------------------------------


def test_parses_check_payment():
    drafts = EntrataParser().parse(body=REAL_ENTRATA_BODY_CHECK)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.amount == Decimal("1776.00")
    assert d.payer_name == "Arbor Ridge 2"
    assert d.property_hint == "Arbor Ridge 2"
    assert d.invoice_hint is None
    assert d.payment_method == "check"
    assert d.payment_date == date(2026, 4, 24)
    assert d.reference_number == "3151"


def test_parses_ach_payment():
    drafts = EntrataParser().parse(body=REAL_ENTRATA_BODY_ACH)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.amount == Decimal("2450.00")
    assert d.property_hint == "Pointe on Bell"
    assert d.payment_method == "ach"
    assert d.payment_date == date(2026, 4, 26)


def test_parses_two_digit_year():
    body = REAL_ENTRATA_BODY_CHECK.replace("04/24/2026", "04/24/26")
    drafts = EntrataParser().parse(body=body)
    assert drafts[0].payment_date == date(2026, 4, 24)


def test_parses_amount_with_comma():
    body = REAL_ENTRATA_BODY_CHECK.replace("$1,776.00", "$12,345.67")
    drafts = EntrataParser().parse(body=body)
    assert drafts[0].amount == Decimal("12345.67")


# ---------------------------------------------------------------------------
# parse() — degenerate inputs
# ---------------------------------------------------------------------------


def test_empty_body_returns_empty_list():
    assert EntrataParser().parse(body="") == []


def test_unparseable_body_returns_empty_list():
    assert EntrataParser().parse(body="hello world this isn't entrata format") == []


def test_missing_amount_returns_empty():
    body = REAL_ENTRATA_BODY_CHECK.replace("Amount     $1,776.00", "")
    assert EntrataParser().parse(body=body) == []


def test_missing_payment_number_returns_empty():
    body = REAL_ENTRATA_BODY_CHECK.replace("Payment #  3151", "")
    assert EntrataParser().parse(body=body) == []


def test_unknown_type_normalizes_to_other():
    body = REAL_ENTRATA_BODY_CHECK.replace("Type       Check", "Type       Wire")
    drafts = EntrataParser().parse(body=body)
    assert drafts[0].payment_method == "other"
