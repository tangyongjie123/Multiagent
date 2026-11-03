# Agent 提示词位置

更新时间：2026-11-03

## 1. 主 Agent 没有 LLM 提示词

主 Agent 当前不是由模型自主规划，而是 LangGraph 中的确定性路由器。

实现位置：

```text
app/agents/supervisor.py
```

关键函数：

- `_next_role()`：按固定顺序找到下一个未完成子 Agent。
- `_main_agent_node()`：处理失败、Token 预算和下一步动作。
- `_route_main_agent()`：把动作转换为 LangGraph 条件边。

主 Agent 根据状态字段和合法动作路由，没有 System Prompt。

## 2. 实际发送给模型的提示词

所有模型提示词集中位于：

```text
app/agents/prompts.py
```

| 常量 | 用途 |
| --- | --- |
| `ARCHITECTURE_SYSTEM_PROMPT` | Architecture Agent 的职责、证据和判断边界 |
| `QUALITY_SYSTEM_PROMPT` | Quality Agent 的质量检查范围 |
| `TOOL_POLICY_PROMPT` | MCP 只读工具、证据和预算约束 |
| `NO_TOOL_FINALIZE_PROMPT` | 工具预算用尽后强制生成最终 JSON |

## 3. 不调用 LLM 的 Agent

| Agent | 实现方式 |
| --- | --- |
| Repository | 本地文件扫描与统计 |
| Test | 文件识别和 `find_related_tests` MCP 工具 |
| Security | `run_static_rules` 确定性规则 |
| Report | 汇总结构化结果并渲染 Markdown、HTML 和 SVG |

这些 Agent 没有自然语言提示词，修改行为应调整对应服务代码或规则。

## 4. 聊天扩展后的提示词规划

后续新增 Intent、Conversation、Evidence Verifier、Retrieval 和 Remediation Agent 时，仍应把系统提示词集中放在 `app/agents/prompts.py`，不要把提示词散落到路由或 Service 层。
