# 项目上下文

## 项目定位

- 项目名称：RepoGraph。
- 产品方向：用户提交一个公开 Git 仓库地址，由多个 Agent 对仓库进行只读静态分析。
- 每次分析必须有一个主 Agent，统一负责规划、调度、结果校验和最终汇总。
- 主 Agent 下包含 Repository、Architecture、Test、Security、Quality、Report 六个专业子 Agent。
- MVP 优先支持 Java、Spring Boot、Maven 仓库，同时允许分析其他语言的目录和基础文件。

## 核心目标

- 接收 GitHub、GitLab 或 Gitee 的公开 HTTPS Git 地址。
- 使用浅克隆获取指定分支代码。
- 扫描仓库结构、技术栈、构建文件、测试文件和入口类。
- 从架构、测试、安全、质量四个方向生成有证据的结构化问题。
- 使用主 Agent 汇总各子 Agent 结果并生成中文审查报告。
- 前端实时展示克隆、扫描、各 Agent 分析状态、问题清单和最终报告。
- 分析完成后提供基于 Finding 证据的 AI 聊天，并展示三个聊天专业 Agent 的执行过程。

## 分层职责

- `app/api/` 只处理 HTTP 请求、响应码和输入输出 Schema。
- `app/agents/` 负责分析/聊天主 Agent 路由、专业 Agent 判断和结构化输出。
- `app/services/` 负责业务编排及副作用，包括克隆、扫描、事件、持久化和报告生成。
- `app/db/` 只提供数据库模型和会话，不包含 Agent 决策。
- `app/mcp/` 只提供受控只读工具，不直接决定分析任务何时结束。
- 调用方向保持 `API -> Service -> Agent/MCP/DB/文件系统`，避免反向依赖。

## 主 Agent 约束

- 所有分析先进入主 Agent，由主 Agent 决定下一个专业 Agent。
- 子 Agent 只能由主 Agent 调度，并向主 Agent 返回结构化结果。
- 主 Agent 只能从 LangGraph 声明的合法动作中选择路由。
- 主 Agent 负责汇总问题、去重、处理失败和决定结束状态。
- 主 Agent 的每次路由、暂停和终止决策必须持久化。
- 专业 Agent 可以通过受控 MCP 工具获取额外证据，但只能调用分配给自己且已声明的工具。

## 子 Agent 职责

| Agent | 职责 |
| --- | --- |
| Repository Agent | 仓库文件统计、语言识别、构建文件和测试文件发现 |
| Architecture Agent | 模块、分层、技术栈、依赖和架构风险分析 |
| Test Agent | 测试文件、测试框架、覆盖缺口和测试建议分析 |
| Security Agent | 凭证、命令执行和基础安全风险检查 |
| Quality Agent | 异常处理、可维护性、输入校验、并发和明显缺陷分析 |
| Report Agent | 将证据、严重级别和建议汇总为中文 Markdown 报告 |

## MCP 工具约束

- MCP 使用 Streamable HTTP，端点默认挂载在 `/mcp/`。
- Agent 只能使用只读工具：目录、文件、代码搜索、相关测试和确定性规则。
- 工具必须校验路径，禁止访问分析工作区之外的文件和软链接目标。
- 工具返回值必须限制长度，并对密码、Token、密钥和私钥进行脱敏。
- 不得提供任意 Shell、任意网络请求或目标仓库写操作工具。
- 每个 Agent 默认最多调用 3 次 MCP 工具，最多进行 3 轮工具推理。
- `tool.started`、`tool.completed` 和 `tool.failed` 必须持久化并显示在前端。

## MVP 工作流

```text
Git URL
→ 主 Agent
→ Repository Agent
→ Architecture Agent
→ Test Agent
→ Security Agent
→ Quality Agent
→ Report Agent
→ 完成
```

如果子 Agent 失败，主 Agent必须终止分析并明确展示失败原因，不能伪造分析成功。

## 运行技术栈

- Python 3.11.18。
- FastAPI、Uvicorn、Pydantic v2。
- LangGraph。
- MCP Python SDK，使用 Streamable HTTP。
- React 19、TypeScript、Vite。
- PostgreSQL。
- Milvus。
- Neo4j。
- Python 解释器：`D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe`。

## 数据与安全边界

- 只允许 HTTP/HTTPS Git URL，默认只允许 GitHub、GitLab 和 Gitee。
- Git URL 中禁止包含用户名和密码。
- 使用 `--depth 1 --single-branch` 浅克隆。
- 限制仓库大小、文件数量和克隆超时。
- 不执行被审查仓库的代码、脚本、测试或构建命令。
- 源码分析必须只读，不能修改、提交或推送被审查仓库。
- 所有生成文件只能写入 `workspaces/repositories/{analysis_id}`。
- 密钥、Token 和数据库密码只能来自 `.env`，不能进入代码、日志或报告。

## 持久化

- PostgreSQL：仓库、分析运行、事件、问题、报告元数据、聊天会话、消息、Finding 引用和聊天事件。
- LangGraph checkpoint：分析状态。
- Milvus：代码块和知识片段向量。
- Neo4j：仓库、文件、类、方法和依赖关系。
- 工作区：克隆后的仓库和生成的审查报告。

## 前端

- React 控制台用于提交仓库、查看分析历史和实时进度。
- 使用 SSE 接收 Agent 事件，不使用高频轮询。
- 顶栏提供独立“AI 助手”入口，进入后展示当前分析上下文、最近对话、快捷问题、Markdown 回答和 Finding 引用。
- 时间线必须显示 MCP 工具调用、耗时和失败状态。
- 问题必须显示严重级别、分类、文件位置、证据、影响和修复建议。
- 报告支持在线查看和 Markdown 下载。
- 默认中文界面。

## 聊天扩展

- 证据聊天 MVP 已接入主 Agent、Intent Agent、Conversation Agent 和 Evidence Verifier Agent。
- 聊天主 Agent 仍是确定性 LangGraph 路由；Intent 和 Conversation 可以调用聊天模型，Evidence Verifier 不调用模型。
- 聊天消息通过后台任务生成，Agent 阶段和 `chat.answer.delta` 正文增量均写入 PostgreSQL，并通过 SSE 实时展示。
- 同一会话在助手生成期间不得接受并发提问。
- 聊天回答必须引用已有 Finding、文件证据或明确说明证据不足。
- 聊天当前只基于已完成分析和已有 Finding，不直接读取完整仓库，也不使用 Milvus 按需索引。
- 聊天模型输入、回答、Finding 引用摘要和失败信息必须统一脱敏。

## 语言约定

- 项目规则、Agent 提示词、需求、报告和前端文案默认中文。
- 代码标识符、接口字段、环境变量和命令保留英文。

## 文档维护

- 需求以 `docs/PROJECT_REQUIREMENTS.md` 为准。
- 安装、依赖、环境变量、启动方式、数据库要求、用户操作流程或 URL 发生变化时，必须同步更新 `docs/USER_MANUAL.md`。
- 完成重要功能、发生项目方向调整或形成关键技术决策时，必须在 `docs/PROJECT_DEVELOPMENT_LOG.md` 追加开发记录和对话摘要。
- 架构、数据库、前端和 Agent 提示词文档必须随代码同步更新。
- 计费文档不属于当前项目范围。
- 不创建无实际作用的占位文档。
- 不长期保留一次性调试报告、运行快照或已经执行完的维护流水账。
