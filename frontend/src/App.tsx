import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import type {
  Analysis,
  AnalysisEvent,
  Artifact,
  Finding,
  HealthResult,
  Repository,
  Severity,
} from "./types";

const AGENT_ORDER = [
  "main",
  "repository",
  "architecture",
  "test",
  "security",
  "quality",
  "report",
];
const AGENT_LABELS: Record<string, string> = {
  main: "Main",
  repository: "Repository",
  architecture: "Architecture",
  test: "Test",
  security: "Security",
  quality: "Quality",
  report: "Report",
};
const TERMINAL = ["completed", "failed", "cancelled"];
const STREAM_EVENTS = [
  "analysis.created",
  "analysis.started",
  "repository.scanned",
  "agent.started",
  "agent.completed",
  "agent.failed",
  "analysis.completed",
  "analysis.failed",
  "analysis.cancelled",
  "analysis.interrupted",
];
const SEVERITIES: Severity[] = ["critical", "major", "minor", "info"];

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDuration(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function statusClass(status: string): string {
  if (["completed", "ok"].includes(status)) return "state state-good";
  if (["failed", "error", "cancelled"].includes(status)) return "state state-bad";
  if (["analyzing", "cloning", "pending"].includes(status)) return "state state-live";
  return "state";
}

function repoShortName(repository: Repository): string {
  return repository.url.replace(/\.git$/, "").split("/").slice(-2).join("/");
}

export default function App() {
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [report, setReport] = useState("");
  const [activeTab, setActiveTab] = useState<"findings" | "timeline" | "report">(
    "findings",
  );
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [clock, setClock] = useState(Date.now());

  const selectedRepository = useMemo(
    () => repositories.find((item) => item.id === selectedRepositoryId) ?? null,
    [repositories, selectedRepositoryId],
  );
  const visibleFindings = useMemo(
    () =>
      severityFilter === "all"
        ? findings
        : findings.filter((item) => item.severity === severityFilter),
    [findings, severityFilter],
  );
  const severityCounts = useMemo(
    () =>
      Object.fromEntries(
        SEVERITIES.map((severity) => [
          severity,
          findings.filter((item) => item.severity === severity).length,
        ]),
      ) as Record<Severity, number>,
    [findings],
  );
  const elapsed = analysis?.started_at
    ? formatDuration(
        (analysis.completed_at ? Date.parse(analysis.completed_at) : clock) -
          Date.parse(analysis.started_at),
      )
    : "—";
  const streamEnabled =
    analysis?.id === selectedAnalysisId &&
    ["pending", "cloning", "analyzing"].includes(analysis.status);

  async function loadAnalysis(analysisId: string): Promise<Analysis> {
    const result = await api.analysis(analysisId);
    setAnalysis(result);
    if (TERMINAL.includes(result.status)) {
      const [nextFindings, nextArtifacts] = await Promise.all([
        api.findings(analysisId),
        api.artifacts(analysisId),
      ]);
      setFindings(nextFindings);
      setArtifacts(nextArtifacts);
      if (result.status === "completed") {
        setReport(await api.report(analysisId));
      }
    }
    return result;
  }

  async function selectAnalysis(analysisId: string) {
    setSelectedAnalysisId(analysisId);
    setFindings([]);
    setArtifacts([]);
    setReport("");
    setEvents(await api.events(analysisId));
    await loadAnalysis(analysisId);
  }

  async function selectRepository(repositoryId: string) {
    setSelectedRepositoryId(repositoryId);
    setSelectedAnalysisId("");
    setAnalysis(null);
    setFindings([]);
    setArtifacts([]);
    setReport("");
    const history = await api.analyses(repositoryId);
    setAnalyses(history);
    if (history[0]) {
      await selectAnalysis(history[0].id);
    }
  }

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((requestError) => setError(String(requestError)));
    api
      .repositories()
      .then(async (items) => {
        setRepositories(items);
        if (items[0]) await selectRepository(items[0].id);
      })
      .catch((requestError) => setError(String(requestError)));
  }, []);

  useEffect(() => {
    setClock(Date.now());
    if (!analysis || TERMINAL.includes(analysis.status)) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [analysis?.id, analysis?.status]);

  useEffect(() => {
    if (!selectedAnalysisId || !streamEnabled) return;
    const stream = new EventSource(api.eventStreamUrl(selectedAnalysisId));
    const onEvent = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as AnalysisEvent;
      setEvents((current) =>
        current.some((item) => item.id === event.id)
          ? current
          : [...current, event].sort((a, b) => a.sequence - b.sequence),
      );
      void loadAnalysis(selectedAnalysisId).then((latest) => {
        if (TERMINAL.includes(latest.status)) stream.close();
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
  }, [selectedAnalysisId, streamEnabled]);

  async function submitRepository(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.createRepository(repoUrl.trim(), branch.trim() || null);
      setRepositories((current) => [
        result.repository,
        ...current.filter((item) => item.id !== result.repository.id),
      ]);
      setSelectedRepositoryId(result.repository.id);
      setAnalyses([result.analysis]);
      setEvents(await api.events(result.analysis.id));
      await loadAnalysis(result.analysis.id);
      setSelectedAnalysisId(result.analysis.id);
      setRepoUrl("");
    } catch (requestError) {
      setError(String(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function startAnalysis() {
    if (!selectedRepository) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.startAnalysis(
        selectedRepository.id,
        branch.trim() || null,
      );
      setAnalyses((current) => [created, ...current]);
      setEvents(await api.events(created.id));
      setSelectedAnalysisId(created.id);
      await loadAnalysis(created.id);
    } catch (requestError) {
      setError(String(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function cancelAnalysis() {
    if (!analysis) return;
    setBusy(true);
    try {
      setAnalysis(await api.cancelAnalysis(analysis.id));
      setEvents(await api.events(analysis.id));
    } catch (requestError) {
      setError(String(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function downloadReport() {
    if (!analysis) return;
    const content = await api.report(analysis.id);
    const url = URL.createObjectURL(new Blob([content], { type: "text/markdown" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${selectedRepository?.name ?? "repository"}-analysis.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="shell">
      <header className="masthead">
        <a className="brand" href="/">
          <span className="brand-mark">RG</span>
          <span>
            <strong>RepoGraph</strong>
            <small>AI CODE REVIEW</small>
          </span>
        </a>
        <div className="system-state">
          {health &&
            Object.entries(health.components).map(([name, component]) => (
              <span className={statusClass(component.status)} key={name}>
                <i />
                {name}
              </span>
            ))}
        </div>
      </header>

      {error && (
        <div className="notice">
          <strong>操作失败</strong>
          <span>{error}</span>
          <button onClick={() => setError("")} type="button">
            ×
          </button>
        </div>
      )}

      <div className="layout">
        <aside className="rail">
          <section className="rail-section">
            <div className="section-kicker">
              <span>New analysis</span>
              <b>01</b>
            </div>
            <form className="repo-form" onSubmit={submitRepository}>
              <label>
                Git repository
                <input
                  onChange={(event) => setRepoUrl(event.target.value)}
                  placeholder="https://github.com/org/repo.git"
                  required
                  value={repoUrl}
                />
              </label>
              <label>
                Branch
                <input
                  onChange={(event) => setBranch(event.target.value)}
                  placeholder="main（可留空）"
                  value={branch}
                />
              </label>
              <button className="solid-button" disabled={busy} type="submit">
                {busy ? "正在提交..." : "开始分析"}
              </button>
              <p className="fine-print">
                MVP 支持 GitHub、GitLab、Gitee 的公开仓库，只做只读静态分析。
              </p>
            </form>
          </section>

          <section className="rail-section repositories">
            <div className="section-kicker">
              <span>Repositories</span>
              <b>{repositories.length.toString().padStart(2, "0")}</b>
            </div>
            <div className="repo-list">
              {repositories.map((repository) => (
                <button
                  className={
                    repository.id === selectedRepositoryId
                      ? "repo-card selected"
                      : "repo-card"
                  }
                  key={repository.id}
                  onClick={() => void selectRepository(repository.id)}
                  type="button"
                >
                  <span className="repo-provider">{repository.provider}</span>
                  <strong>{repoShortName(repository)}</strong>
                  <small>{formatDate(repository.created_at)}</small>
                </button>
              ))}
            </div>
          </section>
        </aside>

        <section className="workspace">
          {selectedRepository ? (
            <>
              <div className="repo-heading">
                <div>
                  <p className="eyebrow">REPOSITORY REVIEW</p>
                  <h1>{repoShortName(selectedRepository)}</h1>
                  <a href={selectedRepository.url} rel="noreferrer" target="_blank">
                    {selectedRepository.url}
                  </a>
                </div>
                <div className="heading-actions">
                  <button className="outline-button" disabled={busy} onClick={startAnalysis}>
                    重新分析
                  </button>
                  {analysis && ["pending", "cloning", "analyzing"].includes(analysis.status) && (
                    <button className="stop-button" disabled={busy} onClick={cancelAnalysis}>
                      停止
                    </button>
                  )}
                </div>
              </div>

              <div className="status-grid">
                <article className="metric hero-metric">
                  <span>Analysis status</span>
                  <strong className={statusClass(analysis?.status ?? "pending")}>
                    {analysis?.status ?? "等待分析"}
                  </strong>
                  <small>{analysis?.summary ?? "选择历史运行或启动新分析"}</small>
                </article>
                <article className="metric">
                  <span>Elapsed</span>
                  <strong>{elapsed}</strong>
                  <small>{analysis?.current_agent ?? "—"}</small>
                </article>
                <article className="metric">
                  <span>Findings</span>
                  <strong>{analysis?.finding_count ?? findings.length}</strong>
                  <small>所有严重级别</small>
                </article>
                <article className="metric">
                  <span>Commit</span>
                  <strong className="mono">{analysis?.commit_sha?.slice(0, 8) ?? "—"}</strong>
                  <small>{analysis?.branch ?? "默认分支"}</small>
                </article>
              </div>

              <section className="agent-track">
                {AGENT_ORDER.map((agent, index) => {
                  const complete =
                    (agent === "main" && analysis?.status === "completed") ||
                    events.some(
                      (event) =>
                        event.agent === agent && event.event_type === "agent.completed",
                    );
                  const live = analysis?.current_agent === agent && analysis.status === "analyzing";
                  return (
                    <div
                      className={`agent-step${complete ? " complete" : ""}${live ? " live" : ""}`}
                      key={agent}
                    >
                      <span>{String(index).padStart(2, "0")}</span>
                      <strong>{AGENT_LABELS[agent]}</strong>
                      <i />
                    </div>
                  );
                })}
              </section>

              <div className="history-strip">
                {analyses.map((item) => (
                  <button
                    className={item.id === selectedAnalysisId ? "active" : ""}
                    key={item.id}
                    onClick={() => void selectAnalysis(item.id)}
                    type="button"
                  >
                    <span className={statusClass(item.status)}>{item.status}</span>
                    <code>{item.id.slice(0, 8)}</code>
                    <small>{formatDate(item.created_at)}</small>
                  </button>
                ))}
              </div>

              <div className="tabs">
                <button
                  className={activeTab === "findings" ? "active" : ""}
                  onClick={() => setActiveTab("findings")}
                >
                  Findings <b>{findings.length}</b>
                </button>
                <button
                  className={activeTab === "timeline" ? "active" : ""}
                  onClick={() => setActiveTab("timeline")}
                >
                  Timeline <b>{events.length}</b>
                </button>
                <button
                  className={activeTab === "report" ? "active" : ""}
                  onClick={() => setActiveTab("report")}
                >
                  Report
                </button>
              </div>

              {activeTab === "findings" && (
                <section className="tab-panel">
                  <div className="filter-row">
                    <button
                      className={severityFilter === "all" ? "active" : ""}
                      onClick={() => setSeverityFilter("all")}
                    >
                      All {findings.length}
                    </button>
                    {SEVERITIES.map((severity) => (
                      <button
                        className={severityFilter === severity ? "active" : ""}
                        key={severity}
                        onClick={() => setSeverityFilter(severity)}
                      >
                        {severity} {severityCounts[severity]}
                      </button>
                    ))}
                  </div>
                  <div className="finding-list">
                    {visibleFindings.map((finding, index) => (
                      <article className={`finding ${finding.severity}`} key={finding.id}>
                        <div className="finding-index">{String(index + 1).padStart(2, "0")}</div>
                        <div className="finding-body">
                          <div className="finding-head">
                            <span>{finding.severity}</span>
                            <span>{finding.category}</span>
                            <code>
                              {finding.file_path ?? "project"}
                              {finding.line ? `:${finding.line}` : ""}
                            </code>
                          </div>
                          <h3>{finding.title}</h3>
                          <p>{finding.evidence}</p>
                          <div className="finding-note">
                            <strong>影响</strong>
                            <span>{finding.impact}</span>
                          </div>
                          <div className="finding-note">
                            <strong>建议</strong>
                            <span>{finding.recommendation}</span>
                          </div>
                        </div>
                      </article>
                    ))}
                    {visibleFindings.length === 0 && (
                      <div className="empty-state">
                        {analysis?.status === "completed"
                          ? "当前筛选条件下没有发现问题。"
                          : "分析完成后将在这里显示问题。"}
                      </div>
                    )}
                  </div>
                </section>
              )}

              {activeTab === "timeline" && (
                <section className="tab-panel timeline">
                  {events.map((event) => (
                    <article key={event.id}>
                      <span className="timeline-time">
                        {analysis?.started_at
                          ? `+${formatDuration(
                              Date.parse(event.created_at) -
                                Date.parse(analysis.started_at),
                            )}`
                          : "—"}
                      </span>
                      <i />
                      <div>
                        <div className="timeline-head">
                          <strong>{AGENT_LABELS[event.agent] ?? event.agent}</strong>
                          <code>{event.event_type}</code>
                        </div>
                        <p>{event.message}</p>
                      </div>
                    </article>
                  ))}
                </section>
              )}

              {activeTab === "report" && (
                <section className="tab-panel report-panel">
                  <div className="report-toolbar">
                    <span>{artifacts.length} artifacts</span>
                    {analysis?.status === "completed" && (
                      <button className="outline-button" onClick={downloadReport}>
                        下载 Markdown
                      </button>
                    )}
                  </div>
                  <pre>{report || "分析完成后生成报告。"}</pre>
                </section>
              )}
            </>
          ) : (
            <div className="landing">
              <span className="landing-number">01—06</span>
              <h1>Read the repository.<br />Find what matters.</h1>
              <p>
                输入一个公开 Git 仓库地址。六个 Agent 将从结构、架构、测试、安全和质量方向依次形成证据，并由主 Agent 汇总为可下载审查报告。
              </p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
