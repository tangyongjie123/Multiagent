# RepoGraph

RepoGraph 是一个面向 Git 仓库的多 Agent 静态代码审查平台。用户提交公开仓库地址后，主 Agent 通过 LangGraph 依次调度 Repository、Architecture、Test、Security、Quality 和 Report 六个专业 Agent，输出带文件位置、证据、影响和修复建议的中文审查报告。

项目只读取被审查仓库，不执行其中的代码、脚本、测试或构建命令，也不会修改或推送目标仓库。

## 核心流程

```text
Git URL
  -> 主 Agent
  -> Repository Agent
  -> Architecture Agent
  -> Test Agent
  -> Security Agent
  -> Quality Agent
  -> Report Agent
  -> PostgreSQL 问题记录 + Markdown 报告
```

专业 Agent 通过 MCP Streamable HTTP 读取仓库目录、文件和搜索证据。每次 Agent 路由、MCP 工具调用、失败、完成和取消状态都会写入事件表，并通过 SSE 实时推送到前端。

## 已实现能力

- 支持 GitHub、GitLab 和 Gitee 的公开 HTTP/HTTPS 仓库地址。
- 使用 `git clone --depth 1 --single-branch` 浅克隆指定分支。
- 扫描文件数量、体积、语言、构建文件、测试文件、入口类与 Spring Boot 标识。
- 使用确定性规则检查疑似凭证、私钥、系统命令执行、空异常块、标准输出日志和 TODO/FIXME。
- 使用 LangGraph 实现主 Agent 到六个专业 Agent 的显式状态流转。
- 在 FastAPI 内挂载真实的 MCP Streamable HTTP 服务。
- 提供 `list_repository_tree`、`read_repository_file`、`search_repository_code`、`find_related_tests` 和 `run_static_rules` 五个只读工具。
- Architecture 和 Quality Agent 可自主调用 LangChain 工具，Test 和 Security Agent 通过 MCP 执行确定性能力。
- 使用结构化输出约束 Architecture 和 Quality Agent 的问题格式。
- 将仓库、分析状态、事件、问题和产物元数据持久化到 PostgreSQL。
- 使用 PostgreSQL 保存 LangGraph checkpoint。
- 通过 SSE 展示实时进度，并支持取消正在运行的分析。
- 在 React + TypeScript 控制台中查看问题、时间线、Markdown 报告和历史运行。
- 提供 FastAPI OpenAPI 文档和基础健康检查。

## 技术栈

| 层 | 技术 |
| --- | --- |
| API | FastAPI、Pydantic v2、Uvicorn |
| Agent 编排 | LangGraph、LangChain、MCP、OpenAI 兼容模型接口 |
| 数据 | PostgreSQL、SQLAlchemy、asyncpg、psycopg |
| 前端 | React 19、TypeScript、Vite |
| 外部服务 | Milvus、Neo4j、DashScope/DeepSeek |

## 快速启动

项目绑定以下 Conda 环境：

```text
D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe
Python 3.11.18
```

首次运行：

```powershell
cd E:\Aipracite\py_workspace\Multiagent
Copy-Item .env.example .env
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip install -r requirements-dev.txt
cd frontend
npm install
cd ..
python dev.py
```

打开 `http://127.0.0.1:5173`。`dev.py` 会同时启动 FastAPI 和 Vite，按 `Ctrl+C` 停止。

也可以分别启动：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m scripts.run_api
```

```powershell
cd frontend
npm run dev
```

健康检查和接口文档：

```text
GET http://127.0.0.1:8000/health/live
GET http://127.0.0.1:8000/health
GET http://127.0.0.1:8000/docs
```

## 质量检查

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m ruff check main.py dev.py app tests scripts
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m mypy app tests
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pytest
cd frontend
npm run build
```

## 目录结构

```text
app/
  agents/         主 Agent、专业 Agent、结构化输出和模型连接
  api/            FastAPI 路由与请求响应模型
  core/           配置和日志
  db/             PostgreSQL ORM 与会话
  domain/         领域枚举和实体
  graph/          Neo4j 连接与约束
  mcp/            MCP Streamable HTTP 工具服务与客户端
  services/       仓库克隆、静态规则、分析执行和事件
docs/
  ARCHITECTURE.md            系统架构与执行流程
  ANALYSIS_MODEL.md          Agent 职责、状态机和问题模型
  DATABASE.md                PostgreSQL 数据模型
  DEPENDENCIES.md            Python 与前端依赖
  ENVIRONMENT_VARIABLES.md   环境变量和外部服务
  FRONTEND.md                前端设计与运行说明
  GRAPH_DATABASE.md          Neo4j 图谱设计
  IMPLEMENTATION_STATUS.md   当前完成度与限制
  PROJECT_REQUIREMENTS.md    产品范围和验收标准
frontend/       React 可视化控制台
scripts/        启动和 Neo4j 验证脚本
tests/          Python 自动化测试
```

## 文档

- [项目需求](docs/PROJECT_REQUIREMENTS.md)
- [系统架构](docs/ARCHITECTURE.md)
- [分析模型](docs/ANALYSIS_MODEL.md)
- [MCP 工具](docs/MCP_TOOLS.md)
- [依赖与运行环境](docs/DEPENDENCIES.md)
- [环境变量](docs/ENVIRONMENT_VARIABLES.md)
- [PostgreSQL 设计](docs/DATABASE.md)
- [Neo4j 图谱设计](docs/GRAPH_DATABASE.md)
- [前端说明](docs/FRONTEND.md)
- [实现状态](docs/IMPLEMENTATION_STATUS.md)

## 安全边界

- 真实密钥只能保存在未纳入版本控制的 `.env`。
- Git URL 禁止携带用户名或密码，并通过 `GIT_ALLOWED_HOSTS` 限制允许的站点。
- 限制仓库大小、文件数量和克隆超时。
- 不运行被审查仓库中的任何代码或命令。
- MCP 只提供只读工具，文件路径被限制在对应分析工作区，返回值自动脱敏。
- 分析产物只写入 `workspaces/repositories/{analysis_id}`。
- 使用手册中曾公开出现过的密钥应立即撤销并轮换。
