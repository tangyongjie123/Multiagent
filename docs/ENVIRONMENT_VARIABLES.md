# 环境变量与外部服务

更新时间：2026-11-02

真实配置写入项目根目录的 `.env`。`.env` 已被 `.gitignore` 排除，禁止提交、截图或粘贴到公开聊天中。

## 必需的 SaaS API

| 服务 | 用途 | 是否必需 | 环境变量 |
| --- | --- | --- | --- |
| DeepSeek Chat API | 主 Agent 和六个子 Agent 的推理与工具调用 | 必需 | `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` |
| Embedding API | 将代码和文档转换为向量后写入 Milvus | 必需 | `EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSION` |
| Reranker API | 对 Milvus 召回结果重新排序 | 可选 | `RERANK_API_KEY`、`RERANK_BASE_URL`、`RERANK_MODEL` |

DeepSeek 用于对话和代码生成。Embedding 不能默认复用 DeepSeek Chat API，必须选择明确提供 Embedding 接口的模型服务，或后续改为本地 Embedding 模型。

## 必需的数据服务

| 服务 | 用途 | 连接信息 |
| --- | --- | --- |
| PostgreSQL | 项目、任务、Agent 事件和 LangGraph checkpoint | `POSTGRES_*` |
| Milvus | 代码、文档和历史修复案例的向量检索 | `MILVUS_URI`、`MILVUS_TOKEN`、`MILVUS_DATABASE` |
| Neo4j | 文件、类、方法、调用和测试依赖关系 | `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` |

这些不是 SaaS API Key，但需要虚拟机地址、端口和账号密码。Milvus 运行在用户虚拟机的 Docker 环境中，使用前必须先启动并完成健康检查。

## Embedding 选择建议

如果只有 DeepSeek 密钥，可以提供以下任一方案：

1. 提供 OpenAI 兼容的 Embedding API Key、Base URL 和模型名称。
2. 使用本地 Embedding 模型，例如 BGE-M3。该方案不需要 Embedding API Key，但需要额外安装模型运行依赖并下载权重。
3. 提供其他支持 Embedding 的服务，例如 SiliconFlow、DashScope 或 Jina；最终统一映射到 `EMBEDDING_*` 环境变量。

## 密钥安全

- 聊天中出现过的密钥应立即撤销并重新生成。
- `.env.example` 只保存占位符，真实 `.env` 不进入版本控制。
- 日志、错误信息和 Agent 产物不得输出完整密钥。
- 不同环境使用不同密钥，开发和生产不要共用。
- 模型价格与密钥无关，价格配置保存在 `configs/model_pricing.json`。
