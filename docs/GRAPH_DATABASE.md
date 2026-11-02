# Neo4j 代码依赖图

更新时间：2026-11-02

## 连接信息

Neo4j 运行在 `basenode` 虚拟机，已确认：

- 主机名：`basenode`（`192.168.74.180`）
- Neo4j Browser：`http://basenode:7474`
- Bolt：`bolt://basenode:7687`
- HTTP 健康响应：200
- APOC：`apoc-5.26.8-core.jar`

本机 `.env` 配置：

```dotenv
NEO4J_URI=bolt://basenode:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace-with-local-secret
```

密码已填写在本机 `.env`，不会写入 Git。

## 代码图谱目标

节点：

- Project
- Module
- File
- Class
- Method
- Test

关系：

- `CONTAINS`
- `CALLS`
- `DEPENDS_ON`
- `TESTS`

## 应用初始化

应用启动时检测到 Neo4j 配置后，会：

1. 建立 Bolt 连接。
2. 验证连接。
3. 为 Project、File、Class、Method 和 Test 创建唯一约束。
4. 将驱动保存在进程级管理器中。

`/health` 会执行 `RETURN 1` 验证 Neo4j。密码未配置时显示 `not_configured`；连接或查询失败时显示 `error`，不输出密码。

## 当前验证结果

- Neo4j 用户名和密码认证成功。
- Project、File、Class、Method、Test 唯一约束已创建。
- 已写入 Project → File → Class → Method 和 Test → Method 的真实关系。
- Cypher 依赖路径查询返回 1 个 Method。
- 验证数据已在测试完成后清理。
