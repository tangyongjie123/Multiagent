# 项目上下文

## 项目定位

- 从零搭建一个多 Agent 软件开发协作系统。
- 每次运行必须有一个主 Agent（Main Agent / Supervisor），统一负责规划、调度、验收和异常处理。
- 主 Agent 下包含 PM、Architect、Coder、Tester、Reviewer 和 Doc 六个专业子 Agent。
- 使用 LangGraph 编排 Agent 工作流，生成的应用程序使用 Spring Boot。
- 详细的项目范围、功能要求和验收标准以 `docs/PROJECT_REQUIREMENTS.md` 为准。

## 主 Agent 约束

- 所有用户需求和最终答复先进入主 Agent，由主 Agent 决定下一步动作。
- 子 Agent 只能由主 Agent 指派任务，并向主 Agent 返回结构化结果，不能自行无限调用其他 Agent。
- 主 Agent 负责选择 Agent、分配任务、检查输出、触发返工、请求用户补充、管理预算和决定结束或失败。
- 主 Agent 的动态决策只能发生在 LangGraph 允许的状态和动作范围内。
- 主 Agent 不得直接修改业务代码、跳过测试、覆盖 Reviewer 结论或绕过人工确认。
- 每次指派必须保存任务目标、输入范围、允许使用的 Skill 和工具、输出 Schema、预算以及父 Agent。
- 主 Agent 的每次路由、重试、暂停和终止决策都必须持久化并显示在前端。

## 项目目标

- 用户在 Web 页面提交一个受限范围内的 Spring Boot 服务需求。
- 系统通过多个 Agent 完成需求分析、架构设计、任务拆分、代码生成、测试、评审和接口文档编写。
- 成功后交付可编译、可测试、可阅读的 Spring Boot 工程及完整过程记录。
- 页面必须实时展示 Agent 状态、任务依赖、工具调用、测试结果、评审问题和代码差异。
- 核心链路必须实际运行 LangGraph、FastAPI、PostgreSQL、Milvus 和 Neo4j，不能只做静态页面或固定演示数据。

## MVP 必须交付

- 一个可通过 FastAPI 创建并运行的多 Agent 项目。
- 一条从需求输入到最终人工确认的完整工作流。
- 一个默认演示场景：生成支持任务增删改查、状态流转和参数校验的 Spring Boot API。
- 生成工程包含 Maven 配置、启动类、Controller、Service、Repository、Entity、DTO、异常处理、JUnit 测试、OpenAPI 文档和中文使用手册。
- 测试未通过时不得进入最终完成状态；代码评审发现问题时必须支持返工。
- Agent 运行状态、事件和产物必须持久化，并支持页面实时查看。
- Milvus 用于代码与文档检索，Neo4j 用于代码依赖关系，PostgreSQL 用于业务状态和 checkpoint。
- 最终产物支持查看和下载，并保留需求、设计、代码差异、测试报告、评审报告和接口文档。
- 生成工程必须包含 Maven Wrapper、演示配置、`.env.example` 和 Docker Compose，用户无需手工修改源码即可运行。

## 完成定义

- 后端、前端和依赖服务能够按文档启动。
- 固定验收场景能够端到端成功执行，且不存在伪造的 Agent 输出。
- 生成的 Spring Boot 工程能够通过 Maven 编译和测试。
- 生成工程根目录包含 README，且 `docs/USER_MANUAL.md` 能按最终代码完成从准备环境到调用接口的完整操作。
- 使用手册中的启动、测试、停止、清理和接口命令经过验证，不得包含过期路径或占位符。
- Agent 失败重试、最大重试次数和最终失败状态能够正确呈现。
- Milvus 和 Neo4j 具有真实读写及检索结果，不能只初始化客户端。
- 项目通过自动化测试、静态检查、依赖冲突检查和基础安全检查。
- 不满足上述条件时，不得将项目标记为 MVP 完成。

## 成本与上下文约束

- 采用“模板骨架 + Agent 生成业务代码”的方式，不要求模型从零输出全部样板文件。
- Agent 只接收任务所需的代码、diff、检索片段和日志，不得默认传入完整仓库或完整对话。
- PM、Doc 等任务优先使用轻量模型，Architect、Coder、Reviewer 等复杂任务使用能力更强的模型。
- 默认单次运行 Token 预算为 200,000，达到预算上限时暂停并等待用户决定，不能静默超额。
- 默认最大修复次数为 3 次，Milvus 默认召回数量控制在 5 至 8 个高相关片段。
- 实际 Token、估算费用、模型名称、重试次数和上下文来源必须持久化并能在页面查看。
- Token 控制不能牺牲真实测试和评审结果；预算不足时应明确暂停或失败，不能伪造通过。

## 运行技术栈

- 编排后端使用项目绑定的 Conda 虚拟环境 `D:\itwork\itwork2026\app\Miniconda3\envs\multiagent`，Python 版本为 3.11.18。
- Python 解释器路径为 `D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe`，IDE 已绑定该环境。
- 后端 API 使用 FastAPI、Uvicorn 和 Pydantic v2。
- FastAPI 负责 REST 接口、Agent 运行事件流，并可选托管构建后的前端静态资源。
- 可视化界面使用独立的 React + TypeScript 前端，FastAPI 本身不承担可视化界面开发。
- MVP 阶段通过 SSE 向前端推送 Agent 进度、工具调用、测试结果、评审问题和代码差异；需要双向实时控制时再引入 WebSocket。

## Milvus 环境

- Milvus 是代码和文档检索所需的向量数据库。
- 虚拟机由用户启动，Milvus 运行在虚拟机的 Docker 环境中。
- 在进行任何依赖 Milvus 的开发或集成测试前，先连接虚拟机并确认 Milvus 整套服务已经启动。
- 虚拟机网络可达且具备 Docker 访问权限时，先检查现有服务，再通过项目现有的 Docker Compose 配置或明确指定的容器启动服务；等待健康检查通过后，验证 Milvus 端口是否可以连接。
- 不能仅因为项目进程已经启动，就默认 Milvus 正在运行。
- 虚拟机地址、端口、认证信息和数据库名称统一通过环境变量配置，禁止硬编码密码。
- 确认虚拟机和 Compose 的准确结构后，提供可重复执行的启动和健康检查脚本。

## 持久化边界

- Milvus 仅用于向量、向量集合和相似度检索。
- PostgreSQL 用于项目元数据、任务状态、Agent 事件和 LangGraph checkpoint。
- 不应在 Milvus 中存储事务型业务数据。

## 密钥与外部服务

- DeepSeek Chat API 用于主 Agent 和子 Agent 的对话、推理与代码生成。
- Embedding API 用于为 Milvus 生成代码和文档向量，必须单独配置。
- Reranker API 是可选项，未配置时仍应支持基础向量检索。
- 真实密钥只能写入被 `.gitignore` 排除的 `.env`，不能写入 `.env.example`、Markdown、代码、日志或测试数据。
- 用户通过聊天明文发送的密钥应视为已泄露，提醒用户撤销和轮换后再使用。
- 外部服务、环境变量和推荐配置记录在 `docs/ENVIRONMENT_VARIABLES.md`。

## 语言约定

- 项目规则、Agent 提示词、需求文档、评审报告和交付说明默认使用中文。
- 代码标识符、接口字段、环境变量和命令名称保留英文。

## 依赖管理

- 直接生产依赖记录在 `requirements.txt`。
- 测试和代码质量依赖记录在 `requirements-dev.txt`。
- 当前共享 Conda 环境的完整冻结版本记录在 `requirements-lock.txt`。
- 依赖用途、安装和迁移说明记录在 `docs/DEPENDENCIES.md`。

## 开发过程 Token 记录

- 每次完成一个开发任务后，更新 `docs/DEVELOPMENT_TOKEN_USAGE.md`。
- Token 数据优先读取 Codex 会话日志中的 `token_usage_record`，记录输入、缓存输入、输出、推理和合计 Token。
- 使用项目脚本 `scripts/export_development_token_usage.py` 生成文档，不手工编造或复制错误数字。
- 费用使用 `configs/model_pricing.json` 中的公开单价计算，同时记录币种、价格来源和读取日期。
- 按每条模型响应的实际时间判断峰时或谷时，缓存命中与缓存未命中分别计价。
- 金额属于估算值，最终以模型供应商账单为准；价格未配置时必须标记，不能猜算。
- 如果当前轮次尚未完成，明确标记为“进行中”；下一轮开始时重新生成并补齐。
- 开发过程 Token 记录和平台运行过程 Token 记录必须分开，不能混为一谈。
