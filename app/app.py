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
    scheduler.add_job(_run_billing_cycle, CronTrigger(hour=6, minute=0), id="billing_cycle")
    scheduler.add_job(_run_payment_retries, CronTrigger(hour=10, minute=0), id="payment_retries")
    scheduler.add_job(_send_auto_sent_digest, CronTrigger(day_of_week="mon", hour=14, minute=0), id="auto_sent_digest")
    scheduler.start()
    logger.info("Scheduler started (billing, payment retries, weekly auto-sent digest)")

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


async def _send_auto_sent_digest():
    """Weekly digest of auto-sent AI replies per org. Emails the owner."""
    from src.core.database import get_db_context
    from src.services.email_service import EmailService
    from sqlalchemy import select, func, desc
    from datetime import datetime, timedelta, timezone
    from src.models.organization import Organization
    from src.models.agent_message import AgentMessage
    from src.models.agent_thread import AgentThread
    from src.models.user import User
    from src.models.organization_user import OrganizationUser

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    try:
        async with get_db_context() as db:
            orgs = (await db.execute(select(Organization))).scalars().all()
            for org in orgs:
                try:
                    # Count auto-sent in past 7 days
                    messages = (await db.execute(
                        select(AgentMessage, AgentThread)
                        .join(AgentThread, AgentThread.id == AgentMessage.thread_id)
                        .where(
                            AgentMessage.organization_id == org.id,
                            AgentMessage.status == "auto_sent",
                            AgentMessage.sent_at >= week_ago,
                        )
                        .order_by(desc(AgentMessage.sent_at))
                    )).all()

                    if not messages:
                        continue

                    # Find org owner
                    owner_user = (await db.execute(
                        select(User)
                        .join(OrganizationUser, OrganizationUser.user_id == User.id)
                        .where(
                            OrganizationUser.organization_id == org.id,
                            OrganizationUser.role == "owner",
                        ).limit(1)
                    )).scalar_one_or_none()
                    if not owner_user or not owner_user.email:
                        continue

                    # Build digest body
                    lines = [f"Last week, AI auto-sent {len(messages)} {'reply' if len(messages) == 1 else 'replies'}:\n"]
                    by_category = {}
                    for msg, thread in messages:
                        cat = msg.category or "general"
                        by_category[cat] = by_category.get(cat, 0) + 1
                        customer = thread.customer_name or msg.from_email
                        lines.append(f"• [{cat}] {customer}: {msg.subject[:60] if msg.subject else '(no subject)'}")
                    lines.append("\nBy category:")
                    for cat, cnt in sorted(by_category.items(), key=lambda x: -x[1]):
                        lines.append(f"  {cat}: {cnt}")
                    lines.append("\nReview any of these at https://app.quantumpoolspro.com/inbox (click the Auto-Sent filter).")

                    body = "\n".join(lines)

                    from src.services.email_service import EmailMessage
                    svc = EmailService(db)
                    await svc.send_email(org.id, EmailMessage(
                        to=owner_user.email,
                        subject=f"Weekly AI auto-send digest — {len(messages)} replies",
                        text_body=body,
                    ))
                    logger.info(f"Sent auto-send digest to {owner_user.email}: {len(messages)} replies")
                except Exception as e:
                    logger.error(f"Digest failed for org {org.id}: {e}")
    except Exception as e:
        logger.error(f"Auto-sent digest error: {e}")
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

    # Security headers
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Static file serving for uploads
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
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
