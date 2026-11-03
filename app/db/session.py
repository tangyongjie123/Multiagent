"""异步 PostgreSQL engine 与 session 管理。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.base import Base


class DatabaseUnavailableError(RuntimeError):
    """数据库未配置或无法连接。"""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """按需创建 PostgreSQL 异步引擎。"""

    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    if settings.postgres_async_dsn is None:
        raise DatabaseUnavailableError("PostgreSQL 尚未配置")

    _engine = create_async_engine(
        settings.postgres_async_dsn,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """返回 PostgreSQL session 工厂。"""

    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：提供请求级数据库会话。"""

    async with get_session_factory()() as session:
        yield session


async def initialize_database() -> None:
    """开发阶段按需创建表；生产环境应使用 Alembic。"""

    settings = get_settings()
    if not settings.postgres_configured or not settings.auto_create_tables:
        return

    import app.db.models  # noqa: F401

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                "ALTER TABLE runs ADD COLUMN IF NOT EXISTS "
                "worker_id VARCHAR(64)"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE runs ADD COLUMN IF NOT EXISTS "
                "heartbeat_at TIMESTAMPTZ"
            )
        )


async def check_database() -> bool:
    """执行轻量查询验证数据库连接。"""

    if not get_settings().postgres_configured:
        return False
    async with get_engine().connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        return bool(result.scalar_one() == 1)


async def close_database() -> None:
    """释放数据库连接池。"""

    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
