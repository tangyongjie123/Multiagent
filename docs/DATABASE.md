# PostgreSQL 数据设计

更新时间：2026-11-03

## 1. 职责

PostgreSQL 是平台的业务状态源，负责：

- 已提交仓库。
- 每次分析及运行状态。
- Agent 和系统事件。
- 结构化问题。
- 报告与中间产物元数据。
- LangGraph checkpoint。

Milvus 不保存事务型业务数据。报告正文、问题 JSON 和仓库快照保存在工作区，数据库只保存路径、哈希和元数据。

## 2. 连接方式

配置来自 `.env`：

```dotenv
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=multiagent
POSTGRES_USER=multiagent
POSTGRES_PASSWORD=replace-with-a-strong-password
AUTO_CREATE_TABLES=true
```

应用使用两种连接串：

- SQLAlchemy：`postgresql+asyncpg://`
- LangGraph checkpoint：`postgresql://`，由 psycopg 驱动

Windows 默认 Proactor 事件循环不兼容当前 psycopg 异步模式，因此应用入口会切换到 Selector 事件循环。推荐通过 `scripts.run_api` 或 `dev.py` 启动。

## 3. 表结构

### `repositories`

| 字段 | 说明 |
| --- | --- |
| `id` | UUID 主键 |
| `url` | 规范化后的公开 Git URL |
| `name` | 仓库名称 |
| `branch` | 默认分支，可空 |
| `provider` | `github.com`、`gitlab.com` 或 `gitee.com` |
| `latest_commit` | 最近一次成功扫描的 Commit |
| `created_at` / `updated_at` | 时间戳 |

### `repository_analyses`

| 字段 | 说明 |
| --- | --- |
| `id` | UUID 主键 |
| `repository_id` | 关联仓库 |
| `status` | 分析状态 |
| `current_agent` | 当前或最后执行的 Agent |
| `branch` / `commit_sha` | 本次分析分支和 Commit |
| `summary` / `error_message` | 结果摘要和失败原因 |
| `worker_id` | 当前执行 Worker |
| `finding_count` | 问题总数 |
| `input_tokens` / `output_tokens` | 模型用量 |
| `started_at` / `heartbeat_at` / `completed_at` | 执行时间 |
| `created_at` | 创建时间 |

### `analysis_events`

| 字段 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `analysis_id` | 所属分析 |
| `sequence` | 单个分析内单调递增序号 |
| `event_type` | 例如 `agent.started`、`analysis.completed` |
| `agent` | 事件来源 Agent |
| `message` | 中文可读信息 |
| `data` | JSONB 扩展数据 |
| `created_at` | 事件时间 |

`analysis_id + sequence` 有唯一约束，SSE 根据序号断点续传。

### `analysis_findings`

| 字段 | 说明 |
| --- | --- |
| `id` | UUID 主键 |
| `analysis_id` | 所属分析 |
| `category` | architecture、test、security、quality |
| `severity` | critical、major、minor、info |
| `title` | 问题标题 |
| `file_path` / `line` | 可选文件位置 |
| `evidence` | 可验证证据 |
| `impact` | 影响 |
| `recommendation` | 修复建议 |
| `created_at` | 创建时间 |

### `analysis_artifacts`

| 字段 | 说明 |
| --- | --- |
| `id` | UUID 主键 |
| `analysis_id` | 所属分析 |
| `kind` | `report`、`findings`、`repository` |
| `name` | 文件名 |
| `content_type` | MIME 类型 |
| `storage_path` | 工作区路径 |
| `sha256` | 文件内容哈希 |
| `created_at` | 创建时间 |

## 4. LangGraph checkpoint

`langgraph-checkpoint-postgres` 自动维护：

```text
checkpoint_blobs
checkpoint_migrations
checkpoint_writes
checkpoints
```

线程 ID 格式为 `analysis:{analysis_id}`，便于将一次运行与 checkpoint 关联。

## 5. 初始化与迁移

开发环境可以在应用启动时自动建表：

```dotenv
AUTO_CREATE_TABLES=true
```

生产环境应关闭自动建表并使用 Alembic。

旧版 `projects`、`runs`、`agent_events` 和 `artifacts` 已在 2026-11-03 备份到 PostgreSQL schema `repograph_backup_20261103` 后删除。该 schema 仅用于短期回滚，确认现有页面和报告正常后可手工删除。

本地 PostgreSQL 可通过 Compose 启动：

```powershell
docker compose up -d postgres
docker compose ps
docker compose logs --tail=50 postgres
```

## 6. 健康检查

`GET /health` 执行 `SELECT 1`，并检查 LangGraph checkpointer。数据库不可用时 API 返回 `503`，错误信息不会包含数据库密码。
