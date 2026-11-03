import { useMemo } from "react";

import { AGENT_LABELS, AGENT_ORDER } from "./agentMeta";
import type { AnalysisEvent } from "./types";

interface ExecutionDetailsProps {
  events: AnalysisEvent[];
  startedAt: string | null;
  currentAgent: string | null;
  analysisStatus: string;
}

interface AgentTrace {
  agent: string;
  events: AnalysisEvent[];
  status: "pending" | "running" | "completed" | "failed";
  duration: string;
}

const EVENT_LABELS: Record<string, string> = {
  "analysis.created": "创建分析任务",
  "analysis.started": "启动分析",
  "repository.scanned": "完成仓库扫描",
  "agent.started": "Agent 开始",
  "agent.completed": "Agent 完成",
  "agent.failed": "Agent 失败",
  "tool.started": "工具开始",
  "tool.completed": "工具完成",
  "tool.failed": "工具失败",
  "analysis.completed": "分析完成",
  "analysis.failed": "分析失败",
  "analysis.cancelled": "分析取消",
  "analysis.interrupted": "分析中断",
};

function formatOffset(startedAt: string | null, value: string): string {
  if (!startedAt) return "—";
  const seconds = Math.max(
    0,
    Math.round((Date.parse(value) - Date.parse(startedAt)) / 1_000),
  );
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `+${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function formatAgentDuration(events: AnalysisEvent[]): string {
  const start =
    events.find((event) => event.event_type === "agent.started") ??
    events.find((event) => event.event_type === "analysis.started");
  const end = [...events]
    .reverse()
    .find((event) =>
      [
        "agent.completed",
        "agent.failed",
        "analysis.completed",
        "analysis.failed",
        "analysis.cancelled",
      ].includes(event.event_type),
    );
  if (!start || !end) return "进行中";
  const seconds = Math.max(
    0,
    Math.round((Date.parse(end.created_at) - Date.parse(start.created_at)) / 1_000),
  );
  return `${seconds} 秒`;
}

function traceStatus(
  events: AnalysisEvent[],
  agent: string,
  currentAgent: string | null,
  analysisStatus: string,
): AgentTrace["status"] {
  if (agent === "main") {
    if (["failed", "cancelled"].includes(analysisStatus)) return "failed";
    if (analysisStatus === "completed") return "completed";
  }
  if (events.some((event) => event.event_type === "agent.failed")) return "failed";
  if (events.some((event) => event.event_type === "agent.completed")) {
    return "completed";
  }
  if (
    agent === currentAgent &&
    ["pending", "cloning", "analyzing"].includes(analysisStatus)
  ) {
    return "running";
  }
  return events.length > 0 ? "running" : "pending";
}

function safeValue(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function eventData(event: AnalysisEvent, key: string): string {
  const value = event.data[key];
  return value === undefined || value === null || value === ""
    ? "—"
    : safeValue(value);
}

function ToolStep({
  start,
  completion,
  startedAt,
}: {
  start: AnalysisEvent;
  completion: AnalysisEvent | undefined;
  startedAt: string | null;
}) {
  const toolName = eventData(start, "tool");
  const argumentsText = eventData(start, "arguments");
  const failed = completion?.event_type === "tool.failed";
  const result = completion
    ? failed
      ? eventData(completion, "error_type")
      : eventData(completion, "preview")
    : "等待工具返回";
  return (
    <details className={`tool-trace${failed ? " failed" : ""}`}>
      <summary>
        <span className="trace-time">{formatOffset(startedAt, start.created_at)}</span>
        <i />
        <strong>{toolName}</strong>
        <code>{completion?.event_type ?? "tool.running"}</code>
        {completion && (
          <small>{eventData(completion, "duration_ms")} ms</small>
        )}
      </summary>
      <div className="tool-trace-body">
        <label>调用参数</label>
        <pre>{argumentsText}</pre>
        <label>{failed ? "错误" : "结果预览"}</label>
        <pre>{result}</pre>
      </div>
    </details>
  );
}

export function ExecutionDetails({
  events,
  startedAt,
  currentAgent,
  analysisStatus,
}: ExecutionDetailsProps) {
  const traces = useMemo<AgentTrace[]>(
    () =>
      AGENT_ORDER.map((agent) => {
        const agentEvents = events.filter((event) => event.agent === agent);
        return {
          agent,
          events: agentEvents,
          status: traceStatus(agentEvents, agent, currentAgent, analysisStatus),
          duration: formatAgentDuration(agentEvents),
        };
      }),
    [events, currentAgent, analysisStatus],
  );

  return (
    <section className="execution-details">
      <div className="execution-note">
        展示 Agent、路由和 MCP 工具的可观测执行步骤，不包含模型隐藏推理。
      </div>
      {traces.map((trace, index) => {
        const completionIds = new Set(
          trace.events
            .filter((event) => ["tool.completed", "tool.failed"].includes(event.event_type))
            .map((event) => String(event.data.call_id ?? "")),
        );
        const defaultOpen =
          trace.status === "running" ||
          trace.status === "failed" ||
          trace.agent === currentAgent;
        return (
          <details
            className={`agent-trace ${trace.status}`}
            key={trace.agent}
            open={defaultOpen}
          >
            <summary>
              <span>{String(index).padStart(2, "0")}</span>
              <strong>{AGENT_LABELS[trace.agent]}</strong>
              <em>{trace.status}</em>
              <small>{trace.duration}</small>
            </summary>
            <div className="agent-trace-body">
              {trace.events.length === 0 && (
                <p className="trace-empty">尚未产生执行事件。</p>
              )}
              {trace.events.map((event) => {
                if (
                  ["tool.completed", "tool.failed"].includes(event.event_type)
                ) {
                  return null;
                }
                if (event.event_type === "tool.started") {
                  const callId = String(event.data.call_id ?? "");
                  const completion = completionIds.has(callId)
                    ? trace.events.find(
                        (candidate) =>
                          String(candidate.data.call_id ?? "") === callId &&
                          ["tool.completed", "tool.failed"].includes(
                            candidate.event_type,
                          ),
                      )
                    : undefined;
                  return (
                    <ToolStep
                      completion={completion}
                      key={event.id}
                      start={event}
                      startedAt={startedAt}
                    />
                  );
                }
                return (
                  <div className="agent-event" key={event.id}>
                    <span className="trace-time">
                      {formatOffset(startedAt, event.created_at)}
                    </span>
                    <i />
                    <div>
                      <strong>
                        {EVENT_LABELS[event.event_type] ?? event.event_type}
                      </strong>
                      <p>{event.message}</p>
                    </div>
                    <code>{event.event_type}</code>
                  </div>
                );
              })}
            </div>
          </details>
        );
      })}
    </section>
  );
}
