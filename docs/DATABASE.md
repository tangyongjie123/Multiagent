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

## 2. 表职责总览

| 表 | 主要负责 | 不负责 | 主要关联 |
| --- | --- | --- | --- |
| `repositories` | 保存去重后的仓库身份、URL、提供方和最新 Commit | 分析状态、问题和报告内容 | 一对多关联分析、聊天会话 |
| `repository_analyses` | 保存一次分析运行的状态、分支、Commit、耗时和模型用量 | 事件明细、问题明细 | 关联仓库；被事件、问题和产物引用 |
| `analysis_events` | 保存可回放的 Agent、工具和系统事件顺序 | 当前状态和最终结论 | 多对一关联分析 |
| `analysis_findings` | 保存可定位、可分类和可排序的审查问题 | 完整源码、模型隐藏推理 | 多对一关联分析 |
| `analysis_artifacts` | 保存报告、图表和中间文件的元数据、路径与哈希 | 文件正文 | 多对一关联分析；正文位于工作区 |
| `chat_sessions` | 保存聊天会话及其仓库/分析关联 | 具体消息内容 | 关联仓库和可选分析；一对多关联消息 |
| `chat_messages` | 保存用户和未来助手消息、模型和 Token 用量 | 引用证据和 Agent 事件 | 多对一关联聊天会话 |
| `checkpoints` | 保存 LangGraph 线程的 checkpoint 主记录 | 业务问题和报告 | 被 writes/blobs 引用 |
| `checkpoint_writes` | 保存图节点执行产生的待处理写入 | 最终业务数据 | 关联 `checkpoints` |
| `checkpoint_blobs` | 保存序列化后的 channel 大对象 | 对外 API 响应 | 关联 checkpoint 线程和 channel |
| `checkpoint_migrations` | 记录 LangGraph checkpoint 表迁移版本 | 业务数据 | 无 |

## 3. 连接方式

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

## 4. 表结构

### `repositories`

负责保存仓库的唯一身份和基础元数据。一个仓库可以拥有多次分析，但仓库 URL 应经过去重；分析和问题不直接重复存储在该表中。

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

负责记录“一次运行”及其生命周期。当前 Agent、错误摘要和 Token 总量属于该表；具体事件顺序和问题明细分别写入事件表与问题表。

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

负责保存运行过程的可观测时间线，包括 Agent、MCP 工具和系统事件。它用于前端回放和审计，但不能代替分析当前状态；当前状态以 `repository_analyses.status` 为准。

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

负责保存最终可操作的问题。每条记录应能定位文件或说明项目级证据；原始文件内容和完整模型对话不写入该表。

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

负责保存报告和图表文件的元数据。报告正文、SVG、JSON 快照实际位于分析工作区，表中只保存类型、路径、Content-Type 和 SHA-256 校验值。

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

### `chat_sessions`

负责保存一次持续对话的上下文边界，并关联仓库和可选的分析结果。该表不保存消息正文；消息写入 `chat_messages`。

| 字段 | 说明 |
| --- | --- |
| `id` | UUID 主键 |
| `repository_id` | 关联仓库；仓库删除时级联删除会话 |
| `analysis_id` | 可选关联某次分析；分析删除时置空 |
| `title` | 会话标题 |
| `status` | `active` 或 `archived` |
| `created_at` / `updated_at` | 会话时间 |
| `last_message_at` | 最近一条消息时间 |

### `chat_messages`

负责保存会话中的用户消息和未来的助手消息。引用证据、文件位置和 Finding 关联将在后续 `chat_citations` 表中保存，当前阶段尚未创建该表。

| 字段 | 说明 |
| --- | --- |
| `id` | UUID 主键 |
| `session_id` | 所属聊天会话 |
| `role` | `user` 或未来的 `assistant` |
| `content` | 消息正文 |
| `status` | `recorded`、`generating`、`completed` 或 `failed` |
| `model_name` | 生成助手消息时使用的模型 |
| `input_tokens` / `output_tokens` | 单条模型响应用量 |
| `created_at` | 创建时间 |

当前阶段只实现用户消息持久化。`assistant` 生成、引用表和 SSE 聊天事件将在下一阶段接入主 Agent 后启用。

## 5. LangGraph checkpoint

`langgraph-checkpoint-postgres` 自动维护：

```text
checkpoint_blobs
checkpoint_migrations
checkpoint_writes
checkpoints
```

线程 ID 格式为 `analysis:{analysis_id}`，便于将一次运行与 checkpoint 关联。

各 checkpoint 表职责：

| 表 | 职责 |
| --- | --- |
| `checkpoints` | 保存每个线程、命名空间和 checkpoint ID 的图状态快照与元数据 |
| `checkpoint_writes` | 保存节点运行产生的 channel 写入、任务 ID 和写入顺序 |
| `checkpoint_blobs` | 保存较大的序列化 channel 值，供 checkpoint 恢复 |
| `checkpoint_migrations` | 记录 LangGraph checkpoint schema 的迁移版本，不删除 |

这些表由 LangGraph 管理，不应手工修改业务内容。清理任务必须同时维护 `checkpoints`、`checkpoint_writes` 和 `checkpoint_blobs`。

## 6. 初始化与迁移

开发环境可以在应用启动时自动建表：

```dotenv
AUTO_CREATE_TABLES=true
```

生产环境应关闭自动建表并使用 Alembic。

旧版 `projects`、`runs`、`agent_events` 和 `artifacts` 已在 2026-11-03 备份到 PostgreSQL schema `repograph_backup_20261103` 后删除。该 schema 仅用于短期回滚，确认现有页面和报告正常后可手工删除。

事件时间修复前还将相关业务表备份到 `repograph_time_fix_20261103`。确认时间线正常后可删除该回滚 schema。

本地 PostgreSQL 可通过 Compose 启动：

```powershell
docker compose up -d postgres
docker compose ps
docker compose logs --tail=50 postgres
```

## 7. 健康检查

`GET /health` 执行 `SELECT 1`，并检查 LangGraph checkpointer。数据库不可用时 API 返回 `503`，错误信息不会包含数据库密码。
