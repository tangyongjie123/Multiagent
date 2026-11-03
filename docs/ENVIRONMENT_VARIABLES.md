# 环境变量与外部服务

更新时间：2026-11-03

真实值写入项目根目录 `.env`。该文件已被 `.gitignore` 排除，不得提交、截图或粘贴到公开渠道。

## 1. 应用配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`、`test`、`production` |
| `APP_HOST` | `0.0.0.0` | FastAPI 监听地址 |
| `APP_PORT` | `8000` | FastAPI 端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS 允许来源，多个值用逗号分隔 |
| `UVICORN_ACCESS_LOG` | `false` | 是否记录逐请求访问日志 |
| `AUTO_CREATE_TABLES` | `true` | 开发环境自动建表；生产建议关闭 |
| `CHAT_REQUEST_TIMEOUT_SECONDS` | `120` | 单次模型请求超时，范围 10 至 600 秒 |
| `ANALYSIS_TOKEN_BUDGET` | `120000` | 单次分析输入与输出 Token 上限 |
| `MCP_TOOL_URL` | 自动使用 `http://127.0.0.1:{APP_PORT}/mcp/` | Agent 调用 MCP 工具的 Streamable HTTP 地址 |
| `MCP_TOOL_TIMEOUT_SECONDS` | `20` | 单次 MCP 工具调用超时 |
| `AGENT_MAX_TOOL_CALLS` | `3` | 单个 Agent 最大 MCP 工具调用次数 |
| `AGENT_MAX_TOOL_ROUNDS` | `3` | 最大工具推理轮数 |

## 2. Git 仓库访问

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GIT_ALLOWED_HOSTS` | `github.com,gitee.com,gitlab.com` | 允许浅克隆的主机白名单 |
| `GIT_CLONE_TIMEOUT_SECONDS` | `180` | 克隆超时，范围 10 至 600 秒 |
| `GIT_MAX_REPOSITORY_MB` | `200` | 扫描仓库体积上限 |
| `GIT_MAX_FILES` | `10000` | 扫描文件总数上限 |
| `GIT_ANALYSIS_MAX_FILES` | `80` | 送入分析的源码/配置文件数量上限 |
| `GIT_ANALYSIS_MAX_FILE_CHARS` | `20000` | 单个源码文件读取字符上限 |

`GIT_ALLOWED_HOSTS` 用于基础 SSRF 防护，不应用来允许任意第三方域名。公开仓库地址中禁止包含用户名或密码。

## 3. Chat 模型

### DeepSeek

```dotenv
CHAT_PROVIDER=deepseek
DEEPSEEK_API_KEY=replace-with-a-valid-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=replace-with-chat-model
DEEPSEEK_PRO_MODEL=replace-with-stronger-model
```

### DashScope 或兼容接口

```dotenv
CHAT_PROVIDER=dashscope
DASHSCOPE_API_KEY=replace-with-a-valid-key
DASHSCOPE_BASE_URL=replace-with-openai-compatible-base-url
DASHSCOPE_CHAT_MODEL=replace-with-chat-model
```

只配置当前使用的供应商即可。模型 Key 只用于平台自身推理，不发送到被审查仓库。

## 3.1 MCP 工具服务

```dotenv
MCP_TOOL_URL=http://127.0.0.1:8000/mcp/
MCP_TOOL_TIMEOUT_SECONDS=20
AGENT_MAX_TOOL_CALLS=3
AGENT_MAX_TOOL_ROUNDS=3
```

MCP 服务默认挂载到 FastAPI 的 `/mcp/` 路径，不需要单独端口。修改 `APP_PORT` 后，如果显式设置了 `MCP_TOOL_URL`，必须同步修改该地址。

当前 MCP 端点没有单独的远程认证，只适合本机开发。部署到不可信网络前必须增加认证、授权和网络访问控制。

## 4. Embedding

通用 OpenAI 兼容配置：

```dotenv
EMBEDDING_PROVIDER=openai-compatible
EMBEDDING_API_KEY=replace-with-a-valid-key
EMBEDDING_BASE_URL=replace-with-openai-compatible-base-url
EMBEDDING_MODEL=replace-with-embedding-model
EMBEDDING_DIMENSION=1024
```

未配置通用字段时可回退到：

```dotenv
DASHSCOPE_EMBEDDING_MODEL=replace-with-embedding-model
DASHSCOPE_EMBEDDING_DIMENSION=1024
```

Embedding 维度必须与 Milvus 集合一致。当前版本已支持配置和健康检查，但尚未在每次仓库分析时自动生成和写入向量。

## 5. Reranker

```dotenv
RERANK_API_KEY=
RERANK_BASE_URL=
RERANK_MODEL=
```

当前为预留配置，不接入仓库分析主链路。未配置时不影响基础分析。

## 6. PostgreSQL

```dotenv
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=multiagent
POSTGRES_USER=multiagent
POSTGRES_PASSWORD=replace-with-a-strong-password
```

该服务保存业务数据、Agent 事件、问题和 LangGraph checkpoint。生产环境应使用专用数据库和最小权限用户，不要长期使用超级用户。

## 7. Milvus

```dotenv
MILVUS_URI=http://replace-with-milvus-host:19530
MILVUS_USER=replace-with-milvus-user
MILVUS_PASSWORD=replace-with-milvus-password
MILVUS_TOKEN=
MILVUS_DATABASE=default
MILVUS_TOP_K=8
```

Milvus 运行在用户维护的虚拟机 Docker 环境中。启动平台前应先确认虚拟机可达、容器健康且 19530 端口可连接。`/health` 会执行 `list_collections()` 做真实连接检查。

## 8. Neo4j

```dotenv
NEO4J_URI=bolt://replace-with-neo4j-host:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace-with-neo4j-password
```

应用启动时会验证连接并创建代码图谱约束。当前尚未在分析业务中自动写入代码图谱。

## 9. 服务是否必需

| 服务 | MVP 主链路 | 当前用途 |
| --- | --- | --- |
| PostgreSQL | 必需 | 业务状态、事件、问题、产物和 checkpoint |
| Chat API | 必需 | Architecture 和 Quality 的真实推理 |
| Git | 必需 | 本地浅克隆公开仓库 |
| Milvus | 可选 | 当前仅健康检查和后续向量检索基础 |
| Neo4j | 可选 | 当前仅连接、约束和后续图谱基础 |
| Embedding | 可选 | 当前仅健康检查，后续写入 Milvus 时必需 |
| Reranker | 可选 | 预留 |

`/health` 整体为 `degraded` 并不必然表示核心分析不可用；应查看具体组件状态。

## 10. 密钥安全

- 聊天中曾公开的 API Key 应视为泄露，必须撤销并轮换。
- `.env.example` 只能包含占位符。
- 日志、异常响应、文档、测试数据和前端构建不得出现真实密钥。
- PostgreSQL、Milvus 和 Neo4j 使用不同强密码。
- 提交前运行 `git status` 和 `git diff --check`，确认 `.env` 未被暂存。
