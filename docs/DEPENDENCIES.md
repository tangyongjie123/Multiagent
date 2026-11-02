# Python 环境与依赖版本

更新时间：2026-11-02

## 当前环境

| 项目 | 配置 |
| --- | --- |
| 环境类型 | Conda 虚拟环境 |
| 环境名称 | `multiagent` |
| 环境目录 | `D:\itwork\itwork2026\app\Miniconda3\envs\multiagent` |
| Python 解释器 | `D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe` |
| Python 版本 | 3.11.18 |
| pip 版本 | 26.2.2 |
| PyCharm 解释器 | 已绑定上述环境 |

项目复用 IDE 已绑定的 Conda 环境，没有额外创建 `.venv`。后端统一使用 Python 3.11，不使用系统默认的 Python 3.12。

## 安装依赖

在项目根目录执行：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip install -r requirements.txt
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip install -r requirements-dev.txt
```

检查依赖是否完整：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip check
```

## 直接生产依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| fastapi | 0.162.0 | HTTP API |
| uvicorn[standard] | 0.54.0 | ASGI 服务 |
| pydantic | 2.14.2 | 数据模型与校验 |
| pydantic-settings | 2.16.2 | 环境变量配置 |
| sse-starlette | 3.6.0 | Agent 运行事件 SSE |
| httpx | 0.28.1 | 异步 HTTP 客户端 |
| aiofiles | 25.1.0 | 异步文件读写 |
| python-dotenv | 1.2.4 | 本地 `.env` 加载 |
| python-multipart | 0.0.33 | 文件上传支持 |
| langgraph | 1.2.19 | 多 Agent 状态图编排 |
| langgraph-checkpoint-postgres | 3.2.0 | LangGraph PostgreSQL checkpoint |
| langchain | 1.4.7 | Agent、消息和工具抽象 |
| langchain-openai | 1.7.3 | OpenAI 及兼容接口接入 |
| langchain-text-splitters | 1.1.3 | 代码与文档切分 |
| tiktoken | 0.14.0 | Token 计算 |
| tenacity | 9.2.1 | 失败重试 |
| pymilvus | 3.0.2 | Milvus 客户端 |
| neo4j | 6.4.1 | Neo4j 异步客户端 |
| sqlalchemy[asyncio] | 2.1.6 | PostgreSQL ORM |
| asyncpg | 0.32.0 | PostgreSQL 异步驱动 |
| psycopg[binary,pool] | 3.3.6 | LangGraph checkpoint 数据库驱动 |
| alembic | 1.20.1 | 数据库迁移 |
| redis | 8.1.0 | 后续事件总线与任务状态支持 |
| GitPython | 3.2.1 | 代码仓库操作 |
| Jinja2 | 3.1.6 | 文档与提示词模板 |
| structlog | 26.1.0 | 结构化日志 |
| PyYAML | 6.0.3 | Skill 和配置文件解析 |
| docker | 7.2.0 | Docker 服务与沙箱操作 |
| orjson | 3.13.0 | 高性能 JSON 序列化 |

## 开发依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| pytest | 9.2.0 | 单元测试与集成测试 |
| pytest-asyncio | 1.4.1.post1 | 异步测试 |
| pytest-cov | 7.1.0 | 测试覆盖率 |
| ruff | 0.17.3 | 代码检查和格式化 |
| mypy | 2.4.1 | 静态类型检查 |
| pre-commit | 4.7.0 | 提交前自动检查 |

## 完整版本记录

当前虚拟环境的完整冻结结果保存在 `requirements-lock.txt`，包含所有间接依赖。由于该 Conda 环境是共享环境，其中还包含原有的 PyAutoGUI、keyboard 等工具；创建干净环境时，应以 `requirements.txt` 和 `requirements-dev.txt` 为准。

## 验证结果

- Python 3.11.18 可用。
- FastAPI、Pydantic、LangGraph、LangChain、PyMilvus、SQLAlchemy、Neo4j 和 Psycopg 均已成功导入。
- `pip check` 返回 `No broken requirements found.`。
- Milvus 客户端已经安装，但尚未连接虚拟机中的 Milvus 服务。
- 前端 Node.js 依赖尚未安装，等创建 React 工程时单独记录。
