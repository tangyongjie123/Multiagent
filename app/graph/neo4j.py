"""Neo4j 驱动生命周期、约束初始化与健康检查。"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

_driver: Any = None


async def initialize_neo4j() -> None:
    """连接 Neo4j 并创建代码图谱基础约束。"""

    global _driver
    settings = get_settings()
    if (
        not settings.neo4j_configured
        or settings.neo4j_uri is None
        or settings.neo4j_password is None
    ):
        return

    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        notifications_min_severity="WARNING",
    )
    await driver.verify_connectivity()
    constraints = (
        "CREATE CONSTRAINT project_id IF NOT EXISTS "
        "FOR (p:Project) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT file_key IF NOT EXISTS "
        "FOR (f:File) REQUIRE (f.project_id, f.path) IS UNIQUE",
        "CREATE CONSTRAINT class_fqn IF NOT EXISTS "
        "FOR (c:Class) REQUIRE c.fqn IS UNIQUE",
        "CREATE CONSTRAINT method_fqn IF NOT EXISTS "
        "FOR (m:Method) REQUIRE m.fqn IS UNIQUE",
        "CREATE CONSTRAINT test_fqn IF NOT EXISTS "
        "FOR (t:Test) REQUIRE t.fqn IS UNIQUE",
    )
    async with driver.session() as session:
        for statement in constraints:
            await session.run(statement)
    _driver = driver


async def check_neo4j() -> bool:
    """执行 Cypher 验证 Neo4j 连接。"""

    if _driver is None:
        return False
    async with _driver.session() as session:
        result = await session.run("RETURN 1 AS ok")
        record = await result.single()
        return bool(record and record["ok"] == 1)


def get_neo4j_driver() -> Any:
    """返回当前 Neo4j 驱动。"""

    return _driver


async def close_neo4j() -> None:
    """关闭 Neo4j 驱动。"""

    global _driver
    if _driver is not None:
        await _driver.close()
    _driver = None
