# 项目实现进度

更新时间：2026-11-02

## 已完成

### 工程与基础设施

- 建立 Python 3.11 Conda 开发环境。
- 记录生产、开发和完整锁定依赖。
- 建立 Git 仓库、`.gitignore`、`.gitattributes` 和 GitHub 远程仓库。
- 配置 `.env.example` 与本地 `.env` 分离。
- 增加开发 Token 与费用统计工具。

### FastAPI 后端

- 建立应用工厂、生命周期、CORS 和统一数据库异常响应。
- 增加 `/health/live` 存活检查和 `/health` 依赖健康检查。
- 增加项目创建、项目列表和项目详情接口。
- 增加运行记录创建、运行状态、事件列表、SSE 事件流和产物列表接口。
- 建立 PostgreSQL 异步 engine、session 和连接池管理。
- 建立项目、运行、Agent 事件和产物 ORM 模型。

### 主 Agent 与 LangGraph

- 建立唯一主 Agent 调度节点。
- 主 Agent 依次调度 PM、Architect、Coder、Tester、Reviewer 和 Doc。
- 所有专业 Agent 完成后必须返回主 Agent。
- 子 Agent 失败后主 Agent 记录失败决策并终止。
- 主 Agent 决策保存在工作流状态中，便于后续写入数据库和前端展示。
- 已实现 Tester/Reviewer 失败后的 Coder 修复循环，最大修复次数为 3。
- PM、Architect、Coder、Reviewer 和 Doc 已接入真实对话模型；Tester 根据 REST 契约生成并执行 JUnit 测试。

### 运行集成验证

- FastAPI 已通过 Uvicorn 实际启动，`/health/live` 返回 HTTP 200。
- `/health` 实测 PostgreSQL、checkpoint、Milvus、Neo4j、Chat 和 Embedding 全部为 `ok`。
- PostgreSQL 认证成功，应用已创建 `projects`、`runs`、`agent_events`、`artifacts` 四张表。
- 通过真实 HTTP 请求创建项目和运行记录，并成功读取持久化事件。
- SSE 接口已返回 `run.created` 事件。
- LangGraph checkpoint 已自动创建 PostgreSQL 表，并实际保存六 Agent 测试工作流状态。
- 增加 Windows 兼容启动器 `scripts/run_api.py`，修复 Uvicorn 默认 Proactor 事件循环导致的 checkpoint 初始化失败。
- 增加根目录 `main.py` 快捷入口，激活环境后可直接执行 `python main.py`。
- 使用兼容启动器后，`/health` 中 PostgreSQL 和 checkpoint 均为 `ok`。
- 完成端到端运行 `c693c7d0-765f-44f3-80f5-36f593a1e042`，六个 Agent 全部完成。
- 生成工程通过真实 `mvn -B test`，4 个 JUnit 测试全部通过。
- 生成服务通过真实 HTTP CRUD 验收，并生成 README、中文使用手册和 OpenAPI。
- 增加生成工程文件树、单文件读取、Diff 和 ZIP 下载接口。
- 增加 React + TypeScript 可视化控制台，支持项目创建、运行历史、SSE 时间线、文件浏览、Diff 和下载。
- 前端实时显示整体运行耗时和每条事件的相对时间。
- 前端支持停止运行；后端取消任务时会终止当前模型请求或 Maven 进程树。
- 已完成真实取消验证：运行在 PM 阶段被取消，最终状态为 `cancelled`，未继续产生 Agent 完成事件。
- 增加 `python dev.py` 一键启动前后端开发服务器。
- Coder 改为领域层与 Web 层两阶段生成，支持动态包名。
- Tester 升级为完整 CRUD、400、404、409 契约测试。
- 运行增加 Worker ID 和心跳，防止多个后端实例误将活跃运行标记为中断。

### 外部服务

- Milvus 连接验证成功，当前可访问 4 个集合。
- DashScope 兼容 Embedding 接口验证成功：
  - 模型：`qwen3.7-text-embedding`
  - 维度：1024
- DashScope 兼容 Chat 接口验证成功，模型：`qwen3.8-flash`。
- DeepSeek 新 Key 已确认与旧 Key 不同、格式正确，但 `/user/balance` 和 `/chat/completions` 均返回 HTTP 401，因此当前使用 DashScope 对话模型。
- Neo4j Browser 7474 和 Bolt 7687 已验证可达，APOC 5.26.8 已安装。
- Neo4j 已通过认证，代码图谱唯一约束和真实节点/关系读写验证成功。

## 模型 API 需求结论

- DeepSeek Chat API：当前 Key 不可用，但已切换到 DashScope 对话模型。
- Chat 与 Embedding：DashScope 当前 Key 均已验证可用，不需要额外申请 API。
- Reranker API：可选，不影响当前阶段。
- PostgreSQL、Milvus 和 Neo4j 是数据服务，不需要大模型 API Key。

## 验证结果

```text
Ruff: All checks passed
mypy: Success: no issues found in 37 source files
pytest: 9 passed
checkpoint verification: checkpoint_created=True, completed_agents=6
generated project: 4 JUnit tests passed
frontend production build: success
```

## 尚未完成

- Spring Boot 代码生成沙箱尚未实现。
- 生成工程尚未包含 Maven Wrapper。
- Tester 当前采用契约级集成测试，尚未覆盖每个 Service 分支。
- 前端尚未实现预算确认和人工审批按钮。
- 前端尚未可视化 Milvus 检索结果和 Neo4j 依赖图。

## 当前需要外部配置

PostgreSQL 运行在 `192.168.74.180:5432`，本机 `localhost:5432` 未监听。开发连接和建表已经完成。

完成方式：

1. 创建项目专用的数据库和最小权限用户。
2. 如坚持使用 DeepSeek 官方 API，需要确认 Key 状态；当前 DashScope 通道可正常完成六 Agent。

## 下一阶段

1. 增加 Alembic 初始迁移。
2. 将生成执行迁移到 Docker 沙箱并生成 Maven Wrapper。
3. 初始化 Milvus 的 `code_chunks` 与 `knowledge_chunks` 集合。
4. 将 React 构建产物纳入部署流程。
5. 增加预算确认和人工审批交互。
