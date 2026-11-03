"""存活与依赖服务健康检查。"""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx
from fastapi import APIRouter

from app.agents.checkpoint import get_checkpoint_error, get_checkpointer
from app.api.schemas import HealthComponent, HealthResponse
from app.core.config import get_settings
from app.db.session import check_database
from app.graph.neo4j import check_neo4j

router = APIRouter(tags=["health"])


def _check_milvus_sync() -> None:
    """Milvus SDK 为同步客户端，因此在工作线程中执行检查。"""

    from pymilvus import MilvusClient  # type: ignore[import-untyped]

    settings = get_settings()
    client = MilvusClient(
        uri=settings.milvus_uri or "",
        user=settings.milvus_user or "",
        password=(
            settings.milvus_password.get_secret_value()
            if settings.milvus_password is not None
            else ""
        ),
        timeout=3,
    )
    client.list_collections()


async def _database_component() -> HealthComponent:
    """检查 PostgreSQL 是否可用。"""

    settings = get_settings()
    if not settings.postgres_configured:
        return HealthComponent(status="not_configured", detail="POSTGRES_PASSWORD 未配置")
    try:
        healthy = await asyncio.wait_for(check_database(), timeout=3)
    except Exception as exc:
        return HealthComponent(status="error", detail=type(exc).__name__)
    return HealthComponent(status="ok" if healthy else "error")


async def _milvus_component() -> HealthComponent:
    """检查 Milvus 连接，不在这里创建集合或写入数据。"""

    settings = get_settings()
    if not settings.milvus_configured:
        return HealthComponent(status="not_configured")
    try:
        await asyncio.wait_for(asyncio.to_thread(_check_milvus_sync), timeout=5)
    except Exception as exc:
        return HealthComponent(status="error", detail=type(exc).__name__)
    return HealthComponent(status="ok")


async def _neo4j_component() -> HealthComponent:
    """检查 Neo4j Bolt 连接。"""

    settings = get_settings()
    if not settings.neo4j_configured or settings.neo4j_password is None:
        return HealthComponent(status="not_configured")
    try:
        healthy = await asyncio.wait_for(check_neo4j(), timeout=3)
    except Exception as exc:
        return HealthComponent(status="error", detail=type(exc).__name__)
    return HealthComponent(status="ok" if healthy else "error")


async def _http_auth_component(
    *,
    api_key: str | None,
    url: str | None,
) -> HealthComponent:
    """通过只读模型接口检查 API Key 是否有效。"""

    if not api_key or not url:
        return HealthComponent(status="not_configured")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.is_success:
            return HealthComponent(status="ok")
        return HealthComponent(status="error", detail=f"HTTP {response.status_code}")
    except httpx.HTTPError as exc:
        return HealthComponent(status="error", detail=type(exc).__name__)


def _checkpoint_component() -> HealthComponent:
    """确认 LangGraph checkpointer 已初始化。"""

    settings = get_settings()
    if not settings.postgres_configured:
        return HealthComponent(status="not_configured")
    if get_checkpointer() is not None:
        return HealthComponent(status="ok")
    return HealthComponent(
        status="error",
        detail=get_checkpoint_error() or "checkpointer_not_initialized",
    )


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """仅表示 FastAPI 进程存活。"""

    return {"status": "ok"}


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """检查应用与核心依赖服务。"""

    settings = get_settings()
    chat_base_url = settings.effective_chat_base_url
    if settings.chat_provider == "deepseek" and chat_base_url:
        chat_probe_url = f"{chat_base_url.rstrip('/')}/user/balance"
    elif chat_base_url:
        chat_probe_url = f"{chat_base_url.rstrip('/')}/models"
    else:
        chat_probe_url = None
    embedding_base_url = settings.effective_embedding_base_url
    embedding_probe_url = (
        f"{embedding_base_url.rstrip('/')}/models" if embedding_base_url else None
    )
    component_results: tuple[HealthComponent, ...] = await asyncio.gather(
        _database_component(),
        _milvus_component(),
        _neo4j_component(),
    )
    components: dict[str, HealthComponent] = {
        "database": component_results[0],
        "checkpoint": _checkpoint_component(),
        "milvus": component_results[1],
        "neo4j": component_results[2],
        "llm": await _http_auth_component(
            api_key=(
                settings.effective_chat_api_key.get_secret_value()
                if settings.effective_chat_api_key is not None
                else None
            ),
            url=chat_probe_url,
        ),
        "embedding": await _http_auth_component(
            api_key=(
                settings.effective_embedding_api_key.get_secret_value()
                if settings.effective_embedding_api_key is not None
                else None
            ),
            url=embedding_probe_url,
        ),
    }
    overall: Literal["ok", "degraded"] = (
        "ok"
        if all(component.status == "ok" for component in components.values())
        else "degraded"
    )
    return HealthResponse(
        status=overall,
        version=settings.app_version,
        components=components,
    )
