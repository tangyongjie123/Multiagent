# 当前实现状态

更新时间：2026-11-03

## 1. 重构结果

项目已从“从需求生成 Spring Boot 工程”重构为“多 Agent Git 仓库静态审查平台”。

已移除：

- 旧项目生成 API。
- Maven 工程生成与测试执行服务。
- 旧代码生成 Agent 角色。
- 旧前端代码生成控制台。
- 开发 Token、模型价格和计费文档。
- 旧的生成工程与故障排查文档。

已新增：

- 仓库提交、历史、重跑和取消 API。
- Git URL 白名单、浅克隆、大小与文件数限制。
- Repository、Architecture、Test、Security、Quality、Report 六个专业 Agent。
- 确定性安全与质量规则。
- 新的 PostgreSQL 数据表和 LangGraph 状态图。
- SSE 实时事件、结构化问题和 Markdown 报告。
- React 仓库审查控制台。
- 新的架构、分析模型和环境文档。

## 2. 已验证

| 项目 | 状态 |
| --- | --- |
| Ruff | 通过 |
| mypy | 通过 |
| pytest | 通过（9 项） |
| 前端 TypeScript + Vite 构建 | 通过 |
| 旧代码生成路由移除 | 已完成 |
| 新 GitHub 分支工作区 | 已完成 |
| 新 API 和前端页面 | 通过真实仓库验收 |

代码测试覆盖：

- Git URL 校验。
- 仓库扫描与 Spring Boot 识别。
- 静态安全与质量规则。
- 主 Agent 完成路径。
- 主 Agent 失败路径。
- FastAPI 存活检查。
- 模型配置回退。

## 3. 真实环境验收

使用 `https://github.com/spring-projects/spring-petclinic.git` 完成验收：

- `/health` 中 database、checkpoint、Milvus、Neo4j、LLM 和 Embedding 均为 `ok`。
- 浅克隆 Commit：`500158f732419217507c7656904b8e6aa1bcc0d6`。
- 扫描 132 个文件、21 个测试文件，识别 Java、YAML 和 XML。
- Repository、Architecture、Test、Security、Quality、Report 六个 Agent 全部完成。
- 分析状态最终为 `completed`，用时约 2 分 35 秒。
- 共生成 19 条问题：critical 2、major 2、minor 14、info 1。
- 事件、问题和 3 个产物写入 PostgreSQL。
- SSE 按序号返回真实事件。
- Markdown 报告可读取，内容包含文件位置、证据、影响和建议。
- 取消中的运行最终为 `cancelled`，没有被后续结果覆盖。
- 非白名单主机返回 HTTP 400。

## 4. 尚未完成

- Milvus 代码切块、Embedding、集合写入和相似检索未接入分析链路。
- Neo4j 自动 AST 解析和仓库建图未接入分析链路。
- 前端 Markdown 渲染、代码高亮和依赖图未实现。
- 当前使用 FastAPI 进程内后台任务，进程重启只能标记中断，不能自动续跑完整任务。
- 数据库未提交 Alembic 初始迁移；开发环境依赖 `AUTO_CREATE_TABLES=true`。
- 没有身份认证、多租户和私有仓库授权。
- 未执行目标仓库编译、测试或严格 SAST。

## 5. 已知数据兼容性

旧版 `projects`、`runs`、`agent_events` 和 `artifacts` 等表没有自动删除。新版本使用 `repositories`、`repository_analyses`、`analysis_events`、`analysis_findings` 和 `analysis_artifacts`。

在确认旧数据不再需要之前，不应执行不可恢复的表删除操作。

## 6. 当前结论

RepoGraph 的仓库静态审查主链路已经通过真实公开仓库验收，可以作为当前 MVP。Milvus 和 Neo4j 的深度业务接入、私有仓库和生产级任务队列仍属于后续阶段。
