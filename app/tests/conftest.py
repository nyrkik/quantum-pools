"""Shared pytest fixtures.

Test isolation strategy:
- Dedicated `quantumpools_test` Postgres database (created once: `CREATE DATABASE
  quantumpools_test OWNER quantumpools;`)
- Schema is dropped + recreated at the start of each test session
- Each test runs inside a SAVEPOINT; rollback at end means tests cannot leak
  state into each other
- Webhook secrets and Fernet keys are set to test values BEFORE any src.*
  module is imported, so production .env values cannot bleed in

This is the foundation for every test in tests/. Tests that need DB write
access take the `db_session` fixture; tests that hit FastAPI endpoints take
`async_client`. Org-scoped tests use `org_a` / `org_b` to verify isolation.
"""

from __future__ import annotations

import os
import uuid

# IMPORTANT: set env BEFORE any src.* import. The settings module reads at
# import time, so any change after that has no effect.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://quantumpools:quantumpools@localhost:7062/quantumpools_test",
)
# Stable Fernet key for tests so EmailIntegration token tests are reproducible.
os.environ["EMAIL_INTEGRATION_KEY"] = "Z3F0LXRlc3Rrcm9rdW50ZXMteW9wbnVsbHRlc3QtMTIzNDU2Nzg="
# Webhook auth token for webhook-signature tests.
os.environ["POSTMARK_WEBHOOK_TOKEN"] = "test-webhook-token-for-pytest"
# Disable Sentry in tests.
os.environ["SENTRY_DSN"] = ""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Now safe to import.
from src.core.database import Base


# Build a dedicated engine for tests — bypasses src.core.database's lazy global
# so we don't accidentally pick up production settings.
# NullPool: pytest-asyncio creates a fresh event loop per test (function loop
# scope). A pooled connection from a previous loop becomes stale ("got Future
# attached to a different loop"). NullPool avoids reuse — every operation gets
# a fresh asyncpg connection on the current loop.
_test_engine = create_async_engine(
    os.environ["DATABASE_URL"], echo=False, future=True, poolclass=NullPool,
)
_TestSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


_SCHEMA_READY = False


def _assert_test_database():
    """Safety rail: refuse to drop schema on anything other than a test DB.

    The test DB URL must contain 'test' in the database name. Without this
    check, a misconfigured TEST_DATABASE_URL could DROP SCHEMA on production.
    """
    url = os.environ["DATABASE_URL"]
    # Extract the database name after the last '/'
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in db_name.lower():
        raise RuntimeError(
            f"Refusing to run tests against database '{db_name}' — "
            f"name must contain 'test'. Check TEST_DATABASE_URL."
        )


async def _ensure_schema():
    """Drop + recreate schema once per process.

    We DROP SCHEMA public CASCADE then CREATE SCHEMA public — this sidesteps
    the circular-FK problem (estimate_approvals ↔ invoices) that prevents
    SQLAlchemy's Base.metadata.drop_all from working, while guaranteeing
    the test DB always matches the current model state.

    Previous approach (create_all only, no drop) silently let column
    additions drift out of sync with prod schema — discovered 2026-04-18
    when `invoices.internal_notes` was missing from the test DB.

    Cost: ~5-10 seconds at session start. Runs once per pytest process,
    amortized across all tests in the run.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    _assert_test_database()
    import src.models  # noqa: F401  — triggers all model imports for metadata
    from sqlalchemy import text
    async with _test_engine.begin() as conn:
        # Drop everything, then rebuild from current model metadata.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        await conn.run_sync(Base.metadata.create_all)
    _SCHEMA_READY = True


async def _truncate_all():
    """TRUNCATE every user table CASCADE — wipes data without dropping schema."""
    from sqlalchemy import text
    async with _test_engine.begin() as conn:
        # Get every table name in our metadata, then TRUNCATE in one statement.
        names = [t.name for t in Base.metadata.sorted_tables]
        if names:
            quoted = ", ".join(f'"{n}"' for n in names)
            await conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """A session per test against the test DB.

    Strategy: TRUNCATE every table before each test. This is simpler than
    nested SAVEPOINT transactions (asyncpg + SQLAlchemy 2.0 don't always
    cooperate well there — got "another operation is in progress" errors)
    and slow-but-bulletproof at our scale (a few dozen tables).

    Tests are free to commit. The next test starts on a clean slate.
    """
    await _ensure_schema()
    await _truncate_all()
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        await session.close()


# ------------------------------------------------------------------
# Org/user fixtures — used by every cross-tenant isolation test.
# ------------------------------------------------------------------


@pytest_asyncio.fixture
async def org_a(db_session):
    """Sample organization A. Pair with org_b for cross-tenant tests."""
    from src.models.organization import Organization
    org = Organization(
        id=str(uuid.uuid4()),
        name="Test Org Alpha",
        slug=f"test-a-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    return org


@pytest_asyncio.fixture
async def org_b(db_session):
    """Sample organization B. Used to verify isolation from org_a."""
    from src.models.organization import Organization
    org = Organization(
        id=str(uuid.uuid4()),
        name="Test Org Beta",
        slug=f"test-b-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    return org
