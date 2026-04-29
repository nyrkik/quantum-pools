"""Phase 8.5: Gmail rate-limit shared parking.

Locks in the cross-path 24h-bucket protection. The 2026-04-28 lockout
went 24h+ dark; without these, a bulk dunning run or broadcast on a
Gmail-mode org could re-trigger it.

Covered:
- `parse_gmail_retry_after` reads both header and body forms.
- `record_gmail_rate_limit` writes only forward — never shrinks an
  existing park (so a softer 429 from a different path can't reduce
  the window).
- `is_gmail_rate_limited` auto-clears when the timestamp passes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.models.email_integration import (
    EmailIntegration,
    IntegrationStatus,
    IntegrationType,
)
from src.services.gmail.rate_limit import (
    is_gmail_rate_limited,
    parse_gmail_retry_after,
    record_gmail_rate_limit,
)


@pytest.mark.asyncio
async def test_parse_retry_after_header():
    class _Err(Exception):
        headers = {"Retry-After": "900"}
    out = parse_gmail_retry_after(_Err("doesn't matter"))
    assert out is not None
    delta = (out - datetime.now(timezone.utc)).total_seconds()
    # Header parse → +900s ± a few seconds
    assert 870 <= delta <= 910


@pytest.mark.asyncio
async def test_parse_retry_after_body():
    err = Exception(
        'HttpError 429 ... "User-rate limit exceeded.  '
        'Retry after 2026-04-29T22:46:58.059Z". Details: ...'
    )
    out = parse_gmail_retry_after(err)
    assert out == datetime(2026, 4, 29, 22, 46, 58, 59000, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_parse_retry_after_no_match():
    assert parse_gmail_retry_after(Exception("totally unrelated error")) is None


@pytest.mark.asyncio
async def test_record_and_check_park(db_session, org_a):
    integ = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        type=IntegrationType.gmail_api.value,
        status=IntegrationStatus.connected.value,
        account_email="test@example.com",
    )
    db_session.add(integ)
    await db_session.commit()

    # Not parked initially.
    assert not await is_gmail_rate_limited(integ.id)

    # Park 5 min into the future → check returns True.
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    await record_gmail_rate_limit(integ.id, future)
    assert await is_gmail_rate_limited(integ.id)


@pytest.mark.asyncio
async def test_record_only_extends_never_shrinks(db_session, org_a):
    integ = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        type=IntegrationType.gmail_api.value,
        status=IntegrationStatus.connected.value,
        account_email="test@example.com",
    )
    db_session.add(integ)
    await db_session.commit()

    long_window = datetime.now(timezone.utc) + timedelta(hours=12)
    short_window = datetime.now(timezone.utc) + timedelta(minutes=15)

    # Set the long window first.
    await record_gmail_rate_limit(integ.id, long_window)
    # Then a softer 429 from a different path tries to set a shorter
    # window — must NOT reduce the existing park.
    await record_gmail_rate_limit(integ.id, short_window)

    # Re-fetch and confirm the long window survived.
    fresh = (await db_session.execute(
        select(EmailIntegration).where(EmailIntegration.id == integ.id)
    )).scalar_one_or_none()
    await db_session.refresh(fresh)
    stored = fresh.gmail_retry_after_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    assert abs((stored - long_window).total_seconds()) < 1


@pytest.mark.asyncio
async def test_park_auto_clears_when_expired(db_session, org_a):
    integ = EmailIntegration(
        id=str(uuid.uuid4()),
        organization_id=org_a.id,
        type=IntegrationType.gmail_api.value,
        status=IntegrationStatus.connected.value,
        account_email="test@example.com",
    )
    db_session.add(integ)
    await db_session.commit()

    # Already-passed timestamp.
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await record_gmail_rate_limit(integ.id, past)

    # Hmm — record_gmail_rate_limit only writes forward. The past timestamp
    # would be skipped against an existing NULL since None is treated as
    # "no existing park". Let's set it directly via SQL to test the clear path.
    fresh = (await db_session.execute(
        select(EmailIntegration).where(EmailIntegration.id == integ.id)
    )).scalar_one_or_none()
    fresh.gmail_retry_after_at = past
    await db_session.commit()

    # is_gmail_rate_limited should see the past timestamp, return False,
    # AND clear the column so the next call doesn't pay the lookup.
    assert not await is_gmail_rate_limited(integ.id)
    await db_session.refresh(fresh)
    assert fresh.gmail_retry_after_at is None
