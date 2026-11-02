"""LangGraph PostgreSQL checkpoint 生命周期管理。"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from app.core.config import get_settings

_exit_stack: AsyncExitStack | None = None
_checkpointer: Any = None
_initialization_error: str | None = None


async def initialize_checkpointer() -> None:
    """连接 PostgreSQL 并初始化 LangGraph checkpoint 表。"""

    global _checkpointer, _exit_stack, _initialization_error
    settings = get_settings()
    if not settings.postgres_configured or settings.postgres_libpq_dsn is None:
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    stack = AsyncExitStack()
    try:
        checkpointer = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(settings.postgres_libpq_dsn)
        )
        await checkpointer.setup()
    except Exception as exc:
        await stack.aclose()
        _initialization_error = type(exc).__name__
        raise

    _checkpointer = checkpointer
    _exit_stack = stack
    _initialization_error = None


def get_checkpointer() -> Any:
    """返回已初始化的 checkpoint 实例。"""

    return _checkpointer


def get_checkpoint_error() -> str | None:
    """返回 checkpoint 初始化错误类型。"""

    return _initialization_error


async def close_checkpointer() -> None:
    """关闭 checkpoint 连接。"""

    global _checkpointer, _exit_stack
    if _exit_stack is not None:
        await _exit_stack.aclose()
    _checkpointer = None
    _exit_stack = None
