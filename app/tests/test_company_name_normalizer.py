"""Tests for CompanyNameNormalizer.

Real Sapphire data inspired the test cases:
- Conam vs CONAM (case)
- Bright PM vs BrightPM (whitespace)
- BLVD vs BLVD Residential (token superset)
- Westcal vs WestCal (case)
- AIR (singleton — should NOT cluster with itself)
"""

from __future__ import annotations

import uuid

import pytest

from src.models.customer import Customer
from src.services.customers.normalizer import (
    CompanyCluster,
    CompanyNameNormalizer,
    SIMILAR_THRESHOLD,
    _cluster,
)


# ---------------------------------------------------------------------------
# Pure clustering (no DB)
# ---------------------------------------------------------------------------


def test_cluster_groups_case_variants():
    out = _cluster([("Conam", 3), ("CONAM", 2)], threshold=SIMILAR_THRESHOLD)
    assert len(out) == 1
    cluster = out[0]
    assert set(cluster.members) == {"Conam", "CONAM"}
    assert cluster.canonical == "Conam"  # mode-wins (3 > 2)
    assert cluster.total_rows == 5


def test_cluster_groups_whitespace_variants():
    out = _cluster([("Bright PM", 2), ("BrightPM", 1)], threshold=SIMILAR_THRESHOLD)
    assert len(out) == 1
    assert set(out[0].members) == {"Bright PM", "BrightPM"}
    assert out[0].canonical == "Bright PM"


def test_cluster_groups_token_superset():
    """token_set_ratio treats 'BLVD' as a perfect match against 'BLVD
    Residential' because all tokens of one are in the other."""
    out = _cluster([("BLVD", 16), ("BLVD Residential", 1)], threshold=SIMILAR_THRESHOLD)
    assert len(out) == 1
    assert set(out[0].members) == {"BLVD", "BLVD Residential"}
    assert out[0].canonical == "BLVD"  # 16 > 1 wins


def test_cluster_canonical_ties_break_to_longer():
    """When two names have equal count, longer wins as canonical
    (more-specific is usually the right call)."""
    out = _cluster([("Foo", 5), ("Foo Inc", 5)], threshold=SIMILAR_THRESHOLD)
    assert out[0].canonical == "Foo Inc"


def test_cluster_excludes_singletons():
    out = _cluster(
        [("AIR", 1), ("Eugene Burger Management", 1), ("Conam", 3), ("CONAM", 2)],
        threshold=SIMILAR_THRESHOLD,
    )
    members = {m for c in out for m in c.members}
    # AIR + Eugene Burger don't fuzzy-cluster with anything
    assert "AIR" not in members
    assert "Eugene Burger Management" not in members
    # Conam pair did
    assert {"Conam", "CONAM"}.issubset(members)


def test_cluster_orders_by_total_impact():
    """Largest cluster (by total customer count) sorts first."""
    out = _cluster(
        [
            ("Westcal", 1), ("WestCal", 19),
            ("Conam", 3), ("CONAM", 2),
        ],
        threshold=SIMILAR_THRESHOLD,
    )
    assert len(out) == 2
    # WestCal cluster has 20 rows, Conam has 5
    assert out[0].canonical == "WestCal"
    assert out[1].canonical == "Conam"


def test_cluster_does_not_merge_unrelated_names():
    out = _cluster(
        [("Greystar", 6), ("Bright PM", 2), ("AIR", 1), ("BLVD", 16)],
        threshold=SIMILAR_THRESHOLD,
    )
    assert out == []  # no clusters; all distinct


# ---------------------------------------------------------------------------
# find_similar (DB-backed, single-org)
# ---------------------------------------------------------------------------


async def _seed(db, org_id: str, names: list[tuple[str, int]]):
    for name, count in names:
        for _ in range(count):
            db.add(Customer(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                first_name=f"prop-{uuid.uuid4().hex[:6]}",
                last_name="",
                company_name=name,
            ))
    await db.flush()


@pytest.mark.asyncio
async def test_find_similar_suggests_existing_canonical(db_session, org_a):
    await _seed(db_session, org_a.id, [("Conam", 5), ("Greystar", 2)])
    await db_session.commit()
    norm = CompanyNameNormalizer(db_session)
    out = await norm.find_similar(org_a.id, "CONAM")
    names = [m.name for m in out]
    assert "Conam" in names  # case-insensitive match surfaces


@pytest.mark.asyncio
async def test_find_similar_skips_exact_case_match(db_session, org_a):
    """User types the exact existing spelling — no suggestion needed."""
    await _seed(db_session, org_a.id, [("Conam", 5)])
    await db_session.commit()
    norm = CompanyNameNormalizer(db_session)
    out = await norm.find_similar(org_a.id, "Conam")
    assert out == []


@pytest.mark.asyncio
async def test_find_similar_returns_empty_for_short_query(db_session, org_a):
    await _seed(db_session, org_a.id, [("Conam", 5)])
    await db_session.commit()
    norm = CompanyNameNormalizer(db_session)
    assert await norm.find_similar(org_a.id, "C") == []
    assert await norm.find_similar(org_a.id, "") == []


@pytest.mark.asyncio
async def test_find_similar_includes_customer_count(db_session, org_a):
    await _seed(db_session, org_a.id, [("Greystar", 6), ("Grey Star", 1)])
    await db_session.commit()
    norm = CompanyNameNormalizer(db_session)
    out = await norm.find_similar(org_a.id, "GreyStar")
    by_name = {m.name: m for m in out}
    assert by_name["Greystar"].customer_count == 6
    assert by_name["Grey Star"].customer_count == 1


@pytest.mark.asyncio
async def test_find_similar_org_scoped(db_session, org_a, org_b):
    """Customer counts from a different org must NOT leak."""
    await _seed(db_session, org_a.id, [("Conam", 5)])
    await _seed(db_session, org_b.id, [("Conam", 99)])
    await db_session.commit()
    norm = CompanyNameNormalizer(db_session)
    out = await norm.find_similar(org_a.id, "CONAM")
    assert any(m.name == "Conam" for m in out)
    # The match's customer_count reflects org_a only.
    assert next(m for m in out if m.name == "Conam").customer_count == 5


# ---------------------------------------------------------------------------
# cluster_existing (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cluster_existing_returns_real_clusters(db_session, org_a):
    await _seed(db_session, org_a.id, [
        ("Conam", 3), ("CONAM", 2),
        ("WestCal", 19), ("Westcal", 1),
        ("AIR", 1),  # singleton, should not appear
    ])
    await db_session.commit()
    norm = CompanyNameNormalizer(db_session)
    clusters = await norm.cluster_existing(org_a.id)
    by_canonical = {c.canonical: c for c in clusters}
    assert "WestCal" in by_canonical
    assert "Conam" in by_canonical
    assert "AIR" not in by_canonical
    assert by_canonical["WestCal"].total_rows == 20
    assert by_canonical["Conam"].total_rows == 5
