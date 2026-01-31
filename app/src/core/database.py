"""
QuantumPools - Database Connection Management

ARCHITECTURE DECISION: Migration-Only Database Initialization
=============================================================
Alembic migrations are the ONLY way tables get created.
We NEVER use Base.metadata.create_all().

On startup, run `alembic upgrade head` (idempotent — safe on any state).
"""

from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import logging
import subprocess
import os

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker] = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "sslmode=" in db_url:
            db_url = db_url.replace("sslmode=", "ssl=")

        _engine = create_async_engine(
            db_url,
            echo=settings.sql_echo,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        logger.info("Database engine created")
    return _engine


def get_session_maker() -> async_sessionmaker:
    global _session_maker
    if _session_maker is None:
        engine = get_engine()
        _session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False,
        )
    return _session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context():
    """Context manager for DB sessions outside FastAPI deps."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def _run_alembic_upgrade():
    try:
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        alembic_bin = None
        for candidate in [
            os.path.join(app_dir, "..", "venv", "bin", "alembic"),
            os.path.join(app_dir, "venv", "bin", "alembic"),
        ]:
            if os.path.exists(candidate):
                alembic_bin = candidate
                break
        if alembic_bin is None:
            alembic_bin = "alembic"

        result = subprocess.run(
            [alembic_bin, "upgrade", "head"],
            cwd=app_dir,
            capture_output=True,
            text=True,
            env={**os.environ, "DATABASE_URL": get_settings().database_url},
        )
        if result.returncode == 0:
            logger.info(f"Alembic upgrade head completed: {result.stdout.strip()}")
        else:
            logger.error(f"Alembic upgrade failed: {result.stderr}")
            raise RuntimeError(f"Failed to run alembic upgrade: {result.stderr}")
    except FileNotFoundError:
        logger.warning("Alembic not found - migrations must be run manually")
    except Exception as e:
        logger.error(f"Error running alembic upgrade: {e}")
        raise


async def init_database():
    """Initialize database via alembic upgrade head."""
    logger.info("=" * 60)
    logger.info("DATABASE INITIALIZATION - Migrations Only")
    logger.info("=" * 60)

    engine = get_engine()
    async with engine.connect() as conn:
        try:
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'alembic_version')"
            ))
            alembic_exists = result.scalar()
            current_revision = None
            if alembic_exists:
                result = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                row = result.first()
                current_revision = row[0] if row else None
            logger.info(f"  alembic_version table exists: {alembic_exists}")
            logger.info(f"  Current revision: {current_revision or 'None'}")
        except Exception as e:
            logger.warning(f"Error checking database state: {e}")

    logger.info("  Running alembic upgrade head...")
    await _run_alembic_upgrade()
    logger.info("=" * 60)
    logger.info("DATABASE INITIALIZATION COMPLETE")
    logger.info("=" * 60)


async def check_connection() -> bool:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def close_database():
    global _engine, _session_maker
    if _engine:
        await _engine.dispose()
        logger.info("Database engine closed")
    _engine = None
    _session_maker = None
