# PostgreSQL 数据库设计

更新时间：2026-11-02

## 使用范围

PostgreSQL 是平台的唯一关系型数据库，负责：

- 项目和需求。
- Agent 运行状态。
- 任务和 Agent 事件。
- 代码、测试、评审及文档产物元数据。
- LangGraph checkpoint。
- Token 与费用统计。

MySQL 不再作为项目依赖。

## 连接配置

真实配置写入 `.env`：

```dotenv
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=replace-with-a-strong-password
AUTO_CREATE_TABLES=true
```

应用使用 `postgresql+asyncpg://` 连接数据库。LangGraph 的 PostgreSQL checkpoint 使用 `postgresql://` 与 psycopg。

## 本地容器启动

项目的 `compose.yaml` 会在 `5432` 端口启动 PostgreSQL 16：

```powershell
docker compose up -d postgres
docker compose ps
docker compose logs --tail=50 postgres
```

当前实际 PostgreSQL 服务地址为 `192.168.74.180:5432`，本机 `127.0.0.1:5432` 未监听。该服务要求 `postgres` 用户提供密码。

实际本地 `.env` 应使用：

```dotenv
POSTGRES_HOST=192.168.74.180
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
```

密码只填写在本机 `.env` 的 `POSTGRES_PASSWORD` 中。验证连接后应创建项目专用的 `multiagent` 数据库和最小权限用户，避免应用长期使用 PostgreSQL 超级用户。

开发阶段当前使用用户提供的 `postgres` 用户和 `postgres` 数据库。已验证连接成功，PostgreSQL 版本为 16.15。

## 初始化

开发模式设置 `AUTO_CREATE_TABLES=true` 时，FastAPI 启动会创建当前模型对应的表。

生产模式必须设置 `AUTO_CREATE_TABLES=false`，并使用 Alembic 迁移。Alembic 初始迁移将在 PostgreSQL 实际可连接后生成并验证。

当前已在 PostgreSQL 的 `public` schema 中创建：

```text
agent_events
artifacts
projects
runs
```

## 初始数据表

| 表 | 用途 |
| --- | --- |
| `projects` | 项目名称、原始需求和时间信息 |
| `runs` | 一次 Agent 运行、状态、Token 和费用 |
| `agent_events` | 可持久化、可回放的 Agent 与工具事件 |
| `artifacts` | 需求、设计、代码、测试和文档产物元数据 |

LangGraph 自动创建并管理以下 checkpoint 表：

```text
checkpoint_blobs
checkpoint_migrations
checkpoint_writes
checkpoints
```

Windows 环境需要 `WindowsSelectorEventLoopPolicy`，因为 psycopg 异步连接不支持默认的 `ProactorEventLoop`。应用入口已自动配置。

## 健康检查

`GET /health` 会执行 `SELECT 1` 检查数据库。未配置密码或无法连接时返回 `degraded`，不会在错误信息中暴露连接密码。

当前实测 `/health` 中数据库状态为 `ok`。
