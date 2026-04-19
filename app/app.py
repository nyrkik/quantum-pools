"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.database import init_database, close_database, check_connection
from src.core.redis_client import get_redis, close_redis, check_redis
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from src.middleware.error_tracking import ErrorTrackingMiddleware
from src.middleware.request_id import RequestIDMiddleware
from src.core.rate_limiter import limiter
from src.api.router import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    # Sentry
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.1)
        logger.info("Sentry initialized")

    # Database
    await init_database()
    logger.info("Database initialized")

    # Redis
    try:
        redis = await get_redis()
        if redis:
            logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")

    # APScheduler for recurring billing
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()
    # Billing cycle + payment retries intentionally NOT scheduled — billing is
    # mothballed until Brian's ready to turn it on. Code is retained but dormant.
    # Re-enable by uncommenting below:
    # scheduler.add_job(_run_billing_cycle, CronTrigger(hour=6, minute=0), id="billing_cycle")
    # scheduler.add_job(_run_payment_retries, CronTrigger(hour=10, minute=0), id="payment_retries")
    # Outbound send janitor: any outbound message stuck in `queued` for more than
    # 5 minutes is presumed dead (the sender path crashed before flipping status).
    # Flip to `failed` so it surfaces in the Failed filter and the user knows.
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler.add_job(_run_outbound_send_janitor, IntervalTrigger(minutes=2), id="outbound_send_janitor")
    # Spam retention: purge category='spam' threads older than 30 days.
    # Keeps synced Gmail spam actionable without letting it grow unbounded.
    scheduler.add_job(_run_spam_retention, CronTrigger(hour=4, minute=30), id="spam_retention")
    # platform_events jobs run on UTC explicitly — the rest of the event
    # pipeline timestamps in UTC, and fixing the trigger timezone avoids
    # the twice-yearly DST jitter the host's local zone introduces.
    # platform_events partition manager: on the 25th of every month, create
    # the next month's partition ahead of time so month-end inserts never
    # hit a missing-partition error.
    scheduler.add_job(
        _run_platform_events_partition,
        CronTrigger(day=25, hour=2, minute=0, timezone="UTC"),
        id="platform_events_partition",
    )
    # platform_events retention purge: daily at 03:15 UTC, delete rows
    # older than each org's event_retention_days.
    scheduler.add_job(
        _run_platform_events_retention,
        CronTrigger(hour=3, minute=15, timezone="UTC"),
        id="platform_events_retention",
    )
    # Proposals expire-stale: daily at 04:00 UTC, mark staged proposals
    # older than 30 days as expired. Emits proposal.expired + records a
    # rejection-class learning signal per row.
    scheduler.add_job(
        _run_proposals_expire_stale,
        CronTrigger(hour=4, minute=0, timezone="UTC"),
        id="proposals_expire_stale",
    )
    # Phase 3 inbox summarizer: every 15 seconds, pick up threads whose
    # debounce window has passed and regenerate their summaries. Only
    # orgs with inbox_v2_enabled have debounce_until set (see the hook
    # in orchestrator.py), so this is a no-op for non-opted-in orgs.
    scheduler.add_job(
        _run_inbox_summarizer_sweep,
        IntervalTrigger(seconds=15),
        id="inbox_summarizer_sweep",
    )
    # Stale sweep: daily at 05:30 UTC, regenerate summaries older than
    # 7 days on threads that aren't closed — picks up new learning.
    scheduler.add_job(
        _run_inbox_summarizer_stale,
        CronTrigger(hour=5, minute=30, timezone="UTC"),
        id="inbox_summarizer_stale",
    )
    scheduler.start()
    logger.info("Scheduler started (outbound send janitor; spam retention; platform_events partition + retention; proposals expire; inbox_v2 summarizer; billing dormant; auto-send removed)")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    await close_database()
    await close_redis()
    logger.info("Shutdown complete")


async def _run_billing_cycle():
    """APScheduler job: generate recurring invoices for all orgs."""
    from src.core.database import get_db_context
    from src.services.billing_service import BillingService
    from sqlalchemy import select
    from src.models.organization import Organization

    try:
        async with get_db_context() as db:
            orgs = (await db.execute(select(Organization))).scalars().all()
            for org in orgs:
                try:
                    svc = BillingService(db)
                    await svc.generate_recurring_invoices(org.id)
                except Exception as e:
                    logger.error(f"Billing cycle failed for org {org.id}: {e}")
                    sentry_sdk.capture_exception(e)
    except Exception as e:
        logger.error(f"Billing cycle error: {e}")
        sentry_sdk.capture_exception(e)


async def _run_payment_retries():
    """APScheduler job: retry failed autopay attempts."""
    from src.core.database import get_db_context
    from src.services.billing_service import BillingService
    from sqlalchemy import select
    from src.models.organization import Organization

    try:
        async with get_db_context() as db:
            orgs = (await db.execute(select(Organization))).scalars().all()
            for org in orgs:
                try:
                    svc = BillingService(db)
                    await svc.retry_failed_payments(org.id)
                except Exception as e:
                    logger.error(f"Payment retry failed for org {org.id}: {e}")
                    sentry_sdk.capture_exception(e)
    except Exception as e:
        logger.error(f"Payment retry error: {e}")
        sentry_sdk.capture_exception(e)


async def _run_outbound_send_janitor():
    """Flip outbound messages stuck in `queued` for >5 min to `failed`.

    A queued outbound message normally lives for milliseconds — created, sent,
    flipped to sent/failed. Anything older than 5 minutes means the send path
    crashed before flipping status (the FB-24 NameError pattern). Without this
    janitor, those messages stay queued forever, invisible to the user and the
    Failed filter, and the email is silently lost.
    """
    from datetime import datetime, timedelta, timezone
    from src.core.database import get_db_context
    from src.models.agent_message import AgentMessage
    from src.services.agents.thread_manager import update_thread_status
    from sqlalchemy import select, update

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    try:
        async with get_db_context() as db:
            stuck = (await db.execute(
                select(AgentMessage.id, AgentMessage.thread_id).where(
                    AgentMessage.direction == "outbound",
                    AgentMessage.status == "queued",
                    AgentMessage.received_at < cutoff,
                )
            )).all()
            if not stuck:
                return
            ids = [s.id for s in stuck]
            thread_ids = {s.thread_id for s in stuck if s.thread_id}
            await db.execute(
                update(AgentMessage)
                .where(AgentMessage.id.in_(ids))
                .values(status="failed", delivery_error="timed out in queue (sender crashed before completing)")
            )
            await db.commit()
            logger.warning(f"Outbound janitor: flipped {len(ids)} stuck queued message(s) to failed")
            for tid in thread_ids:
                try:
                    await update_thread_status(tid)
                except Exception as e:
                    logger.warning(f"Janitor: failed to recompute thread {tid}: {e}")
            # Surface to ops via ntfy so the user knows something failed silently.
            try:
                from src.utils.notify import alert_failure
                alert_failure(
                    "outbound-email",
                    f"{len(ids)} outbound email(s) stuck in queued >5min — flipped to failed. "
                    f"Check the inbox Failed filter for thread details.",
                    cooldown_seconds=600,
                )
            except Exception:
                pass  # ntfy is best-effort
    except Exception as e:
        logger.error(f"Outbound send janitor error: {e}")


async def _run_spam_retention():
    """Purge spam threads older than 30 days.

    Gmail's own 30-day spam auto-purge eventually removes the upstream copy;
    we mirror that policy locally so synced spam doesn't accumulate. Only
    threads with ``category='spam'`` are affected — QP-classified + Gmail-
    synced spam both fall under this. Manual-override threads (someone
    rescued the thread from Spam in QP) are excluded because the rescue
    path clears ``category`` already.

    AgentMessage.thread_id has no ON DELETE cascade, so we delete messages
    first, then threads. ThreadRead does cascade. Threads with attached
    AgentAction rows (shouldn't exist for spam, but if a rule ever fires
    on a misclassified thread) are skipped to avoid FK violations.
    """
    from datetime import datetime, timedelta, timezone
    from src.core.database import get_db_context
    from src.models.agent_action import AgentAction
    from src.models.agent_message import AgentMessage
    from src.models.agent_thread import AgentThread
    from sqlalchemy import delete, select

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        async with get_db_context() as db:
            candidates = (await db.execute(
                select(AgentThread.id).where(
                    AgentThread.category == "spam",
                    AgentThread.last_message_at < cutoff,
                )
            )).scalars().all()
            if not candidates:
                return

            # Exclude any thread that unexpectedly has actions attached
            blocked = set((await db.execute(
                select(AgentAction.thread_id).where(AgentAction.thread_id.in_(candidates))
            )).scalars().all())
            targets = [tid for tid in candidates if tid not in blocked]
            if not targets:
                return

            await db.execute(
                delete(AgentMessage).where(AgentMessage.thread_id.in_(targets))
            )
            result = await db.execute(
                delete(AgentThread).where(AgentThread.id.in_(targets))
            )
            await db.commit()
            logger.info(
                f"Spam retention: purged {result.rowcount} spam threads older than 30 days "
                f"(skipped {len(blocked)} with attached actions)"
            )
    except Exception as e:
        logger.error(f"Spam retention error: {e}")
        sentry_sdk.capture_exception(e)


async def _run_platform_events_partition():
    """Create next month's `platform_events` partition ahead of time.

    Runs on the 25th of every month so there's always a buffer before
    month-end. Missing-partition INSERT errors would silently drop
    events (emit is fail-soft), so this job guards observability.
    """
    from src.core.database import get_db_context
    from src.services.events.partition_manager import ensure_next_partition
    try:
        async with get_db_context() as db:
            await ensure_next_partition(db)
    except Exception as e:
        logger.error(f"platform_events partition job error: {e}")
        sentry_sdk.capture_exception(e)


async def _run_platform_events_retention():
    """Per-org `platform_events` purge older than `event_retention_days`."""
    from src.core.database import get_db_context
    from src.services.events.retention_purge import purge_expired_events
    try:
        async with get_db_context() as db:
            await purge_expired_events(db)
    except Exception as e:
        logger.error(f"platform_events retention job error: {e}")
        sentry_sdk.capture_exception(e)


async def _run_inbox_summarizer_sweep():
    """Phase 3 — every 15s, regenerate summaries for threads whose
    debounce window has passed. Only inbox_v2-enabled orgs have rows
    with ai_summary_debounce_until set, so this is cheap when off.

    Bounded: processes at most N threads per tick so a large backlog
    can't starve the scheduler. The remainder catches up on the next
    tick.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from src.core.database import get_db_context
    from src.models.agent_thread import AgentThread
    from src.models.organization import Organization
    from src.services.agents.inbox_summarizer import InboxSummarizerService

    PER_TICK = 20

    try:
        async with get_db_context() as db:
            now = datetime.now(timezone.utc)
            # Join to orgs so we filter out any thread whose org got
            # opted out after the debounce was set. Avoids stale runs.
            result = await db.execute(
                select(AgentThread.id).join(
                    Organization,
                    Organization.id == AgentThread.organization_id,
                ).where(
                    AgentThread.ai_summary_debounce_until.isnot(None),
                    AgentThread.ai_summary_debounce_until <= now,
                    Organization.inbox_v2_enabled == True,  # noqa: E712
                ).limit(PER_TICK)
            )
            thread_ids = [row[0] for row in result.all()]

            if not thread_ids:
                return

            svc = InboxSummarizerService(db)
            for tid in thread_ids:
                try:
                    await svc.summarize_thread(tid)
                    await db.commit()
                except Exception as e:
                    logger.error(f"inbox_summarizer tick failed for {tid}: {e}")
                    await db.rollback()
    except Exception as e:
        logger.error(f"inbox_summarizer sweep error: {e}")
        sentry_sdk.capture_exception(e)


async def _run_inbox_summarizer_stale():
    """Daily 05:30 UTC — regenerate stale summaries (>7 days old) on
    threads that aren't closed. Picks up new learning without waiting
    for the next inbound.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from src.core.database import get_db_context
    from src.models.agent_thread import AgentThread
    from src.models.organization import Organization
    from src.services.agents.inbox_summarizer import InboxSummarizerService

    STALE_DAYS = 7
    PER_RUN = 500

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
        async with get_db_context() as db:
            result = await db.execute(
                select(AgentThread.id).join(
                    Organization,
                    Organization.id == AgentThread.organization_id,
                ).where(
                    AgentThread.ai_summary_generated_at.isnot(None),
                    AgentThread.ai_summary_generated_at < cutoff,
                    AgentThread.status.notin_(["archived", "closed"]),
                    Organization.inbox_v2_enabled == True,  # noqa: E712
                ).limit(PER_RUN)
            )
            thread_ids = [row[0] for row in result.all()]

            if not thread_ids:
                logger.info("inbox_summarizer_stale: nothing to refresh")
                return

            svc = InboxSummarizerService(db)
            refreshed = 0
            for tid in thread_ids:
                try:
                    await svc.summarize_thread(tid)
                    await db.commit()
                    refreshed += 1
                except Exception as e:
                    logger.error(f"inbox_summarizer_stale {tid}: {e}")
                    await db.rollback()
            logger.info(f"inbox_summarizer_stale: refreshed {refreshed} threads")
    except Exception as e:
        logger.error(f"inbox_summarizer stale job error: {e}")
        sentry_sdk.capture_exception(e)


async def _run_proposals_expire_stale():
    """Mark staged agent_proposals older than 30 days as expired.

    Each expired row gets a proposal.expired event + a rejection-class
    learning record ("user never got around to acting on this"). Feeds
    back into agent tuning — patterns that keep expiring are patterns
    the agent should stop proposing.
    """
    from src.core.database import get_db_context
    from src.services.proposals import ProposalService
    try:
        async with get_db_context() as db:
            service = ProposalService(db)
            n = await service.expire_stale(age_days=30)
            await db.commit()
            if n:
                logger.info(f"proposals: expired {n} stale proposals")
    except Exception as e:
        logger.error(f"proposals expire-stale job error: {e}")
        sentry_sdk.capture_exception(e)


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantumPools API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url="/api/redoc" if settings.environment != "production" else None,
    )

    # Rate limiter (slowapi)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error tracking
    app.add_middleware(ErrorTrackingMiddleware)

    # Request ID — registered AFTER error tracking so it runs FIRST (outermost).
    # Sets request_id contextvar read by PlatformEventService.emit() and by
    # the error tracking middleware for correlation. See
    # docs/ai-platform-phase-1.md §5.2.
    app.add_middleware(RequestIDMiddleware)

    # Security headers
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Static file serving for uploads.
    # IMPORTANT: /uploads/attachments is intentionally blocked here — message
    # attachments are sensitive (customer photos, contracts, scans) and must
    # only be served via the authenticated /api/v1/attachments/{id}/file
    # endpoint which verifies organization_id ownership. Other subdirs
    # (branding, photos, visits, charges, feedback) are still served as
    # static; tighten those separately if/when their content becomes sensitive.
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)

    @app.middleware("http")
    async def block_static_attachments(request: Request, call_next):
        # Block direct access to /uploads/attachments/* — those go through auth.
        if request.url.path.startswith("/uploads/attachments/"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Use /api/v1/attachments/{id}/file (auth required)"},
            )
        return await call_next(request)

    app.mount("/uploads", StaticFiles(directory=str(upload_path)), name="uploads")

    # Global exception handlers
    from src.core.exceptions import NotFoundError, ValidationError as BizValidationError

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(BizValidationError)
    async def validation_handler(request: Request, exc: BizValidationError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Routes
    app.include_router(api_router)

    # WebSocket (mounted directly — not under API router prefix)
    from src.api.v1.ws import router as ws_router
    app.include_router(ws_router)

    @app.get("/api/health")
    async def health():
        db_ok = await check_connection()
        redis_ok = await check_redis()
        return {
            "status": "healthy" if db_ok else "degraded",
            "database": "connected" if db_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
        }

    return app


app = create_app()
