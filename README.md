# MultiAgent 软件开发协作平台

一个基于 LangGraph、FastAPI、Milvus 和 Neo4j 的多 Agent 软件开发系统。

## 项目状态

当前已经完成首个可运行的端到端版本：

- 项目范围、功能需求和验收标准。
- Python 3.11 Conda 虚拟环境与依赖记录。
- DeepSeek、DashScope、Embedding、PostgreSQL、Milvus 和 Neo4j 的安全配置模板。
- 开发过程 Token、模型价格和费用统计工具。
- FastAPI 健康检查、项目接口、运行接口和 SSE 事件流。
- PostgreSQL 异步数据层及项目、运行、事件、产物模型。
- LangGraph PostgreSQL checkpoint。
- PostgreSQL 数据库连接、建表和真实 API 持久化验证。
- SSE 事件推送验证。
- 主 Agent 集中调度六个专业 Agent 的 LangGraph 图。
- DashScope `qwen3.8-flash` 对话接口和 `qwen3.7-text-embedding` 向量接口验证成功。
- 当前 `/health` 中 PostgreSQL、checkpoint、Milvus、Chat 和 Embedding 均已通过。
- Neo4j 认证、代码图谱约束和真实关系读写已验证通过。
- 主 Agent 已真实调度 PM、Architect、Coder、Tester、Reviewer 和 Doc。
- 生成工程已通过 Maven 测试和真实 CRUD 接口验收。
- 已生成 README、中文使用手册、OpenAPI 和完整 Spring Boot 后端代码。
- 提供生成工程文件树、内容查看、Diff 和 ZIP 下载接口。
- React + TypeScript 可视化控制台已可运行。

Docker 沙箱、人工审批交互和 Milvus/Neo4j 可视化将在后续阶段实现。

## 目标能力

- 主 Agent 统一规划和调度 PM、Architect、Coder、Tester、Reviewer、Doc 六个子 Agent。
- 通过 LangGraph 保存状态、控制重试并执行质量门禁。
- 在隔离工作区生成可编译、可测试的 Spring Boot 后端工程。
- 使用 PostgreSQL 保存运行状态和 checkpoint。
- 使用 Milvus 检索代码、文档和历史修复案例。
- 使用 Neo4j 分析代码依赖和修改影响。
- 使用 FastAPI + SSE 和 React 展示实时执行过程与交付物。

## 技术栈

- Python 3.11
- FastAPI、Pydantic v2、LangGraph、LangChain
- PostgreSQL、Milvus、Neo4j
- React、TypeScript、Vite
- Java 21、Spring Boot 3.x、Maven

## 目录结构

```text
.
├── AGENTS.md                 项目开发约束
├── configs/                  模型价格等配置
├── docs/                     需求、依赖、环境和费用文档
├── scripts/                  工程辅助脚本
├── .env.example              环境变量模板
├── requirements.txt          生产依赖
├── requirements-dev.txt      开发依赖
└── requirements-lock.txt     当前环境完整冻结版本
```

## 环境配置

使用项目绑定的 Conda 环境：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pip install -r requirements-dev.txt
```

创建本地配置：

```powershell
Copy-Item .env.example .env
```

然后在 `.env` 中填写自己的密钥和数据库连接信息。`.env` 已被 `.gitignore` 排除，禁止提交。

## 启动后端

激活 Conda 环境后，可以直接运行：

```powershell
python main.py
```

同时启动后端和前端：

```powershell
cd frontend
npm install
cd ..
python dev.py
```

访问 `http://127.0.0.1:5173`，停止时按 `Ctrl+C`。

完整启动命令：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m scripts.run_api
```

- 存活检查：`GET http://127.0.0.1:8000/health/live`
- 依赖检查：`GET http://127.0.0.1:8000/health`
- OpenAPI：`GET http://127.0.0.1:8000/docs`

Windows 必须使用 `scripts.run_api` 启动，以确保 psycopg 的异步 checkpoint 运行在 Selector 事件循环中。

## 项目文档

- [项目需求](docs/PROJECT_REQUIREMENTS.md)
- [依赖与 Python 环境](docs/DEPENDENCIES.md)
- [环境变量与外部服务](docs/ENVIRONMENT_VARIABLES.md)
- [模型价格](docs/MODEL_PRICING.md)
- [开发 Token 与费用记录](docs/DEVELOPMENT_TOKEN_USAGE.md)
- [数据库设计](docs/DATABASE.md)
- [Neo4j 代码依赖图](docs/GRAPH_DATABASE.md)
- [当前实现进度](docs/IMPLEMENTATION_STATUS.md)
- [首次端到端运行报告](docs/RUN_REPORT_2026-11-02.md)
- [前端运行说明](docs/FRONTEND.md)
- [故障排查与修复记录](docs/TROUBLESHOOTING.md)
- [项目文件与代码说明](docs/PROJECT_FILE_GUIDE.md)

## 安全说明

- 不在代码、文档或日志中保存真实 API Key。
- 聊天中已暴露的密钥应立即撤销并重新生成。
- Milvus 使用前先启动虚拟机中的 Docker 服务并完成健康检查。
- Agent 生成的代码只能在受控沙箱或隔离工作区中执行。
