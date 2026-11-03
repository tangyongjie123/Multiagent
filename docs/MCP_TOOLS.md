# MCP 工具服务

更新时间：2026-11-03

## 1. 协议与端点

RepoGraph 使用 MCP Python SDK `2.3.0`，通过 Streamable HTTP 提供工具。

默认端点：

```text
http://127.0.0.1:8000/mcp/
```

MCP 服务挂载在 FastAPI 应用内，与 Web API 共用进程和端口。客户端是 Agent 内部的 MCP 客户端，使用独立 MCP 会话调用工具。

## 2. 工具列表

| 工具 | 用途 | 主要参数 |
| --- | --- | --- |
| `list_repository_tree` | 列出仓库文件 | `max_entries` |
| `read_repository_file` | 读取文件指定行范围 | `path`、`start_line`、`max_lines` |
| `search_repository_code` | 按字面量搜索源码 | `query`、`case_sensitive`、`max_results` |
| `find_related_tests` | 查找类名或方法名相关测试 | `target`、`max_results` |
| `run_static_rules` | 执行内置安全与质量规则 | 无 |

所有工具还需要内部参数 `analysis_id`，由工具包装层自动填写，模型不能指定其他分析工作区。

## 3. Agent 权限

| Agent | 工具 |
| --- | --- |
| Repository | 不使用 MCP，直接返回本地扫描快照 |
| Architecture | 目录、文件读取、代码搜索 |
| Test | 相关测试查找 |
| Security | 确定性规则 |
| Quality | 确定性规则、文件读取、代码搜索 |
| Report | 不调用工具，只汇总结构化结果 |

## 4. 安全限制

- `analysis_id` 必须是合法 UUID，且工作区必须存在。
- 文件路径只能是仓库相对路径。
- 路径解析后必须仍位于对应分析目录内。
- 禁止路径穿越、绝对路径、空字节和指向目录外部的软链接。
- 只读取源码、配置和构建文本文件。
- 单文件最大 2 MB。
- 单次工具输出最多 100,000 字符。
- 默认单次调用超时 20 秒。
- 单个 Agent 默认最多调用 3 次工具。
- 返回内容会脱敏密码、API Key、Token、URL 凭证和私钥。
- 不提供 Shell、任意 HTTP 请求、文件写入或目标仓库执行工具。

## 5. 事件

每次工具调用写入以下事件之一：

- `tool.started`：工具名、参数摘要和调用 ID。
- `tool.completed`：耗时、输出长度和短预览。
- `tool.failed`：耗时和异常类型。

事件通过 SSE 实时推送到前端时间线。

## 6. 客户端测试

后端启动后，可运行：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m pytest tests/test_mcp_tools.py
```

自动测试覆盖：

- 文件和目录读取。
- 代码搜索。
- 相关测试查找。
- 敏感内容脱敏。
- 路径逃逸拒绝。
- LangChain 工具包装。
- `tool.started` 与 `tool.completed` 事件。

## 7. 当前限制

- MCP 端点依赖 Web API 进程启动。
- 默认客户端只访问本机 `127.0.0.1`；当前没有独立远程认证。
- 部署到不可信网络前必须增加 MCP 身份认证、来源限制和网络隔离。
- Milvus 相似代码检索和 Neo4j 影响图查询尚未注册为 MCP 工具。
- 每个工具调用创建独立 MCP 会话，后续可复用长连接降低握手开销。
