# Python 与前端依赖

更新时间：2026-11-03

## 1. Python 环境

| 项目 | 配置 |
| --- | --- |
| 环境类型 | Conda 虚拟环境 |
| 环境名称 | `multiagent` |
| 环境目录 | `D:\itwork\itwork2026\app\Miniconda3\envs\multiagent` |
| Python | 3.11.18 |
| pip | 26.2.2 |
| 项目绑定 | PyCharm 和终端均使用该解释器 |

项目没有额外创建 `.venv`，避免同时维护两套 Python 环境。

## 2. 安装

```powershell
cd E:\Aipracite\py_workspace\Multiagent
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip install -r requirements-dev.txt
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip check
```

依赖文件：

- `requirements.txt`：生产直接依赖。
- `requirements-dev.txt`：生产依赖、测试和代码质量工具。
- `requirements-lock.txt`：当前共享 Conda 环境的冻结快照。

`requirements-lock.txt` 包含该共享环境原有的 GUI 工具，不等于最小可部署依赖。

## 3. Python 生产依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| fastapi | 0.162.0 | REST API |
| uvicorn[standard] | 0.54.0 | ASGI 服务 |
| pydantic | 2.14.2 | 请求、领域和 Agent 输出校验 |
| pydantic-settings | 2.16.2 | `.env` 与环境变量 |
| python-dotenv | 1.2.4 | `.env` 文件加载 |
| sse-starlette | 3.6.0 | SSE 事件流 |
| httpx | 0.28.1 | 外部服务健康检查 |
| langgraph | 1.2.19 | 主 Agent 状态图 |
| langgraph-checkpoint-postgres | 3.2.0 | PostgreSQL checkpoint |
| langchain-core | 1.7.3 | 消息、工具和结构化模型调用的直接依赖 |
| langchain-openai | 1.7.3 | OpenAI 兼容 Chat API |
| mcp | 2.3.0 | MCP 服务端、Streamable HTTP 客户端与工具协议 |
| pymilvus | 3.0.2 | Milvus 客户端 |
| neo4j | 6.4.1 | Neo4j 异步驱动 |
| sqlalchemy[asyncio] | 2.1.6 | PostgreSQL ORM |
| asyncpg | 0.32.0 | SQLAlchemy PostgreSQL 驱动 |
| psycopg[binary,pool] | 3.3.6 | LangGraph checkpoint 数据库驱动 |
| alembic | 1.20.1 | 后续数据库迁移 |
| structlog | 26.1.0 | 结构化日志 |

## 4. Python 开发和测试依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| pytest | 9.2.0 | 单元测试 |
| pytest-asyncio | 1.4.1.post1 | 异步测试 |
| pytest-cov | 7.1.0 | 覆盖率 |
| ruff | 0.17.3 | Lint 和格式检查 |
| mypy | 2.4.1 | 静态类型检查 |
| pre-commit | 4.7.0 | 提交前检查 |

## 5. 前端依赖

| 依赖 | 版本 |
| --- | --- |
| Node.js | 24.16.0 |
| npm | 11.13.0 |
| react | 19.3.1 |
| react-dom | 19.3.1 |
| typescript | 7.0.2 |
| vite | 8.3.5 |
| @vitejs/plugin-react | 6.2.1 |

安装与构建：

```powershell
cd frontend
npm ci
npm run build
```

`frontend/package-lock.json` 是前端可重复安装的版本来源。

## 6. 系统工具

- Git：用于浅克隆公开仓库，需要可从终端直接执行 `git`。
- 如果 IDE 启动的后端进程找不到 Git，可在 `.env` 设置 `GIT_EXECUTABLE` 为完整路径。
- Docker：可选，用于本地启动 PostgreSQL；也可以使用已有 PostgreSQL。
- Milvus 与 Neo4j：可选，运行在用户维护的虚拟机或 Docker 环境中。
- MCP 工具服务：随 FastAPI 进程启动，默认地址为 `http://127.0.0.1:8000/mcp/`。

## 7. 后续聊天 Agent 扩展

当前依赖已经覆盖聊天和多 Agent 扩展所需能力：

- FastAPI 与 SSE：聊天 REST API 和流式回答。
- LangGraph：主 Agent 模式路由和多 Agent 状态。
- LangChain Core/OpenAI：消息、工具调用、结构化输出和聊天模型。
- MCP：受控证据工具。
- PostgreSQL：会话、消息、引用和分析状态。
- Milvus：代码块和历史问题向量检索。
- Neo4j：文件、类、方法和依赖关系查询。

因此聊天版 MVP 不需要提前加入未使用的聊天 UI 或额外向量数据库 SDK；只有实际接入新能力时才增加对应依赖。

## 8. 验证

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip check
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m ruff check main.py dev.py app tests scripts
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m mypy app tests
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pytest
cd frontend
npm run build
```
