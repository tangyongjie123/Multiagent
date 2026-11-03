"""FastAPI 应用入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.checkpoint import close_checkpointer, initialize_checkpointer
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import (
    DatabaseUnavailableError,
    close_database,
    initialize_database,
)
from app.graph.neo4j import close_neo4j, initialize_neo4j
from app.mcp.server import create_mcp_http_app, mcp_server
from app.services.analysis_runner import recover_interrupted_analyses

mcp_http_app = create_mcp_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """初始化数据库、checkpoint、Neo4j 和 MCP 服务生命周期。"""

    settings = get_settings()
    configure_logging(settings.log_level)
    await initialize_database()
    with suppress(Exception):
        await recover_interrupted_analyses()
    with suppress(Exception):
        await initialize_checkpointer()
    with suppress(Exception):
        await initialize_neo4j()
    # MCP HTTP 应用与 FastAPI 共用进程；会话管理器必须覆盖整个应用生命周期。
    async with mcp_server.session_manager.run():
        yield
    await close_neo4j()
    await close_checkpointer()
    await close_database()


def create_app() -> FastAPI:
    """构建 FastAPI 应用。"""

    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    # 挂载后 Agent 通过 /mcp/ 使用 Streamable HTTP 调用只读工具。
    application.mount("/mcp", mcp_http_app)

    @application.exception_handler(DatabaseUnavailableError)
    async def database_unavailable_handler(
        _: Request,
        exc: DatabaseUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc)},
        )

    return application


app = create_app()
