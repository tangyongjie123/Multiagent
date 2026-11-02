"""验证 Neo4j 约束、代码节点关系和 Cypher 查询。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.graph.neo4j import (
    close_neo4j,
    get_neo4j_driver,
    initialize_neo4j,
)


async def main() -> None:
    await initialize_neo4j()
    driver = get_neo4j_driver()
    if driver is None:
        raise RuntimeError("Neo4j 未配置或初始化失败")

    project_id = f"verification-{uuid4()}"
    async with driver.session() as session:
        await session.run(
            """
            CREATE (p:Project {id: $project_id, name: 'Neo4j verification'})
            CREATE (f:File {
                project_id: $project_id,
                path: 'src/main/java/example/OrderService.java'
            })
            CREATE (c:Class {
                fqn: $project_id + ':example.OrderService'
            })
            CREATE (m:Method {
                fqn: $project_id + ':example.OrderService#create'
            })
            CREATE (t:Test {
                fqn: $project_id + ':example.OrderServiceTest#create'
            })
            CREATE (p)-[:CONTAINS]->(f)
            CREATE (f)-[:CONTAINS]->(c)
            CREATE (c)-[:CONTAINS]->(m)
            CREATE (t)-[:TESTS]->(m)
            """,
            project_id=project_id,
        )
        result = await session.run(
            """
            MATCH (p:Project {id: $project_id})
                  -[:CONTAINS]->(:File)-[:CONTAINS]->(:Class)
                  -[:CONTAINS]->(method:Method)
            MATCH (:Test)-[:TESTS]->(method)
            RETURN count(DISTINCT method) AS method_count
            """,
            project_id=project_id,
        )
        record = await result.single()
        print(f"project_id={project_id}")
        print(f"method_count={record['method_count'] if record else 0}")
        await session.run(
            "MATCH (n) WHERE n.id = $project_id "
            "OR n.fqn STARTS WITH $prefix "
            "OR n.project_id = $project_id DETACH DELETE n",
            project_id=project_id,
            prefix=f"{project_id}:",
        )

    await close_neo4j()


if __name__ == "__main__":
    asyncio.run(main())
