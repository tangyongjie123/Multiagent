# 项目文件与代码说明

- 更新时间：2026-11-02
- 适用范围：当前仓库中的平台源码、配置、测试、脚本和项目文档
- 维护原则：以仓库中的实际代码为准；需求目标与当前实现不一致时，应分别说明

## 1. 文档用途

本文档用于回答三个问题：

1. 仓库中的每个文件或目录负责什么。
2. 修改一个功能时通常需要同时查看哪些文件。
3. 哪些内容是应纳入版本控制的源码，哪些是本地配置、缓存或运行产物。

`docs/PROJECT_REQUIREMENTS.md` 描述“项目最终要做什么”，本文档描述“当前仓库中的每个部分实际做什么”。当实现进度发生变化时，应同时检查 `docs/IMPLEMENTATION_STATUS.md`；当具体接口、数据库或环境变量发生变化时，应更新对应专题文档，并同步修改本文档中的职责说明。

## 2. 系统全貌

平台由 React 控制台、FastAPI 后端、LangGraph Agent 工作流、PostgreSQL、Milvus、Neo4j 和隔离的 Spring Boot 生成工作区组成。

```text
React 控制台
    │ REST / SSE
    ▼
FastAPI API
    ├── PostgreSQL：项目、运行、事件、产物元数据、LangGraph checkpoint
    ├── Neo4j：代码图谱连接与基础约束（当前尚未接入正式运行链路）
    ├── Milvus：健康检查和后续代码/文档检索（当前尚未接入正式运行链路）
    └── 后台运行执行器
            │
            ▼
        LangGraph 主 Agent
            │ 按顺序派发并验收
            ▼
PM → Architect → Coder → Tester → Reviewer → Doc
                                      │
                                      └── 失败时返回 Coder 修复
            │
            ▼
workspaces/<run-id>/ 隔离工作区
    ├── Agent 结构化产物
    ├── Spring Boot 模板与生成代码
    ├── Maven 测试日志
    └── README、使用手册和 OpenAPI
```

当前工作流中的 Tester 会真实执行 `mvn -B test`，测试或评审失败会把任务送回 Coder。Milvus 和 Neo4j 已有配置、健康检查及独立验证能力，但向量检索和代码图谱自动写入尚未接入正式 Agent 运行链路。

## 3. 根目录文件

| 文件 | 类型 | 作用 | 修改时机 |
| --- | --- | --- | --- |
| `AGENTS.md` | 开发约束 | 记录项目定位、主 Agent 约束、MVP 范围、技术栈、持久化边界、密钥规则、依赖和 Token 记录要求。 | 项目规则或开发流程变化时 |
| `README.md` | 项目入口文档 | 介绍项目状态、目标能力、技术栈、启动方式、文档索引和安全说明。 | 启动方式、功能状态或文档索引变化时 |
| `.env.example` | 配置模板 | 列出应用、模型、Embedding、PostgreSQL、Milvus、Neo4j、预算和重试相关环境变量，只包含占位符。 | 新增或删除环境变量时 |
| `.env` | 本地私密配置 | 当前开发机的真实外部服务和数据库配置。被 `.gitignore` 排除，不属于可提交源码。 | 仅在本机切换服务或凭证时 |
| `.gitignore` | Git 配置 | 排除虚拟环境、密钥、缓存、IDE 配置、生成目录、日志和 `workspaces/` 运行产物。 | 新增本地或生成文件类型时 |
| `.gitattributes` | Git 配置 | 统一文本文件为 LF，PowerShell、批处理和命令文件使用 CRLF。 | 跨平台换行规则变化时 |
| `.python-version` | Python 配置 | 固定 Python 版本为 3.11.18，与项目 Conda 环境一致。 | 升级 Python 时 |
| `pyproject.toml` | Python 工具配置 | 配置 pytest 测试路径与异步模式、Ruff 规则和 mypy 类型检查范围。 | 测试或静态检查规则变化时 |
| `requirements.txt` | 生产依赖清单 | 固定 FastAPI、LangGraph、数据库客户端、Web 服务和运行时支撑库的直接版本。 | 新增生产依赖时 |
| `requirements-dev.txt` | 开发依赖清单 | 固定 pytest、覆盖率、Ruff、mypy 和 pre-commit 等开发工具。 | 新增测试或质量工具时 |
| `requirements-lock.txt` | 完整环境快照 | 记录共享 Conda 环境当前全部直接和间接依赖，不是最小安装清单。 | 重建或冻结环境时 |
| `compose.yaml` | Docker Compose | 启动 PostgreSQL 16，并配置健康检查、端口和持久化卷。 | PostgreSQL 容器配置变化时 |
| `main.py` | 后端快捷入口 | 调用 `scripts.run_api.main()`，供激活环境后直接执行 `python main.py`。 | 后端启动流程变化时 |
| `dev.py` | 本地开发启动器 | 同时启动 FastAPI 和 Vite 开发服务器，并在退出时终止两个子进程。 | 前后端联合启动方式变化时 |

## 4. 后端源码

后端位于 `app/`，按 Agent、API、核心配置、数据库、领域模型、图数据库和服务分层。

### 4.1 包入口

| 文件 | 作用 |
| --- | --- |
| `app/__init__.py` | 后端包入口；在 Windows 上把事件循环策略切换为 `WindowsSelectorEventLoopPolicy`，避免 psycopg 异步连接不兼容默认的 Proactor 事件循环。 |
| `app/main.py` | FastAPI 应用工厂和生命周期入口。启动时配置日志、初始化 PostgreSQL、恢复中断运行、初始化 PostgreSQL checkpoint 和 Neo4j；关闭时释放 Neo4j、checkpoint 和数据库连接。还配置 CORS，并把数据库不可用异常转换为 HTTP 503。 |
| `app/agents/__init__.py` | 标识 Agent 包，当前无业务逻辑。 |
| `app/api/__init__.py` | 标识 API 包，当前无业务逻辑。 |
| `app/api/routes/__init__.py` | 标识路由包，当前无业务逻辑。 |
| `app/core/__init__.py` | 标识核心配置包，当前无业务逻辑。 |
| `app/db/__init__.py` | 标识数据库包，当前无业务逻辑。 |
| `app/domain/__init__.py` | 标识领域模型包，当前无业务逻辑。 |
| `app/graph/__init__.py` | 标识图数据库包，当前无业务逻辑。 |
| `app/services/__init__.py` | 标识服务包，当前无业务逻辑。 |

### 4.2 Agent 编排

| 文件 | 主要职责 | 关键内容与协作 |
| --- | --- | --- |
| `app/agents/schemas.py` | 定义六个专业 Agent 的结构化交接协议。 | 包含 `RequirementSpec`、`ArchitectureSpec`、`CodeBundle`、`TestBundle`、`ReviewReport` 和 `DocumentationBundle`；严格拒绝未知字段，限制生成文件名、内容长度和接口方法。 |
| `app/agents/llm.py` | 创建 OpenAI 兼容的 LangChain 对话模型客户端。 | 根据 `CHAT_PROVIDER` 选择 DeepSeek 或 DashScope 的有效密钥、Base URL 和模型；未配置时抛出 `LLMNotConfiguredError`。 |
| `app/agents/supervisor.py` | 构建主 Agent 集中调度的 LangGraph 状态图。 | 定义工作流状态、固定专业 Agent 顺序、下一个 Agent 选择、失败路由、Token 预算检查和最大修复次数。所有专业 Agent 节点完成后都返回 `main_agent`，由主 Agent 决定继续、返工、失败或结束。 |
| `app/agents/specialists.py` | 使用真实模型执行 PM、Architect、Coder、Tester、Reviewer 和 Doc。 | PM 输出需求规格；Architect 输出架构；Coder 分领域层和 Web 层两阶段生成代码；Tester 根据接口契约生成 JUnit HTTP 测试并调用 Maven；Reviewer 读取源码、测试和结果决定是否通过；Doc 生成 README、使用手册和 OpenAPI。执行过程通过事件回调写入运行事件。 |
| `app/agents/checkpoint.py` | 管理 LangGraph PostgreSQL checkpoint。 | 使用 `AsyncPostgresSaver` 建立异步连接、初始化 checkpoint 表、提供全局实例和初始化错误，并在应用退出时关闭连接。 |

`specialists.py` 中的 `_invoke()` 会把 Pydantic Schema 写入系统提示词，要求模型仅返回 JSON，再通过 `model_validate_json()` 校验。Tester 的契约测试由代码确定性生成，不调用模型，因此 Tester 自身 Token 记为 0。

### 4.3 HTTP API

| 文件 | 主要职责 | 关键内容与协作 |
| --- | --- | --- |
| `app/api/router.py` | 汇总并挂载健康、项目和运行路由。 | `app/main.py` 只引用这个聚合路由。 |
| `app/api/schemas.py` | 定义 HTTP 请求和响应的 Pydantic 模型。 | 包含项目、运行、事件、产物、文件列表、Diff 和健康检查响应；统一约束长度、时间和类型。 |
| `app/api/routes/health.py` | 提供 `/health/live` 和 `/health`。 | 检查 PostgreSQL、checkpoint、Milvus、Neo4j、Chat 和 Embedding；任一已配置依赖失败时整体状态为 `degraded`。DeepSeek 使用 `/user/balance` 验证凭证，DashScope 使用 `/models`。 |
| `app/api/routes/projects.py` | 管理项目和需求。 | 提供创建、列表和详情接口；项目创建时保存名称与原始需求。 |
| `app/api/routes/runs.py` | 管理 Agent 运行和交付物。 | 创建运行并通过后台任务启动、查询运行、列出运行历史、读取事件、SSE 推送、列出产物、浏览生成文件、读取文件内容、生成 Diff 和下载 ZIP。文件访问通过 `artifacts.py` 做路径安全校验。 |

主要接口分组：

| 接口 | 作用 |
| --- | --- |
| `POST /api/v1/projects` | 创建项目并提交需求 |
| `GET /api/v1/projects` | 查询项目列表 |
| `GET /api/v1/projects/{project_id}` | 查询项目详情 |
| `POST /api/v1/projects/{project_id}/runs` | 启动一次运行 |
| `GET /api/v1/projects/{project_id}/runs` | 查询项目运行历史 |
| `GET /api/v1/runs/{run_id}` | 查询运行状态和 Token 数据 |
| `GET /api/v1/runs/{run_id}/events` | 查询已经持久化的事件 |
| `GET /api/v1/runs/{run_id}/events/stream` | 通过 SSE 推送新增事件 |
| `GET /api/v1/runs/{run_id}/artifacts` | 查询 Agent 产物元数据 |
| `GET /api/v1/runs/{run_id}/files` | 查询生成工程文件树 |
| `GET /api/v1/runs/{run_id}/files/content?path=...` | 查看单个文本文件 |
| `GET /api/v1/runs/{run_id}/diff` | 查看相对空目录的初始 Diff |
| `GET /api/v1/runs/{run_id}/download` | 下载完整生成工程 ZIP |
| `GET /health/live` | 只检查 FastAPI 进程 |
| `GET /health` | 检查配置中的外部依赖 |

### 4.4 配置与日志

| 文件 | 作用 |
| --- | --- |
| `app/core/config.py` | 从 `.env` 和环境变量读取全部配置。定义应用、模型、Embedding、Reranker、PostgreSQL、Milvus、Neo4j、预算和修复次数；提供 DeepSeek/DashScope 回退、SecretStr 安全读取、异步和 checkpoint DSN 构造、服务配置状态判断。 |
| `app/core/logging.py` | 配置 Python 标准日志和 structlog，输出带时间、级别上下文的 JSON 日志。 |

`get_settings()` 使用 `lru_cache` 返回进程级配置单例。测试若修改环境变量，应清理该缓存或直接构造新的 `Settings`。

### 4.5 数据持久化与领域模型

| 文件 | 作用 |
| --- | --- |
| `app/db/base.py` | SQLAlchemy 声明式基类，统一索引、唯一约束、外键和主键的命名规则。 |
| `app/db/models.py` | 定义 PostgreSQL ORM 表：`projects`、`runs`、`agent_events`、`artifacts`。运行表保存状态、当前 Agent、Token、预算、费用和错误；产物表保存类型、名称、存储路径和校验值。 |
| `app/db/session.py` | 创建 asyncpg engine 和异步 session 工厂，提供 FastAPI 请求级 session、开发阶段自动建表、`SELECT 1` 健康检查和连接池释放。 |
| `app/domain/models.py` | 定义与 Web 框架无关的领域枚举和结果模型：Agent 角色、运行状态、Agent 结构化结果、事件和工作流结果。 |

PostgreSQL 同时保存业务状态和 LangGraph checkpoint。Milvus 应只保存向量及检索数据，不应保存项目、运行等事务数据。

### 4.6 图数据库

| 文件 | 作用 |
| --- | --- |
| `app/graph/neo4j.py` | 创建和关闭 Neo4j 异步驱动，验证连接，初始化 Project、File、Class、Method、Test 唯一约束，并提供连接健康检查。 |

当前正式运行链路只初始化约束和检查连接，尚未把生成的 Java 文件、类、方法和测试自动写入 Neo4j；`scripts/verify_neo4j.py` 用于验证真实节点和关系读写。

### 4.7 运行、工作区和产物服务

| 文件 | 作用 | 关键依赖 |
| --- | --- | --- |
| `app/services/run_executor.py` | 执行一次完整运行。启动时恢复上次中断的 `running` 记录；加载项目和配置；创建隔离工作区；构建 LangGraph；累计 Token；保存每个 Agent 结果和主 Agent 决策；更新运行最终状态并写入事件。 | `WorkspaceManager`、`build_supervisor_graph`、`LLMSpecialistExecutor`、数据库 session、checkpoint |
| `app/services/run_events.py` | 按运行内递增序号追加 Agent 事件。 | `AgentEventRecord` |
| `app/services/workspace.py` | 创建 `workspaces/<run-id>/`，写入固定 Maven/Spring Boot 骨架、启动类和 Agent 生成文件；限制路径、文件数量和总大小；保存结构化产物与 Doc 交付文档；读取 Java 源码。 | `pom.xml`、`application.yml`、`application-demo.yml`、Agent 输出 |
| `app/services/maven.py` | 在生成工程目录中执行 `mvn -B test`，设置 300 秒超时，截取输出尾部并保存原始日志到 `artifacts/maven-test.log`。 | 宿主机 Maven、生成工作区 |
| `app/services/artifacts.py` | 枚举生成文件、阻止目录穿越、限制在线查看大小、生成 ZIP、排除构建缓存，并生成相对空目录的文本 Diff。 | `workspaces/<run-id>/` |

`run_executor.py` 目前只把各 Agent 的完整 JSON 结果和主 Agent 决策登记为 `artifacts` 表记录。生产代码、测试、日志、README、OpenAPI 和使用手册属于工作区文件，通过文件列表和 ZIP 接口交付。运行估算费用字段已经存在，但当前执行流程尚未按每次模型响应计算并回填该字段。

## 5. 前端源码

前端位于 `frontend/`，使用 React 19、TypeScript 和 Vite。

| 文件或目录 | 作用 | 关键内容 |
| --- | --- | --- |
| `frontend/index.html` | Vite HTML 入口。 | 设置中文页面、响应式 viewport、页面标题和描述，并挂载 `/src/main.tsx`。 |
| `frontend/src/main.tsx` | React 应用启动文件。 | 创建 React 根节点，启用 `StrictMode`，加载全局样式。 |
| `frontend/src/App.tsx` | 单页控制台的页面状态和交互。 | 加载健康状态、创建/选择项目、显示运行历史、启动运行、通过 SSE 更新事件和 Agent 状态、显示 Token、加载最终交付物、浏览文件、查看 Diff 和下载 ZIP。 |
| `frontend/src/api.ts` | 前端 API 客户端。 | 统一 API Base URL、JSON 请求处理、错误提取、文件文本读取，以及 SSE 和 ZIP 下载 URL 生成。默认连接当前主机的 `8000` 端口，可由 `VITE_API_BASE_URL` 覆盖。 |
| `frontend/src/types.ts` | 前端 TypeScript 数据契约。 | 与 FastAPI 响应对应的运行状态、项目、事件、产物、文件、Diff 和健康检查类型。 |
| `frontend/src/styles.css` | 控制台视觉样式。 | 定义暗色主题、响应式三栏布局、状态标签、Agent 节点、事件时间线、文件树、Diff、错误提示和移动端布局。 |
| `frontend/package.json` | 前端包定义。 | 声明 React、TypeScript、Vite 及插件依赖，提供 `dev`、`build`、`preview` 命令。 |
| `frontend/package-lock.json` | 前端依赖锁文件。 | 锁定 npm 依赖的精确解析结果，保证安装可重复。 |
| `frontend/tsconfig.json` | TypeScript 配置。 | 启用严格类型检查、ES2022、DOM、Bundler 模块解析和 React JSX，不输出编译文件。 |
| `frontend/vite.config.ts` | Vite 配置。 | 启用 React 插件，开发服务器端口固定为 `5173`。 |
| `frontend/dist/` | 前端生产构建产物。 | 由 `npm run build` 生成，包含 HTML、带哈希的 JavaScript 和 CSS；不是手工维护源码。 |
| `frontend/node_modules/` | 本地依赖目录。 | 由 `npm install` 生成，不应提交或逐文件维护。 |

当前页面功能集中在 `App.tsx`。如果后续拆分组件，应同步更新本文档，并保持 API 类型、后端响应模型和页面状态字段一致。

## 6. 脚本

| 文件 | 作用 | 使用场景 |
| --- | --- | --- |
| `scripts/run_api.py` | 使用 Uvicorn 启动后端，并为 Windows 提供 Selector 事件循环工厂。 | 后端正式开发启动入口 |
| `scripts/export_development_token_usage.py` | 扫描当前项目的 Codex 会话 JSONL，提取每轮 `token_usage_record`，读取模型价格，按峰谷时段和缓存命中情况估算费用，生成 `docs/DEVELOPMENT_TOKEN_USAGE.md`。同时做请求摘要限长和敏感信息脱敏。 | 每完成一个开发任务后 |
| `scripts/verify_checkpoint.py` | 用确定性 Agent 执行六节点 LangGraph，验证 PostgreSQL checkpoint 确实创建并保存完整状态。 | 检查 checkpoint 集成 |
| `scripts/verify_neo4j.py` | 连接 Neo4j，创建临时 Project/File/Class/Method/Test 节点和关系，执行 Cypher 查询，然后清理验证数据。 | 检查 Neo4j 真实读写 |

Token 导出脚本支持通过 `--session-file`、`--sessions-root`、`--output` 和 `--pricing-file` 覆盖默认路径。默认输出到 `docs/DEVELOPMENT_TOKEN_USAGE.md`，默认价格配置为 `configs/model_pricing.json`。

## 7. 测试

| 文件 | 覆盖内容 | 未覆盖边界 |
| --- | --- | --- |
| `tests/test_api.py` | 验证 `/health/live` 不依赖外部数据库并可返回 200。 | 其他 REST 接口、数据库持久化和 SSE 的长连接行为 |
| `tests/test_artifacts.py` | 验证文件列表、Diff、ZIP 会排除构建目录，并验证目录穿越会被拒绝。 | 工作区并发写入、真实大文件下载 |
| `tests/test_config.py` | 验证 DashScope 作为对话提供方和通用 Embedding 配置回退。 | 所有环境变量组合及真实凭证连通性 |
| `tests/test_supervisor.py` | 验证六个 Agent 顺序调用、首个失败后停止、Reviewer 拒绝后返回 Coder 并重新测试/评审。 | 真实模型输出、真实 Maven、预算耗尽分支 |
| `tests/test_test_generation.py` | 验证 Tester 会针对 Architect 的列表、详情和创建接口生成对应 JUnit 契约测试。 | 生成测试在任意 Spring Boot 工程中的实际编译与执行 |

运行全部自动化测试：

```powershell
python -m pytest
```

真实外部依赖、真实模型和 Maven 生成链路应通过集成运行或验收场景验证，不能由上述单元测试替代。

## 8. 配置目录

| 文件 | 作用 |
| --- | --- |
| `configs/model_pricing.json` | 保存模型显示名、别名、币种、计价单位、峰谷时段及每百万 Token 的缓存命中输入、缓存未命中输入和输出价格。`scripts/export_development_token_usage.py` 读取此文件估算开发费用。 |

价格配置只用于估算。未配置模型时必须标记无法计价，不能猜测价格；最终费用以供应商账单为准。

## 9. 项目文档

| 文档 | 内容与使用场景 |
| --- | --- |
| `docs/PROJECT_REQUIREMENTS.md` | 项目范围、用户场景、MVP 功能、Agent 职责、状态机、数据存储、接口、页面、Token 控制、安全、测试和验收标准的最高层需求依据。 |
| `docs/IMPLEMENTATION_STATUS.md` | 当前已完成能力、已验证结果、尚未完成项和下一阶段计划。用于判断“需求是否已经实现”。 |
| `docs/RUN_REPORT_2026-11-02.md` | 首次端到端验收报告，记录运行 ID、六 Agent 结果、Maven 测试、CRUD 验收、产物和限制。 |
| `docs/DATABASE.md` | PostgreSQL 的职责、连接方式、容器启动、表结构和 checkpoint 说明。 |
| `docs/GRAPH_DATABASE.md` | Neo4j 连接信息、节点与关系目标、初始化约束、健康检查和验证结果。 |
| `docs/FRONTEND.md` | React 控制台的技术版本、安装、前后端启动、页面能力、CORS、日志和当前限制。 |
| `docs/ENVIRONMENT_VARIABLES.md` | Chat、Embedding、Reranker、PostgreSQL、Milvus 和 Neo4j 的用途、配置项、提供方选择和密钥安全规则。 |
| `docs/DEPENDENCIES.md` | Conda 环境、Python 版本、安装命令、直接生产依赖、开发依赖和完整版本记录。 |
| `docs/MODEL_PRICING.md` | 模型公开价格、峰谷规则、缓存计价规则和估算边界。 |
| `docs/DEVELOPMENT_TOKEN_USAGE.md` | 由脚本自动生成的开发过程逐轮 Token、模型、时段、费用和状态记录。该文档记录 Codex 开发成本，不是平台运行成本。 |
| `docs/PROJECT_FILE_GUIDE.md` | 当前文档，解释每个源码、配置、脚本、测试、文档和运行产物的用途。 |

`README.md` 是项目总入口，`docs/PROJECT_REQUIREMENTS.md` 是需求事实来源，`docs/IMPLEMENTATION_STATUS.md` 是实现事实来源，本文档是文件职责事实来源。

## 10. 运行数据和生成工程

以下目录通常在运行时生成，不属于平台源码：

| 路径 | 内容 | 是否应提交 |
| --- | --- | --- |
| `workspaces/<run-id>/` | 某次运行生成的完整工程、产物和测试日志 | 否，已被 `.gitignore` 排除 |
| `frontend/node_modules/` | 前端 npm 依赖 | 否 |
| `frontend/dist/` | 前端构建结果 | 否，构建时生成 |
| `.pytest_cache/` | pytest 缓存 | 否 |
| `.ruff_cache/` | Ruff 缓存 | 否 |
| `.mypy_cache/` | mypy 缓存 | 否 |
| `.idea/` | PyCharm 本地项目元数据 | 否 |

单个 `workspaces/<run-id>/` 的典型结构如下：

```text
workspaces/<run-id>/
├── README.md
├── openapi.yaml
├── pom.xml
├── docs/
│   └── USER_MANUAL.md
├── artifacts/
│   ├── 01-pm.json
│   ├── 02-architect.json
│   ├── 03-coder.json
│   ├── 04-tester.json
│   ├── 05-reviewer.json
│   ├── 06-doc.json
│   ├── main-agent-decisions.json
│   └── maven-test.log
├── src/main/java/<package-path>/
│   ├── MultiAgentApplication.java
│   ├── domain/ 或 model/
│   ├── dto/
│   ├── repository/
│   ├── service/
│   └── web/、api/ 或 controller/
├── src/main/resources/
│   ├── application.yml
│   └── application-demo.yml
├── src/test/java/<package-path>/
│   └── GeneratedApiContractTest.java
└── target/  （Maven 构建缓存，不在文件浏览和 ZIP 中）
```

生成工程中的逻辑文件用途：

| 文件 | 用途 |
| --- | --- |
| `pom.xml` | Maven 工程定义，声明 Java 21、Spring Boot 3、Web、Validation、JPA、H2、Springdoc 和测试依赖。 |
| `application.yml` | 通用应用配置，默认激活 `demo` profile。 |
| `application-demo.yml` | H2 内存数据库、JPA 建表策略和服务端口配置。 |
| `MultiAgentApplication.java` | Spring Boot 启动类，由 `WorkspaceManager.write_application()` 按架构包名生成。 |
| Entity 或 domain 类 | 表示业务实体、数据库列和状态枚举。 |
| DTO 类 | 定义创建、更新和响应接口的数据结构，并承载参数校验。 |
| Repository | 基于 Spring Data JPA 的数据访问接口。 |
| Service | 实现业务规则、状态流转、默认值、校验和持久化调用。 |
| Controller | 暴露 REST 接口，把 HTTP 请求交给 Service。 |
| 异常类 | 表达资源不存在、业务校验失败等领域错误。 |
| Error Response 与异常处理器 | 把领域异常和参数校验异常统一转换为 JSON 错误响应及正确 HTTP 状态码。 |
| `GeneratedApiContractTest.java` | Tester 根据 Architect 契约生成的 Spring Boot 随机端口 HTTP 集成测试。 |
| `maven-test.log` | `mvn -B test` 的原始输出，是测试结论的证据。 |
| Agent JSON 产物 | 保存 PM、Architect、Coder、Tester、Reviewer、Doc 的结构化结果和 Token。 |
| `main-agent-decisions.json` | 保存主 Agent 每次路由、返工和结束决策。 |
| `README.md` | 生成工程的简介、运行方法和接口概览。 |
| `docs/USER_MANUAL.md` | 生成工程的完整中文操作手册。 |
| `openapi.yaml` | 生成工程的 OpenAPI 3 接口文档。 |

不同需求下类名和目录可能不同，但 Controller、Service、Repository、Entity、DTO、异常处理和测试的职责应保持一致。当前固定骨架尚未生成 Maven Wrapper、Docker Compose 和 `.env.example`，这是已知未完成项。

## 11. 关键请求链路

创建并执行一次运行的主要调用顺序如下：

1. `frontend/src/api.ts` 调用 `POST /api/v1/projects/{project_id}/runs`。
2. `app/api/routes/runs.py` 创建 `RunRecord`，追加 `run.created` 事件，然后注册后台任务。
3. `app/services/run_executor.py::execute_run()` 加载项目和配置，把运行设为 `running`。
4. `WorkspaceManager.initialize()` 创建隔离目录并写入 Spring Boot 模板。
5. `build_supervisor_graph()` 创建主 Agent 状态图，并挂接 PostgreSQL checkpointer。
6. `LLMSpecialistExecutor` 按角色调用模型、写文件、运行 Maven 或写交付文档。
7. 每次 Agent 开始、完成或失败通过 `_emit_event()` 写入 `agent_events`。
8. 前端通过 SSE 读取并显示新增事件；终态后加载文件、Diff、产物和下载地址。
9. `execute_run()` 保存 Agent JSON、主 Agent 决策和最终运行状态。

Windows 启动链路为 `main.py` → `scripts/run_api.py` → `app.main:app`。直接使用其他方式启动 Uvicorn 时必须确保 checkpoint 使用兼容 psycopg 的事件循环。

## 12. 修改功能时的文件定位

| 要修改的内容 | 优先查看的文件 |
| --- | --- |
| 新增或修改 API | `app/api/routes/`、`app/api/schemas.py`、`frontend/src/api.ts`、`frontend/src/types.ts` |
| 调整 Agent 顺序、失败或返工规则 | `app/agents/supervisor.py`、`app/domain/models.py`、`tests/test_supervisor.py` |
| 调整某专业 Agent 的提示词或产物 | `app/agents/specialists.py`、`app/agents/schemas.py`、相关工作区读取/写入代码 |
| 调整模型提供方 | `app/core/config.py`、`app/agents/llm.py`、`.env.example`、`docs/ENVIRONMENT_VARIABLES.md` |
| 调整数据库表 | `app/db/models.py`、`app/db/session.py`、`docs/DATABASE.md` |
| 调整生成工程骨架 | `app/services/workspace.py`、`docs/RUN_REPORT_2026-11-02.md` |
| 调整 Maven 测试行为 | `app/services/maven.py`、`app/agents/specialists.py`、`tests/test_test_generation.py` |
| 调整文件浏览、Diff 或下载 | `app/services/artifacts.py`、`app/api/routes/runs.py`、`frontend/src/App.tsx`、`tests/test_artifacts.py` |
| 调整前端页面 | `frontend/src/App.tsx`、`frontend/src/styles.css`、`frontend/src/api.ts`、`frontend/src/types.ts` |
| 调整健康检查 | `app/api/routes/health.py`、`app/db/session.py`、`app/graph/neo4j.py`、`app/agents/checkpoint.py` |
| 调整开发成本统计 | `scripts/export_development_token_usage.py`、`configs/model_pricing.json`、`docs/MODEL_PRICING.md` |
| 调整启动方式 | `main.py`、`dev.py`、`scripts/run_api.py`、`compose.yaml`、`README.md` |

## 13. 当前文件级边界

以下内容尚不能从现有文件推断为已经实现：

- Milvus 只有客户端健康检查；尚无代码切分、Embedding 调用、集合初始化、向量写入和相似度检索服务。
- Neo4j 只有驱动管理、约束和健康检查；尚无正式的 Java 解析器和运行后代码图谱写入服务。
- Agent 调度当前是按固定顺序选择下一个未完成角色，不是完全自由的动态选人。
- 运行只从 Token 预算判断超限；`WAITING_BUDGET`、`WAITING_REQUIREMENT` 和 `WAITING_APPROVAL` 状态已有枚举，但尚无对应的暂停和人工交互接口。
- 前端尚无运行取消、预算确认、人工审批、Milvus 检索结果和 Neo4j 依赖图。
- 生成工程在宿主工作区执行，尚未迁移到 Docker 沙箱。
- 生成工程尚未包含 Maven Wrapper、Docker Compose 和 `.env.example`。
- 生产依赖中已有 Alembic、Milvus 和代码图工具所需要的基础库，但不能据此认为相应业务功能已经完成。

## 14. 维护检查清单

新增、删除或移动文件时，应执行以下检查：

1. 在本文档对应分类中新增、删除或修改文件职责。
2. 若接口变化，同时更新 API 模型、前端类型、接口表和相关专题文档。
3. 若启动或环境变量变化，同时更新 `.env.example`、`README.md` 和 `docs/ENVIRONMENT_VARIABLES.md`。
4. 若实现进度变化，同时更新 `docs/IMPLEMENTATION_STATUS.md`。
5. 若数据表或外部服务职责变化，同时更新 `docs/DATABASE.md`、`docs/GRAPH_DATABASE.md` 或环境文档。
6. 完成任务后运行 `scripts/export_development_token_usage.py` 更新开发 Token 记录。
7. 提交前确认 `.env`、真实密钥、`workspaces/`、缓存和构建产物没有被加入 Git。
