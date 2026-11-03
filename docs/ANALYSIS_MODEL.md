# Agent 与静态分析模型

更新时间：2026-11-03

## 1. 设计原则

- 所有请求先进入主 Agent。
- 主 Agent 负责选择、汇总、失败判断和终止。
- 每个专业 Agent 只处理一项明确职责。
- 专业 Agent 可以通过受控 MCP 工具获取额外代码证据。
- 确定性规则优先，模型推理补充需要语义判断的部分。
- 每条问题必须包含可检查的证据。
- 分析过程不执行目标仓库代码。
- 模型、Token、事件和问题都保留结构化记录。

所有实际发送给模型的提示词集中位于 `app/agents/prompts.py`。主 Agent 使用 LangGraph 确定性路由，没有 LLM 提示词；详细位置见 `docs/AGENT_PROMPTS.md`。

## 2. Agent 输入与输出

Agent 负责分析和路由决策，`app/services/` 负责克隆、扫描、持久化、事件、报告和资源清理。主 Agent 选定角色后，专业 Agent 返回结构化结果；业务副作用不会由模型直接执行。

### Main Agent

输入：分析 ID、仓库 URL、分支、已完成的 Agent 列表。

输出：下一动作、路由理由和持久化决策。合法动作包括：

```text
repository
architecture
test
security
quality
report
finish
fail
```

### Repository Agent

输入：文件树、扩展名、构建文件、测试文件和 Spring 入口摘要。

输出：文件数量、总字节数、语言统计、构建文件、测试文件、入口类、Spring 标识和有限源码摘要。

该 Agent 不调用大模型。

### Architecture Agent

输入：仓库扫描摘要与最多 10 个源码摘要。

可用 MCP 工具：目录、文件读取和代码搜索。

输出 Schema：`ArchitectureInsight`

```json
{
  "summary": "架构摘要",
  "tech_stack": ["Spring Boot"],
  "modules": ["controller", "service"],
  "findings": [
    {
      "category": "architecture",
      "severity": "major",
      "title": "问题标题",
      "file_path": "src/main/java/...",
      "line": 10,
      "evidence": "可验证证据",
      "impact": "影响",
      "recommendation": "建议"
    }
  ],
  "recommendations": ["改进建议"]
}
```

### Test Agent

输入：构建文件和测试文件路径。

输出：测试文件列表、框架线索、是否执行测试、测试缺口问题。

该 Agent 通过 `find_related_tests` MCP 工具查找入口类相关测试。该 MVP 不运行测试，因此不得宣称测试通过。

### Security Agent

输入：有限源码内容。

输出：确定性安全规则问题。当前规则包括：

- 疑似 API Key、Token、密码和私钥。
- `Runtime.getRuntime().exec` 与 `new ProcessBuilder(`。

该 Agent 通过 `run_static_rules` MCP 工具执行规则。

### Quality Agent

输入：确定性质量问题和最多 8 个源码摘要。

输出 Schema：`QualityReview`。模型结果与确定性结果合并，并由主 Agent 最终去重。

可用 MCP 工具：确定性规则、文件读取和代码搜索。

当前确定性规则包括：

- 空 `catch` 块。
- `System.out.print` 代替日志框架。
- TODO/FIXME 数量。

### Report Agent

输入：前序所有结构化结果。

输出：中文 Markdown 和自包含 HTML。两者均包含严重级别与分类可视化图片、汇总表，并按架构、测试、安全、质量分组列出问题位置、证据、影响和建议。

## 3. 问题模型

```text
Finding
├── category: architecture | test | security | quality
├── severity: critical | major | minor | info
├── title
├── file_path?
├── line?
├── evidence
├── impact
└── recommendation
```

严重级别定义：

| 级别 | 含义 |
| --- | --- |
| `critical` | 可能导致凭证泄露、远程控制或严重数据风险 |
| `major` | 明显影响安全、正确性、可维护性或测试保障 |
| `minor` | 局部代码质量问题或工程规范问题 |
| `info` | 提示信息或待跟踪事项 |

去重键由分类、严重级别、标题、文件、行号和证据组成。相同问题不会重复写入报告。

## 4. 上下文与 Token 控制

- Repository 扫描最多读取 `GIT_ANALYSIS_MAX_FILES` 个源码文件。
- 单文件最多读取 `GIT_ANALYSIS_MAX_FILE_CHARS` 个字符。
- Architecture 只发送 10 个摘要，每个最多 4,000 字符。
- Quality 只发送 8 个摘要，每个最多 4,000 字符。
- 默认分析 Token 预算为 120,000。
- 预算超限后工作流失败并等待用户决定。
- 不把完整仓库、数据库内容或全部历史对话默认传给模型。

## 5. 模型输出校验

- 提示词要求只返回 JSON。
- 响应通过 Pydantic Schema 校验。
- 未知字段被拒绝。
- 严重级别和问题分类必须来自枚举。
- JSON 解析失败、超时或鉴权失败都会使当前 Agent 失败。

## 6. MCP 工具调用循环

```text
模型提出 tool_calls
→ 校验 Agent 是否拥有该工具权限
→ 通过 MCP Streamable HTTP 调用
→ 记录 tool.started
→ 执行路径沙箱、长度限制和脱敏
→ 记录 tool.completed 或 tool.failed
→ 通过 ToolMessage 返回模型
→ 模型生成最终结构化结果
```

控制策略：

- 单个 Agent 默认最多 3 次工具调用。
- 默认最多 3 轮工具推理。
- 预算用完后强制模型不再调用工具，基于已有证据生成最终 JSON。
- 常见工具别名会自动规范化，例如 `read_repository_tree` 映射到 `list_repository_tree`。
- 完全未知的工具会记录 `tool.failed` 并把允许工具列表返回模型，由模型下一轮纠正。
- 不支持的文件类型或越界路径会作为工具结果返回，由模型选择其他证据，不直接终止当前 Agent。
- 非法参数会终止当前 Agent。
- 工具结果不执行目标仓库代码。

## 7. 可复现性与限制

确定性规则结果在相同源码输入下可复现。LLM 结果受模型版本、采样和供应商实现影响，因此报告不能等同于正式安全审计。

当前限制：

- 不进行编译、类型分析或运行期测试。
- 不解析完整 Java AST 或 Maven 依赖闭包。
- 不读取 Git 历史、Issue 和 Pull Request。
- Milvus 检索和 Neo4j 自动建图尚未接入主链路。
- 大型仓库只分析有限源码摘要，可能遗漏跨文件问题。
