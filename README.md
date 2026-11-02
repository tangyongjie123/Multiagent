# MultiAgent 软件开发协作平台

一个基于 LangGraph、FastAPI、Milvus 和 Neo4j 的多 Agent 软件开发系统。

## 项目状态

当前处于基础设计与工程骨架阶段，已经完成：

- 项目范围、功能需求和验收标准。
- Python 3.11 Conda 虚拟环境与依赖记录。
- DeepSeek、Embedding、PostgreSQL、Milvus 和 Neo4j 的安全配置模板。
- 开发过程 Token、模型价格和费用统计工具。

后端 Agent、LangGraph 工作流、React 可视化界面和 Spring Boot 代码生成器将在后续阶段实现。

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

## 项目文档

- [项目需求](docs/PROJECT_REQUIREMENTS.md)
- [依赖与 Python 环境](docs/DEPENDENCIES.md)
- [环境变量与外部服务](docs/ENVIRONMENT_VARIABLES.md)
- [模型价格](docs/MODEL_PRICING.md)
- [开发 Token 与费用记录](docs/DEVELOPMENT_TOKEN_USAGE.md)

## 安全说明

- 不在代码、文档或日志中保存真实 API Key。
- 聊天中已暴露的密钥应立即撤销并重新生成。
- Milvus 使用前先启动虚拟机中的 Docker 服务并完成健康检查。
- Agent 生成的代码只能在受控沙箱或隔离工作区中执行。
