# 多 Agent 软件开发协作系统项目需求

- 文档版本：v0.1
- 更新时间：2026-11-02
- 目标阶段：从 0 到 1 的可运行 MVP

## 1. 项目目标

建设一个面向软件开发的 Web 协作系统。用户用自然语言提交一个受限范围内的软件开发需求，系统调度多个 Agent 完成需求分析、架构设计、任务拆分、代码生成、测试、代码评审和文档编写，并实时展示整个过程。

项目最终需要证明以下能力：

- 使用 LangGraph 实现可持久化、可恢复、可重试的多 Agent 状态流转。
- 使用主 Agent 作为每次运行的唯一负责人，统一调度六个专业子 Agent。
- 使用 FastAPI 提供项目、运行、事件流和产物接口。
- 使用 React + TypeScript 展示 Agent 协作过程与交付物。
- 使用 PostgreSQL 保存业务状态、事件和 LangGraph checkpoint。
- 使用 Milvus 检索代码、文档和历史修复案例。
- 使用 Neo4j 保存代码依赖关系并支持影响分析。
- 通过隔离工作区和测试反馈闭环生成可运行的 Spring Boot 工程。

## 2. MVP 用户场景

### 2.1 主要用户

MVP 面向单个开发者或演示者，不包含团队权限、组织管理和计费功能。

### 2.2 标准流程

1. 用户创建项目并提交软件需求。
2. 主 Agent 接收需求，决定是否询问用户、选用哪些子 Agent 以及执行顺序。
3. 主 Agent 指派 PM Agent 输出结构化需求、验收条件和待澄清问题。
4. 主 Agent 校验结果后指派 Architect Agent 输出架构、数据库设计、接口契约和任务依赖图。
5. 主 Agent 按任务依赖指派 Coder Agent，在隔离工作区内生成 Spring Boot 代码。
6. 主 Agent 指派 Tester Agent 运行编译和单元测试。
7. 测试失败时，主 Agent 决定返工范围；超过最大重试次数后终止或请求用户处理。
8. 主 Agent 指派 Reviewer Agent 检查代码差异、测试结果和跨模块影响。
9. 评审发现问题时，主 Agent 安排修复；评审通过后指派 Doc Agent 输出接口文档和中文使用手册。
10. 主 Agent 汇总产物、风险和未完成事项，等待用户最终确认。

## 3. MVP 范围

### 3.1 必须实现

- 单用户项目管理。
- 自然语言需求输入。
- 一个主 Agent（Main Agent / Supervisor）和 PM、Architect、Coder、Tester、Reviewer、Doc 六个专业子 Agent。
- LangGraph 状态图、条件分支、重试和 checkpoint。
- 隔离代码工作区及受控文件修改。
- Spring Boot 工程生成、Maven 编译和测试。
- 测试门禁和评审返工循环。
- PostgreSQL、Milvus 和 Neo4j 的真实集成。
- FastAPI REST 接口和 SSE 实时事件流。
- React 可视化界面。
- 需求、设计、代码差异、测试报告、评审报告和接口文档的保存与下载。

### 3.2 默认演示需求

MVP 使用同一个固定验收场景验证完整链路：

> 构建一个任务管理 REST API。任务包含标题、描述、状态、截止时间和创建时间；支持任务增删改查；状态只允许 `TODO`、`IN_PROGRESS`、`DONE`；标题不能为空；截止时间不能早于创建时间；接口需要参数校验、统一错误响应和单元测试。

该场景用于集成测试和验收，不代表系统只能处理这一种需求。

### 3.3 MVP 暂不实现

- 任意编程语言和任意框架的代码生成。
- 大型遗留仓库的全自动重构。
- 自动合并代码、自动发布生产环境或自动执行高风险运维操作。
- 多租户、组织架构、角色权限和计费。
- 移动端应用。
- 完全无人监督的长时间自主开发。
- 在宿主机上直接执行 Agent 生成的非受控命令。

## 4. Agent 职责

| Agent | 主要职责 | 必须输出 | 禁止事项 |
| --- | --- | --- | --- |
| Main Agent | 作为运行负责人，规划、调度、委派、验收、返工、预算控制和最终汇总 | 路由决定、任务指派、阶段验收、最终摘要、风险与待办 | 直接修改业务代码、跳过测试或评审、绕过人工确认、无限调用子 Agent |
| PM | 理解需求、识别歧义、拆分任务 | 需求说明、验收条件、任务列表、风险 | 直接编写业务代码 |
| Architect | 设计模块、数据库、接口和依赖 | 架构说明、数据模型、OpenAPI 草案、任务依赖图、ADR | 绕过评审直接交付 |
| Coder | 根据任务生成或修改代码 | 变更文件、代码差异、实现说明、风险说明 | 修改工作区外文件、部署代码 |
| Tester | 生成测试、运行测试、分析失败 | JUnit 测试、测试报告、覆盖率、失败诊断 | 通过修改断言掩盖产品缺陷 |
| Reviewer | 检查缺陷、安全和跨模块影响 | 结构化评审意见、严重级别、是否通过 | 只给笼统评价、直接忽略失败测试 |
| Doc | 根据最终代码生成文档 | OpenAPI、README、中文使用手册、部署说明、设计摘要 | 修改业务逻辑 |

所有 Agent 必须返回符合预定义 Schema 的结构化结果。Agent 之间不得通过自然语言互相猜测状态，任务状态和消息必须由 LangGraph 状态与主 Agent 调度记录保存并传递。

主 Agent 与 LangGraph 的职责必须分离：

- LangGraph 定义合法状态、合法边、输入输出 Schema、重试上限和必须通过的质量门禁。
- 主 Agent 在合法动作集合内做动态决策，例如选择下一个子 Agent、拆分任务、决定是否返工或请求用户补充。
- 子 Agent 不得自主创建新的长期任务、无限调用其他 Agent 或改变全局运行状态。
- 每次子 Agent 调用必须携带 `assignment_id`、`parent_agent_id`、目标任务、输入引用、输出 Schema、Skill 白名单、工具白名单和 Token 预算。

## 5. 工作流要求

### 5.1 状态

```text
created
→ main_agent_dispatch
→ requirement_analysis
→ waiting_requirement_answer（仅存在关键歧义时）
→ architecture_design
→ task_planning
→ implementation
→ testing
→ review
→ documentation
→ waiting_user_approval
→ completed
```

每个专业节点结束后先回到 `main_agent_dispatch`，由主 Agent 校验结果并选择合法后继节点。测试失败和评审不通过时回到 `implementation`。取消或不可恢复错误进入 `failed` 或 `cancelled`。

### 5.2 状态流转约束

- 每个节点执行前检查当前状态是否合法。
- 每次运行只能存在一个活动主 Agent。
- 所有子 Agent 调用必须来自主 Agent 分配，并返回原分配对应的结构化结果。
- 主 Agent 只能在 LangGraph 声明的合法动作集合内路由。
- 每次 Agent 调用、工具调用和状态变化都生成事件。
- 测试失败且未超过最大次数时，错误日志必须传入修复节点。
- 默认最大修复次数为 3 次，可通过环境变量配置。
- 达到最大次数后必须进入终态，不能无限循环。
- checkpoint 必须保存到 PostgreSQL，后端重启后能够读取历史状态。
- 用户可取消运行；取消操作不能产生新的模型调用或测试命令。
- 最终完成前必须经过人工确认。
- 任意模型节点达到 Token 预算上限时可以进入 `waiting_budget_approval`，由用户决定继续或终止。

## 6. 功能需求

| 编号 | 要求 |
| --- | --- |
| FR-01 | 用户可以创建、查看和删除项目。 |
| FR-02 | 用户可以提交自然语言需求和额外约束。 |
| FR-03 | 系统为每次执行生成唯一 `run_id` 和 `trace_id`。 |
| FR-04 | 系统按 LangGraph 状态图执行一个主 Agent 和六个专业子 Agent。 |
| FR-05 | 关键歧义可以暂停流程并等待用户补充。 |
| FR-06 | Agent 输出必须经过 Pydantic Schema 校验。 |
| FR-07 | Coder 只能在分配给本次运行的工作区内读写文件。 |
| FR-08 | 代码修改以文件差异形式记录，并支持回滚到任务前版本。 |
| FR-09 | Tester 必须执行真实 Maven 编译和测试，并保存原始输出。 |
| FR-10 | 测试失败必须触发修复，不得直接生成“通过”结果。 |
| FR-11 | Reviewer 发现问题时返回可定位到文件和行号的评审意见。 |
| FR-12 | 测试失败时 Reviewer 不得批准最终交付。 |
| FR-13 | Doc 必须基于最终代码生成接口文档、README 和完整中文使用手册。 |
| FR-14 | 所有产物保存到数据库和项目工作区，并支持下载。 |
| FR-15 | 前端通过 SSE 实时显示执行状态和事件。 |
| FR-16 | SSE 断线重连后可以恢复当前运行状态和历史事件。 |
| FR-17 | 用户能够查看 Agent 图、任务依赖、代码 diff、测试和评审结果。 |
| FR-18 | Milvus 必须支持代码块写入、向量检索和按项目过滤。 |
| FR-19 | Neo4j 必须保存代码实体及调用、依赖、测试关系。 |
| FR-20 | 系统记录耗时、Token、模型成本、重试次数和成功状态。 |
| FR-21 | 关键操作写入审计日志，日志中不得出现密钥。 |
| FR-22 | 历史运行可以只读回放，不重复执行模型和工具调用。 |
| FR-23 | 公共项目骨架、Maven Wrapper、配置文件、Dockerfile 和 Compose 优先由确定性模板生成。 |
| FR-24 | Agent 只接收当前任务需要的代码片段、diff、结构化摘要和检索结果，不默认传入完整仓库。 |
| FR-25 | 每次运行具有可配置的 Token 硬预算，默认 200,000；达到 80% 时告警，达到上限时暂停。 |
| FR-26 | 系统支持按 Agent 配置不同模型，并记录每次调用的模型、输入 Token、输出 Token、缓存 Token 和估算费用。 |
| FR-27 | Milvus 检索默认返回 5 至 8 个高相关片段，并支持按任务限制上下文大小。 |
| FR-28 | 生成工程必须附带 Maven Wrapper、`demo` 配置、`.env.example`、Dockerfile、Docker Compose 和完整 README。 |
| FR-29 | 生成工程不得要求用户手工修改 Java 源码或补充未声明的依赖，安装必要环境后即可运行。 |
| FR-30 | 每次运行必须且只能有一个主 Agent，负责接收需求、规划、委派和最终汇总。 |
| FR-31 | 主 Agent 必须为每个子任务生成唯一 `assignment_id`，并指定目标、输入、输出 Schema、Skill、工具和预算。 |
| FR-32 | 子 Agent 的结果必须返回主 Agent 校验，不能直接推进全局状态或自行创建无限子任务。 |
| FR-33 | 主 Agent 只能从 LangGraph 允许的动作中选择路由，非法动作必须被系统拒绝并记录事件。 |
| FR-34 | 主 Agent 的每项路由、返工、暂停、终止和最终验收决定必须持久化，并可在页面追踪。 |
| FR-35 | 主 Agent 不得直接修改业务代码、跳过测试、覆盖 Reviewer 结论或绕过人工审批。 |
| FR-36 | 主 Agent 负责聚合子 Agent 的 Token 用量，并在达到预算阈值时告警、暂停或请求用户决定。 |
| FR-37 | 主 Agent 在结束前必须确认所有必需产物齐全、没有未处理的阻断级评审问题，并输出最终风险摘要。 |
| FR-38 | 项目开发期间每轮 Codex 开发任务的实际 Token 用量必须写入开发 Token 记录文档。 |
| FR-39 | 开发 Token 记录必须根据版本化价格配置估算美元费用，并记录价格来源、币种、峰谷时段和未知价格。 |
| FR-40 | 生成工程必须附带 `docs/USER_MANUAL.md`，简要启动说明放在根目录 `README.md` 并提供手册链接。 |

## 7. 技术架构要求

### 7.1 后端

- Python 3.11.18。
- FastAPI、Uvicorn、Pydantic v2。
- LangGraph 1.x。
- SQLAlchemy 2.x、Asyncpg、Psycopg 3。
- PyMilvus。
- Neo4j Python Driver。
- 结构化日志和统一异常响应。
- LangGraph 使用“主 Agent 路由节点 + 专业子 Agent 节点”的 Supervisor 模式。
- 主 Agent 决策使用结构化输出，不解析自由文本来决定状态流转。

### 7.2 前端

- React、TypeScript、Vite。
- 使用 React Flow 绘制 Agent 和任务依赖图。
- 使用 Monaco Editor 展示代码差异。
- 页面支持桌面端，首要适配 1440px 宽度。
- 不通过轮询伪造实时性，实时状态使用 SSE。

### 7.3 生成工程

- 默认生成 Java 21、Spring Boot 3.x、Maven 工程。
- 分层至少包含 Controller、Service、Repository、Entity、DTO 和异常处理。
- 使用 Bean Validation。
- 使用 JUnit 5。
- 提供 OpenAPI 文档。
- 生成的代码必须进入独立沙箱执行，不允许直接操作宿主机。
- 包含 `mvnw.cmd` 和 `mvnw`，安装 Java 21 后可以执行测试。
- `demo` 配置使用 H2 内存数据库，只依赖 JDK 即可启动和演示。
- 默认运行配置面向 PostgreSQL，并提供 `.env.example`。
- 提供 Dockerfile 和 Docker Compose，能够一次启动应用与 PostgreSQL。
- 生成工程的测试、依赖、数据库初始化和配置不得依赖手工补充。
- 生成工程的 README 必须给出 Windows 和通用命令，并说明 `/health` 验证方法。
- 除非用户明确要求，生成应用不依赖平台的 Milvus 和 Neo4j。

### 7.4 生成工程使用手册

生成的 `docs/USER_MANUAL.md` 必须面向第一次使用该服务的开发者，至少包含：

- 项目功能、适用场景和当前限制。
- Java、Docker、PostgreSQL 等环境要求。
- `demo` 模式的一键启动、健康检查和停止命令。
- PostgreSQL 与 Docker Compose 模式的配置和启动步骤。
- `.env` 配置项说明，不得写入真实密码。
- 全部 REST 接口说明及可直接执行的 curl 或 PowerShell 示例。
- 新增、查询、修改、删除、异常响应的完整操作示例。
- Maven 测试和覆盖率查看方法。
- 数据初始化、重置和服务清理方法。
- Swagger UI 与 OpenAPI 文件访问地址。
- 端口冲突、数据库连接失败、参数校验失败和常见 HTTP 错误的排查方法。
- 生成代码版本、生成时间和适用环境说明。

README 负责快速上手，使用手册负责完整操作。两者中的项目名、端口、路径、环境变量和命令必须与最终生成工程一致。

## 8. 数据存储要求

### 8.1 PostgreSQL

至少包含以下数据：

- 项目及项目配置。
- Agent 运行记录和当前状态。
- 任务、任务依赖和任务执行结果。
- Agent 事件和工具调用记录。
- 主 Agent 与子 Agent 的层级、任务指派、路由决定和阶段验收记录。
- 每次子任务的输入引用、输出引用、Skill 白名单、工具白名单和预算。
- 需求、设计、测试、评审和文档产物。
- 人工确认记录。
- LangGraph checkpoint。

### 8.2 Milvus

Milvus 至少建立以下集合或等价设计：

- `code_chunks`：代码片段、所属项目、文件路径、符号名、语言、向量和元数据。
- `knowledge_chunks`：工程规范、历史修复记录和技术文档片段。

代码写入后应能够按 `project_id` 过滤并进行相似度检索。Milvus 只保存向量和检索元数据，不承担业务状态事务。

### 8.3 Neo4j

至少支持以下节点和关系：

- 节点：Project、Module、File、Class、Method、Test。
- 关系：`CONTAINS`、`CALLS`、`DEPENDS_ON`、`TESTS`。

Reviewer 或 Coder 修改代码前，应能够通过依赖图查询受影响的上层模块和测试。

## 9. FastAPI 接口要求

MVP 至少提供以下接口，统一使用 `/api/v1` 前缀：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/api/v1/projects` | 创建项目 |
| GET | `/api/v1/projects` | 项目列表 |
| GET | `/api/v1/projects/{project_id}` | 项目详情 |
| POST | `/api/v1/projects/{project_id}/runs` | 启动一次 Agent 运行 |
| GET | `/api/v1/runs/{run_id}` | 查询运行状态 |
| GET | `/api/v1/runs/{run_id}/events` | SSE 事件流 |
| POST | `/api/v1/runs/{run_id}/answers` | 提交需求澄清 |
| POST | `/api/v1/runs/{run_id}/approve` | 人工确认交付 |
| POST | `/api/v1/runs/{run_id}/cancel` | 取消运行 |
| GET | `/api/v1/runs/{run_id}/artifacts` | 获取产物列表 |
| GET | `/api/v1/runs/{run_id}/graph` | 获取 Agent 与任务图 |
| GET | `/api/v1/runs/{run_id}/files` | 获取生成工程文件树 |
| GET | `/api/v1/runs/{run_id}/files/content` | 读取单个生成文件 |
| GET | `/api/v1/runs/{run_id}/diff` | 获取生成工程 Diff |
| GET | `/api/v1/runs/{run_id}/download` | 下载完整工程 ZIP |

接口应返回稳定的错误码和请求追踪标识。长任务启动接口不能在 HTTP 请求中同步等待整个生成流程结束。

## 10. 可视化页面要求

至少包含以下页面或工作区：

1. 项目列表和创建项目。
2. 需求输入与运行配置。
3. 以主 Agent 为中心的 Agent 实时执行图。
4. 主 Agent 的当前决策、路由原因和子任务指派记录。
5. Agent 消息与工具调用时间线。
6. 任务列表、依赖关系和当前负责人。
7. 代码文件树和 diff 查看器。
8. 测试结果、覆盖率和失败日志。
9. 评审问题列表和严重级别。
10. 最终交付物下载。
11. 运行耗时、重试次数、Token 和成本摘要。

页面必须区分“运行中”“等待回答”“等待确认”“成功”“失败”和“已取消”。

## 11. Skill 与工具要求

- Skill 应以 `SKILL.md`、模板、Schema 和可选脚本组成。
- Skill 在执行到相关节点时按需加载，不在每一轮把所有规范注入上下文。
- Agent 与 Skill 分离：Agent 表示角色和状态，Skill 表示可复用能力。
- 工具权限独立于 Skill，不得因为加载 Skill 自动获得文件或命令权限。
- 第一版至少设计主 Agent 调度、需求分析、架构设计、Spring Boot 编码、JUnit 测试、代码评审和 OpenAPI 文档七类 Skill。
- 主 Agent 调度 Skill 只负责提供任务拆分、结果校验、路由和异常处理规范，不能绕过 LangGraph 的合法边检查。
- 所有 Skill 说明和输出模板默认使用中文。

## 12. Token 与成本控制

### 12.1 生成策略

- 公共骨架由确定性模板生成，包括 Maven Wrapper、`pom.xml`、启动类、基础配置、Dockerfile、Compose 和公共异常类。
- 大模型负责需求分析、架构决策、业务代码、测试诊断、评审和文档，不负责重复生成全部样板。
- Coder 按任务生成业务相关文件或局部补丁，不一次性生成完整仓库。
- 模板使用情况必须记录为运行事件，便于确认成本优化真实生效。

### 12.2 上下文控制

- Agent 之间只传递结构化结果、必要摘要和产物引用，禁止复制全部历史对话。
- PM、Architect、Tester、Reviewer 和 Doc 只读取当前职责需要的材料。
- Coder 优先读取目标文件、相关符号、直接依赖和任务 diff。
- 测试失败时只传递失败用例、堆栈关键部分和相关源码，不发送完整构建日志。
- Reviewer 默认评审 diff、受影响调用链和测试摘要，不读取无关文件。
- Milvus 默认召回 5 至 8 个片段，并受单次上下文长度限制。
- Neo4j 用于缩小受影响模块范围，不能因为使用图数据库而扩大上下文。
- 支持模型服务商 Prompt Cache 时优先使用；否则缓存稳定的系统提示、模板和 Embedding。

### 12.3 预算与模型路由

- 默认单次运行 Token 硬上限为 200,000，可通过 `RUN_TOKEN_BUDGET` 配置。
- 达到预算 80% 时生成告警事件，达到 100% 时暂停运行并进入 `waiting_budget_approval`。
- 用户可以增加一次预算、终止运行或保留当前 checkpoint 稍后继续。
- PM、Doc 等较简单角色默认使用轻量模型；Architect、Coder 和 Reviewer 使用更强模型。
- 模型路由配置必须版本化，不能把模型名称和凭证硬编码在业务代码中。
- 实际 Token 以模型响应中的 usage 字段为准；缺少 usage 时使用 tiktoken 估算并明确标记为估算值。
- 费用计算依赖可配置的模型价格表，不把价格写死在 Agent 中。
- 每次运行生成成本报告，按 Agent、任务、模型和重试轮次汇总。
- 固定演示场景的优化目标为端到端不超过 200,000 Token；超限必须经过显式批准。
- 达到重试或 Token 上限后必须暂停或失败，不得通过省略测试、伪造评审结果或复用旧通过结果继续。

## 13. 安全与边界

- API Key、数据库密码和 Milvus Token 只能通过环境变量或 Secret 注入。
- 生成的代码只能在 Docker 沙箱或受限工作区内运行。
- 命令使用允许列表，禁止无限制 Shell 执行。
- 沙箱默认限制网络访问、CPU、内存、磁盘和执行时间。
- 仓库内容和模型输出均视为不可信输入，防止提示注入影响系统控制指令。
- 对外部仓库执行修改前保存原始基线，并保留可恢复差异。
- 自动生成内容未经人工确认不得提交到主分支或部署。
- 日志、事件和产物中不得记录完整密钥。
- 子 Agent 的有效工具集合由主 Agent 指派和系统策略共同限制，Skill 不能自行扩大权限。
- 禁止子 Agent 直接修改全局运行状态、注册新的长期 Agent 或无限发起下级任务。

## 14. 测试与质量要求

- 为 Schema、状态转换、重试策略、SSE 事件和数据库访问编写单元测试。
- 为主 Agent 的任务委派、非法路由拒绝、返工决策和预算暂停编写单元测试。
- 为 FastAPI 接口编写集成测试。
- 为完整演示流程编写至少一条端到端测试或可重复验收脚本。
- 使用 Ruff 执行代码检查和格式化。
- 使用 mypy 检查核心 Agent、Schema 和存储模块。
- 使用 pytest-cov 记录覆盖率。
- 关键流程不得依赖人工观察才能判定成功。
- Milvus、Neo4j 和 PostgreSQL 集成测试在相关服务不可用时必须明确标记为跳过或失败，不能伪造成功。

## 15. MVP 验收标准

以下条件全部满足才算 MVP 完成：

- [ ] 项目能够按照 README 启动后端和前端。
- [ ] `/health` 能返回应用、PostgreSQL、Milvus 和 Neo4j 的连接状态。
- [ ] 用户能通过页面创建项目并启动 Agent 运行。
- [ ] 每次运行存在且只存在一个主 Agent，并由其发起全部专业子 Agent 调用。
- [ ] 主 Agent 与子 Agent 的指派、结果和路由决定能够持久化并在页面查看。
- [ ] 系统能够拒绝越权路由、无父任务调用和超出工具白名单的子 Agent 操作。
- [ ] 主 Agent 无法跳过测试、覆盖失败评审或绕过最终人工确认。
- [ ] PM 和 Architect 的 JSON 输出能够通过 Schema 校验。
- [ ] 页面能够实时显示 Agent、任务和工具调用事件。
- [ ] Coder 能在隔离工作区内生成完整 Spring Boot 工程。
- [ ] 生成工程能够通过 Maven 编译和 JUnit 测试。
- [ ] Tester 保存真实命令输出和测试报告。
- [ ] 测试失败能够触发修复，超过 3 次后进入失败状态。
- [ ] Reviewer 能给出文件级评审意见，且不能放行失败测试。
- [ ] Doc 能生成 OpenAPI、README、部署说明和 `docs/USER_MANUAL.md`。
- [ ] 使用手册覆盖 Demo 和 Docker Compose 两种启动方式，并包含可执行的接口调用示例。
- [ ] 使用手册中的项目名、端口、路径、配置项和命令与最终代码一致。
- [ ] Doc 提供的启动和停止命令至少完成一次实际执行验证。
- [ ] Milvus 完成至少一次真实向量写入和相似度查询。
- [ ] Neo4j 完成至少一次真实代码关系写入和影响分析查询。
- [ ] PostgreSQL 能保存运行事件和 checkpoint，并可恢复历史记录。
- [ ] 用户能够查看和下载最终产物。
- [ ] SSE 断线重连后能够恢复事件和当前状态。
- [ ] `pytest`、Ruff 和 mypy 通过规定的质量门禁。
- [ ] `pip check` 无依赖冲突。
- [ ] 日志和产物中不存在明文密钥。
- [ ] 生成工程包含完整 Maven Wrapper，仅安装 Java 21 即可通过 `mvnw.cmd test`。
- [ ] 生成工程可通过 `demo` 配置在只有 JDK 的环境中启动，且不需要手工修改源码。
- [ ] 生成工程可通过 Docker Compose 启动应用和 PostgreSQL，并访问 `/health`。
- [ ] `.env.example` 完整列出运行所需配置，真实密钥不会进入生成产物。
- [ ] 固定演示场景能够在默认 200,000 Token 预算内完成，或者具有明确的超额批准记录。
- [ ] Token 达到 80% 和 100% 时分别产生告警与暂停事件。
- [ ] 成本报告能够按 Agent、任务、模型和重试轮次展示实际 Token 与估算费用。
- [ ] Milvus 检索数量、上下文长度和 Agent 输入都能通过配置或运行记录核查。
- [ ] 公共骨架使用模板生成，且运行记录中存在对应模板事件。
- [ ] 非特别要求时，生成工程不依赖平台的 Milvus、Neo4j 或 Agent 服务。
- [ ] 前端能够创建项目、启动运行并通过 SSE 查看实时事件。
- [ ] 前端能够浏览生成文件、查看内容和 Diff、下载完整工程 ZIP。
- [ ] `docs/DEVELOPMENT_TOKEN_USAGE.md` 能根据 Codex 会话日志重新生成，并记录每次开发任务的输入、输出、缓存和合计 Token。
- [ ] 开发 Token 文档能够按每次模型响应计算峰谷费用、累计估算费用，并明确说明其与最终账单的差异。

## 16. 最终交付物

- 可运行的 FastAPI 后端。
- 可运行的 React 可视化前端。
- 一个主 Agent、六个专业子 Agent 和 LangGraph 工作流。
- 可复用的 Skill 目录及模板。
- 数据库模型和迁移脚本。
- Milvus 集合初始化脚本及 Milvus 服务连接检查。
- Neo4j Schema 初始化和依赖分析工具。
- Docker 沙箱与资源限制配置。
- 一个完整的 Spring Boot 示例生成结果。
- API 文档、README、部署文档、演示说明和生成工程中文使用手册。
- 单元测试、集成测试、端到端验收脚本。
- 需求、设计、评审、测试和依赖版本文档。
- 可版本化的 Spring Boot 项目骨架模板。
- 模型路由、Token 预算和价格配置文件。
- 按运行、Agent、任务和模型统计的 Token 与成本报告。
- 生成的 `demo`、PostgreSQL、Docker Compose 三种运行方式及说明。
- 开发过程 Token 使用记录及生成脚本。
- 模型价格配置、价格说明和费用计算逻辑。

## 17. 实施阶段

### 阶段一：基础骨架

- FastAPI、配置、结构化日志和健康检查。
- PostgreSQL 模型、迁移和 checkpoint。
- LangGraph 最小状态图。
- React 项目骨架和 SSE 客户端。
- Spring Boot 模板骨架、Maven Wrapper 和 demo 配置。
- Token 预算、模型路由和调用用量记录基础设施。

### 阶段二：核心闭环

- 主 Agent 调度器、六个子 Agent 和结构化输出。
- 隔离代码工作区。
- Spring Boot 生成、Maven 编译和测试。
- 评审返工和人工确认。

### 阶段三：知识与可视化增强

- Milvus 代码检索。
- Neo4j 依赖图与影响分析。
- 完整 Agent 图、diff、测试和评审页面。
- 运行指标和只读回放。

### 阶段四：验收与演示

- 固定场景端到端验收。
- 性能、安全和异常路径测试。
- README、演示脚本和面试讲解材料。
