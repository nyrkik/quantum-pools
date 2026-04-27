"""Manual workflow_observer scan — dry-run or commit.

Phase 6 step 15. Use this to:
- Smoke-test detector wiring without waiting for the daily 06:00 UTC cron
- Inspect what would surface for an org before staging anything
- Tune thresholds against real production data

Usage:
    python scripts/run_workflow_observer.py --org-id <uuid>            # dry run (rollback)
    python scripts/run_workflow_observer.py --org-id <uuid> --commit   # actually stage

The dry-run path emits observer.scan_complete (which gets rolled back
along with anything else) — the warning "platform_event.emit failed"
is expected on rollback and benign.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.services.agents.workflow_observer import WorkflowObserverAgent


async def main(org_id: str, commit: bool, window_days: int):
    db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://quantumpools:quantumpools@localhost:7062/quantumpools")
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        agent = WorkflowObserverAgent(db)
        result = await agent.scan_org(org_id, window_days=window_days)
        if commit:
            await db.commit()
            print(f"✓ Committed: {result.proposals_staged} proposals staged for org {org_id}")
        else:
            await db.rollback()
            print(f"DRY RUN (rolled back). Run with --commit to stage.")

        print()
        print(f"=== Scan result (org {org_id}, window {window_days}d) ===")
        print(f"  detectors_run                  = {result.detectors_run}")
        print(f"  proposals_staged (would-be)    = {result.proposals_staged}")
        print(f"  skipped_below_threshold        = {result.proposals_skipped_below_threshold}")
        print(f"  skipped_dedup                  = {result.proposals_skipped_dedup}")
        print(f"  skipped_muted                  = {result.proposals_skipped_muted}")
        print(f"  duration_ms                    = {result.duration_ms}")
        if result.errors:
            print(f"  errors:")
            for e in result.errors:
                print(f"    - {e}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True, help="Organization UUID to scan")
    parser.add_argument("--commit", action="store_true",
                        help="Actually stage proposals (default: dry run + rollback)")
    parser.add_argument("--window-days", type=int, default=14,
                        help="Scan window in days (default: 14)")
    args = parser.parse_args()

    asyncio.run(main(args.org_id, args.commit, args.window_days))
