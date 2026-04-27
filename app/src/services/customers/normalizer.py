"""CompanyNameNormalizer — fuzzy-match a candidate company_name against
the org's existing distinct values to detect spelling variations.

Two surfaces:
- `find_similar(org_id, candidate)` — returns existing names that fuzzy-
  match. Used by the customer-form typeahead and by the backfill
  script's clustering step.
- `cluster_existing(org_id)` — groups all existing distinct
  company_names into clusters of likely-same-company. Used once-off by
  the backfill script.

Pure rapidfuzz scoring, no LLM. We can wire AI fallback later if a
B2B customer wants smarter merging (acronyms, regional suffixes), but
v1 keeps it deterministic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz, process
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.customer import Customer


SIMILAR_THRESHOLD = 85  # token_set_ratio; calibrated against Sapphire data
MAX_SUGGESTIONS = 5


@dataclass
class SimilarMatch:
    """One fuzzy hit. `score` is a 0-100 rapidfuzz score."""
    name: str
    score: int
    customer_count: int


@dataclass
class CompanyCluster:
    """A group of existing names the normalizer believes refer to the
    same company. `canonical` is the mode-wins pick (most-used spelling;
    ties → longer name). Caller can override before applying."""
    canonical: str
    members: list[str]            # all spellings in the cluster (incl. canonical)
    counts: dict[str, int]        # spelling → row count
    total_rows: int


class CompanyNameNormalizer:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Live lookup (used by the customer form's typeahead)
    # ------------------------------------------------------------------

    async def _existing_names_with_counts(
        self, org_id: str,
    ) -> list[tuple[str, int]]:
        rows = (await self.db.execute(
            select(Customer.company_name, func.count(Customer.id))
            .where(
                Customer.organization_id == org_id,
                Customer.company_name.is_not(None),
                Customer.company_name != "",
            )
            .group_by(Customer.company_name)
        )).all()
        return [(name, count) for name, count in rows if name]

    async def find_similar(
        self,
        org_id: str,
        candidate: str,
        *,
        threshold: int = SIMILAR_THRESHOLD,
        max_results: int = MAX_SUGGESTIONS,
    ) -> list[SimilarMatch]:
        """Suggestions for an in-progress customer form. Returns at most
        `max_results` existing names that score ≥ threshold. Excludes
        exact matches (case-sensitive) — if the candidate already
        matches one of the org's spellings exactly, no suggestion needed.

        An exact case-INsensitive match (e.g. user typed "conam" when
        "Conam" exists) IS surfaced — that's the canonical-form catch.
        """
        candidate = (candidate or "").strip()
        if not candidate or len(candidate) < 2:
            return []

        existing = await self._existing_names_with_counts(org_id)
        if not existing:
            return []

        names = [n for n, _ in existing]
        counts_by_name = dict(existing)

        results: list[SimilarMatch] = []
        # rapidfuzz extract handles the scoring + ranking efficiently.
        # processor=str.lower so 'CONAM' matches 'Conam' case-insensitively.
        for name, score, _idx in process.extract(
            candidate, names,
            scorer=fuzz.token_set_ratio,
            processor=str.lower,
            limit=max_results * 3,
        ):
            if score < threshold:
                continue
            # Skip exact case-sensitive match (no suggestion needed).
            if name == candidate:
                continue
            # KEEP exact-case-insensitive matches — they're suggestions
            # to use the canonical casing.
            results.append(SimilarMatch(
                name=name, score=int(score),
                customer_count=counts_by_name.get(name, 0),
            ))
            if len(results) >= max_results:
                break
        return results

    # ------------------------------------------------------------------
    # Clustering (used by the backfill script)
    # ------------------------------------------------------------------

    async def cluster_existing(
        self,
        org_id: str,
        *,
        threshold: int = SIMILAR_THRESHOLD,
    ) -> list[CompanyCluster]:
        """Group all distinct company_names in the org into clusters of
        likely-same-company. Single-row clusters (no fuzzy neighbors)
        are NOT returned — only multi-spelling clusters surface."""
        existing = await self._existing_names_with_counts(org_id)
        return _cluster(existing, threshold=threshold)


def _cluster(
    name_counts: Iterable[tuple[str, int]],
    *,
    threshold: int,
) -> list[CompanyCluster]:
    """Pure clustering — no DB. Pulled out for unit testability."""
    names = [(n, c) for n, c in name_counts if n]
    if not names:
        return []

    # Greedy single-link clustering. Walk the names; for each, find any
    # existing cluster member that fuzzy-matches above threshold; if so,
    # join. Otherwise start a new cluster.
    clusters: list[list[str]] = []
    for name, _count in names:
        joined = False
        name_lower = name.lower()
        for cluster in clusters:
            if any(
                fuzz.token_set_ratio(name_lower, member.lower()) >= threshold
                for member in cluster
            ):
                cluster.append(name)
                joined = True
                break
        if not joined:
            clusters.append([name])

    counts = dict(names)
    output: list[CompanyCluster] = []
    for members in clusters:
        if len(members) < 2:
            continue  # singleton clusters aren't interesting
        # Mode-wins canonical: highest count, ties → longer name.
        canonical = max(
            members,
            key=lambda n: (counts.get(n, 0), len(n)),
        )
        output.append(CompanyCluster(
            canonical=canonical,
            members=sorted(members),
            counts={m: counts.get(m, 0) for m in members},
            total_rows=sum(counts.get(m, 0) for m in members),
        ))
    # Largest-impact clusters first (most rows affected).
    output.sort(key=lambda c: c.total_rows, reverse=True)
    return output
