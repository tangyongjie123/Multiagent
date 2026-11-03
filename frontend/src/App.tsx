import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import type {
  AgentEvent,
  AgentRun,
  Artifact,
  DiffResult,
  FileEntry,
  HealthResult,
  Project,
} from "./types";

const ROLE_ORDER = ["main", "pm", "architect", "coder", "tester", "reviewer", "doc"];
const ROLE_LABELS: Record<string, string> = {
  main: "主 Agent",
  pm: "PM",
  architect: "Architect",
  coder: "Coder",
  tester: "Tester",
  reviewer: "Reviewer",
  doc: "Doc",
};
const STREAM_EVENTS = [
  "run.created",
  "run.started",
  "agent.started",
  "agent.completed",
  "agent.failed",
  "run.completed",
  "run.failed",
  "run.interrupted",
];
const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function statusClass(status: string): string {
  if (["completed", "ok"].includes(status)) return "status status-ok";
  if (["failed", "error", "cancelled"].includes(status)) return "status status-error";
  if (["running", "pending"].includes(status)) return "status status-running";
  return "status status-neutral";
}

export default function App() {
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [activePath, setActivePath] = useState<string>("");
  const [activeContent, setActiveContent] = useState<string>("");
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [viewMode, setViewMode] = useState<"content" | "diff">("content");
  const [name, setName] = useState("任务管理 API");
  const [requirement, setRequirement] = useState(
    "使用 Java 21、Spring Boot 3、Maven 和 H2 生成任务管理 REST API，支持增删改查、参数校验、测试、OpenAPI 和中文使用手册。",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [clock, setClock] = useState(Date.now());

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );
  const elapsedText = useMemo(() => {
    if (!run?.started_at) return "—";
    const end = run.completed_at ? Date.parse(run.completed_at) : clock;
    return formatDuration(end - Date.parse(run.started_at));
  }, [clock, run]);

  async function loadHealth() {
    try {
      setHealth(await api.health());
    } catch (requestError) {
      setError(String(requestError));
    }
  }

  async function loadProjects() {
    try {
      const result = await api.projects();
      setProjects(result);
      setSelectedProjectId((current) => current || result[0]?.id || "");
    } catch (requestError) {
      setError(String(requestError));
    }
  }

  async function loadRun(runId: string): Promise<AgentRun> {
    const nextRun = await api.run(runId);
    setRun(nextRun);
    if (TERMINAL_STATUSES.includes(nextRun.status)) {
      await loadDeliverables(runId);
    }
    return nextRun;
  }

  async function loadDeliverables(runId: string) {
    const [nextArtifacts, nextFiles, nextDiff] = await Promise.all([
      api.artifacts(runId),
      api.files(runId).catch(() => ({ files: [] })),
      api.diff(runId).catch(() => null),
    ]);
    setArtifacts(nextArtifacts);
    setFiles(nextFiles.files);
    setDiff(nextDiff);
    if (!activePath && nextFiles.files.length > 0) {
      setActivePath(nextFiles.files[0].path);
    }
  }

  async function loadEvents(runId: string) {
    const result = await api.events(runId);
    setEvents(result);
  }

  async function selectRun(runId: string) {
    setSelectedRunId(runId);
    setEvents([]);
    setArtifacts([]);
    setFiles([]);
    setDiff(null);
    setActivePath("");
    setActiveContent("");
    await Promise.all([loadRun(runId), loadEvents(runId)]);
  }

  useEffect(() => {
    void loadHealth();
    void loadProjects();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setRuns([]);
      return;
    }
    api
      .runs(selectedProjectId)
      .then((result) => {
        setRuns(result);
        if (result[0]) {
          void selectRun(result[0].id);
        } else {
          setSelectedRunId("");
          setRun(null);
        }
      })
      .catch((requestError) => setError(String(requestError)));
  }, [selectedProjectId]);

  const streamEnabled =
    run?.id === selectedRunId &&
    ["pending", "running"].includes(run.status);

  useEffect(() => {
    if (!selectedRunId || !streamEnabled) return;

    const stream = new EventSource(api.eventStreamUrl(selectedRunId));
    const onEvent = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as AgentEvent;
      setEvents((current) =>
        current.some((item) => item.id === event.id)
          ? current
          : [...current, event].sort((left, right) => left.sequence - right.sequence),
      );
      void loadRun(selectedRunId).then((nextRun) => {
        if (TERMINAL_STATUSES.includes(nextRun.status)) {
          stream.close();
        }
      });
    };
    for (const eventName of STREAM_EVENTS) {
      stream.addEventListener(eventName, onEvent as EventListener);
    }
    return () => {
      for (const eventName of STREAM_EVENTS) {
        stream.removeEventListener(eventName, onEvent as EventListener);
      }
      stream.close();
    };
  }, [selectedRunId, streamEnabled]);

  useEffect(() => {
    if (!selectedRunId || !activePath) return;
    api
      .fileContent(selectedRunId, activePath)
      .then(setActiveContent)
      .catch((requestError) => setError(String(requestError)));
  }, [selectedRunId, activePath]);

  useEffect(() => {
    setClock(Date.now());
    if (!run || TERMINAL_STATUSES.includes(run.status)) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status]);

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const project = await api.createProject(name.trim(), requirement.trim());
      setProjects((current) => [project, ...current]);
      setSelectedProjectId(project.id);
    } catch (requestError) {
      setError(String(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function startRun() {
    if (!selectedProject) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.startRun(selectedProject.id);
      setRuns((current) => [created, ...current]);
      await selectRun(created.id);
    } catch (requestError) {
      setError(String(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function stopRun() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const cancelled = await api.cancelRun(run.id);
      setRun(cancelled);
      await loadEvents(run.id);
    } catch (requestError) {
      setError(String(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">MULTI-AGENT SOFTWARE STUDIO</p>
          <h1>开发协作控制台</h1>
        </div>
        <div className="health-strip">
          {health &&
            Object.entries(health.components).map(([name, component]) => (
              <span className={statusClass(component.status)} key={name}>
                {name}: {component.status}
              </span>
            ))}
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <strong>请求失败</strong>
          <span>{error}</span>
          <button type="button" onClick={() => setError("")}>
            关闭
          </button>
        </div>
      )}

      <div className="workspace-grid">
        <aside className="panel project-panel">
          <div className="panel-heading">
            <span>01</span>
            <h2>项目</h2>
          </div>
          <form onSubmit={createProject} className="stack-form">
            <label>
              项目名称
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label>
              开发需求
              <textarea
                rows={7}
                value={requirement}
                onChange={(event) => setRequirement(event.target.value)}
              />
            </label>
            <button className="primary" disabled={busy} type="submit">
              创建项目
            </button>
          </form>

          <div className="project-list">
            {projects.map((project) => (
              <button
                className={project.id === selectedProjectId ? "project active" : "project"}
                key={project.id}
                onClick={() => setSelectedProjectId(project.id)}
                type="button"
              >
                <strong>{project.name}</strong>
                <span>{formatDate(project.created_at)}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="panel run-panel">
          <div className="panel-heading">
            <span>02</span>
            <h2>主 Agent 运行</h2>
          </div>
          {selectedProject ? (
            <div className="run-toolbar">
              <div>
                <strong>{selectedProject.name}</strong>
                <p>{selectedProject.requirement}</p>
              </div>
              <div className="run-actions">
                <button className="primary" disabled={busy} onClick={startRun}>
                  启动新运行
                </button>
                {run && ["pending", "running"].includes(run.status) && (
                  <button className="danger" disabled={busy} onClick={stopRun}>
                    停止运行
                  </button>
                )}
              </div>
            </div>
          ) : (
            <p className="empty">请先创建或选择项目。</p>
          )}

          {runs.length > 0 && (
            <div className="run-history">
              {runs.map((item) => (
                <button
                  className={item.id === selectedRunId ? "run-row active" : "run-row"}
                  key={item.id}
                  onClick={() => void selectRun(item.id)}
                  type="button"
                >
                  <span className={statusClass(item.status)}>{item.status}</span>
                  <code>{item.id.slice(0, 8)}</code>
                  <span>{formatDate(item.created_at)}</span>
                </button>
              ))}
            </div>
          )}

          {run && (
            <>
              <div className="agent-map">
                {ROLE_ORDER.map((role) => {
                  const completed = events.some(
                    (event) =>
                      event.agent === role && event.event_type === "agent.completed",
                  );
                  const active = run.current_agent === role && run.status === "running";
                  return (
                    <div
                      className={`agent-node${completed ? " done" : ""}${active ? " active" : ""}`}
                      key={role}
                    >
                      <span>{ROLE_LABELS[role]}</span>
                    </div>
                  );
                })}
              </div>
              <div className="run-metrics">
                <div>
                  <span>状态</span>
                  <strong className={statusClass(run.status)}>{run.status}</strong>
                </div>
                <div>
                  <span>当前 Agent</span>
                  <strong>{ROLE_LABELS[run.current_agent ?? ""] ?? "—"}</strong>
                </div>
                <div>
                  <span>输入 Token</span>
                  <strong>{run.input_tokens.toLocaleString()}</strong>
                </div>
                <div>
                  <span>输出 Token</span>
                  <strong>{run.output_tokens.toLocaleString()}</strong>
                </div>
                <div>
                  <span>开始时间</span>
                  <strong>{formatDate(run.started_at)}</strong>
                </div>
                <div>
                  <span>已运行时间</span>
                  <strong className="elapsed-time">{elapsedText}</strong>
                </div>
              </div>
              <div className="event-stream">
                {events.map((event) => (
                  <article className="event" key={event.id}>
                    <div className={`event-dot event-${event.event_type}`} />
                    <div>
                      <div className="event-title">
                        <strong>{ROLE_LABELS[event.agent] ?? event.agent}</strong>
                        <span>{event.event_type}</span>
                        <em>
                          {run.started_at
                            ? `+${formatDuration(
                                Date.parse(event.created_at) -
                                  Date.parse(run.started_at),
                              )}`
                            : ""}
                        </em>
                        <time>{formatDate(event.created_at)}</time>
                      </div>
                      <p>{event.message}</p>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="panel output-panel">
          <div className="panel-heading">
            <span>03</span>
            <h2>交付物</h2>
            {selectedRunId && run?.status === "completed" && (
              <a className="download" href={api.downloadUrl(selectedRunId)}>
                下载 ZIP
              </a>
            )}
          </div>
          <div className="view-tabs">
            <button
              className={viewMode === "content" ? "active" : ""}
              onClick={() => setViewMode("content")}
            >
              文件内容
            </button>
            <button
              className={viewMode === "diff" ? "active" : ""}
              onClick={() => setViewMode("diff")}
            >
              Diff {diff ? `+${diff.additions}` : ""}
            </button>
          </div>
          {viewMode === "content" ? (
            <div className="code-layout">
              <div className="file-tree">
                {files.map((file) => (
                  <button
                    className={file.path === activePath ? "active" : ""}
                    key={file.path}
                    onClick={() => setActivePath(file.path)}
                    title={`${file.path} · ${formatBytes(file.size)}`}
                    type="button"
                  >
                    {file.path}
                  </button>
                ))}
                {files.length === 0 && <p className="empty">运行完成后显示文件。</p>}
              </div>
              <pre className="code-view">
                {activeContent || "选择左侧文件查看内容。"}
              </pre>
            </div>
          ) : (
            <pre className="diff-view">{diff?.patch || "运行完成后显示 Diff。"}</pre>
          )}
          <div className="artifact-list">
            {artifacts.map((artifact) => (
              <div className="artifact" key={artifact.id}>
                <strong>{artifact.kind}</strong>
                <span>{artifact.name}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
