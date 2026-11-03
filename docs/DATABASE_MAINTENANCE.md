# PostgreSQL 数据维护记录

更新时间：2026-11-03

## 1. 本次清理目标

- 合并重复仓库记录。
- 删除失败和取消的分析运行。
- 保留全部成功分析及其报告、问题、事件和 checkpoint。
- 删除旧代码生成版本遗留的业务表。
- 清理失去关联对象或属于旧工作流的 LangGraph checkpoint。

## 2. 安全备份

清理前将相关数据复制到：

```text
repograph_backup_20261103
```

该 schema 包含 12 张备份表：

```text
repositories
repository_analyses
analysis_events
analysis_findings
analysis_artifacts
legacy_projects
legacy_runs
legacy_agent_events
legacy_artifacts
checkpoints
checkpoint_writes
checkpoint_blobs
```

只有确认页面、报告和历史查询都正常后，才由维护者手工删除备份 schema：

```sql
DROP SCHEMA repograph_backup_20261103 CASCADE;
```

该命令不可恢复，不应在验收前执行。

## 3. 清理内容

- 将重复 `vue2-manage` 仓库下的成功分析归并到唯一仓库记录。
- 删除 16 次 `failed` 或 `cancelled` 分析。
- 关联事件、问题、产物通过外键级联删除。
- 删除旧项目遗留表：
  - `projects`
  - `runs`
  - `agent_events`
  - `artifacts`
- 删除旧工作流和非成功分析的 checkpoint。
- 保留 `checkpoint_migrations`，不破坏 LangGraph schema 版本记录。

## 4. 清理后状态

| 表 | 行数 |
| --- | ---: |
| `repositories` | 4 |
| `repository_analyses` | 7 |
| `analysis_events` | 204 |
| `analysis_findings` | 143 |
| `analysis_artifacts` | 36 |
| `checkpoints` | 105 |
| `checkpoint_writes` | 1253 |
| `checkpoint_blobs` | 301 |

当前公开 schema 仅保留 RepoGraph 使用的 9 张表：

```text
repositories
repository_analyses
analysis_events
analysis_findings
analysis_artifacts
checkpoints
checkpoint_writes
checkpoint_blobs
checkpoint_migrations
```

## 5. 当前仓库数据

| 仓库 | 成功分析数 |
| --- | ---: |
| `bailicangdu/vue2-manage` | 3 |
| `FantasticLBP/Hotels_Server` | 1 |
| `FreeeBird/hotel` | 1 |
| `spring-projects/spring-petclinic` | 2 |

所有保留下来的分析状态均为 `completed`。

## 6. 后续维护原则

- 每次批量删除前必须先创建带日期的备份 schema。
- 不删除成功分析，除非用户明确要求清理历史。
- 合并仓库前先将分析记录重新关联到唯一仓库 ID。
- 失败分析可以在诊断完成后清理，但不能删除仍用于排查的事件日志。
- 清理 checkpoint 时必须同步维护 `checkpoints`、`checkpoint_writes` 和 `checkpoint_blobs`。
