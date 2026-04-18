"""Background-job correlation context.

Any APScheduler job (or other background worker invocation) that wants its
emitted events to be correlated should wrap its body in ``job_run_context``::

    async with job_run_context("retention_purge") as job_run_id:
        ...  # events emitted here inherit job_run_id

Produces a fresh UUID4 per invocation. Nested contexts are allowed (inner
overrides outer for the duration of the inner block), but in practice jobs
don't nest.

Design reference: docs/ai-platform-phase-1.md §5.3.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from src.services.events.platform_event_service import (
    set_job_run_id,
    reset_job_run_id,
)


@asynccontextmanager
async def job_run_context(job_name: str) -> AsyncIterator[str]:
    """Assign a `job_run_id` to all events emitted inside the block.

    Args:
        job_name: human-readable name — unused by the context itself but
            handy for call-site clarity and logging.

    Yields:
        The generated `job_run_id` (UUID4 string).
    """
    job_run_id = str(uuid.uuid4())
    token = set_job_run_id(job_run_id)
    try:
        yield job_run_id
    finally:
        reset_job_run_id(token)


def current_job_run_id() -> Optional[str]:
    """Read the current `job_run_id` without setting one. Useful for logs."""
    from src.services.events.platform_event_service import _current_job_run_id
    return _current_job_run_id()
