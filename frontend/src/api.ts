import type {
  Analysis,
  AnalysisEvent,
  Artifact,
  Finding,
  HealthResult,
  Repository,
  RepositorySubmission,
} from "./types";

const runtimeHost =
  typeof window === "undefined" ? "localhost" : window.location.hostname;

// 可通过 VITE_API_BASE_URL 覆盖，默认访问同主机的 FastAPI 8000 端口。
export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? `${window.location.protocol}//${runtimeHost}:8000`
).replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // 统一处理 JSON 响应和非 2xx 错误，页面只关注业务数据。
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResult>("/health"),
  repositories: () => request<Repository[]>("/api/v1/repositories"),
  createRepository: (url: string, branch: string | null) =>
    request<RepositorySubmission>("/api/v1/repositories", {
      method: "POST",
      body: JSON.stringify({ url, branch }),
    }),
  analyses: (repositoryId: string) =>
    request<Analysis[]>(`/api/v1/repositories/${repositoryId}/analyses`),
  startAnalysis: (repositoryId: string, branch: string | null) =>
    request<Analysis>(`/api/v1/repositories/${repositoryId}/analyses`, {
      method: "POST",
      body: JSON.stringify({ branch }),
    }),
  analysis: (analysisId: string) =>
    request<Analysis>(`/api/v1/analyses/${analysisId}`),
  cancelAnalysis: (analysisId: string) =>
    request<Analysis>(`/api/v1/analyses/${analysisId}/cancel`, {
      method: "POST",
    }),
  events: (analysisId: string) =>
    request<AnalysisEvent[]>(`/api/v1/analyses/${analysisId}/events`),
  findings: (analysisId: string) =>
    request<Finding[]>(`/api/v1/analyses/${analysisId}/findings`),
  artifacts: (analysisId: string) =>
    request<Artifact[]>(`/api/v1/analyses/${analysisId}/artifacts`),
  report: async (analysisId: string) => {
    const response = await fetch(
      `${API_BASE}/api/v1/analyses/${analysisId}/report`,
    );
    if (!response.ok) throw new Error(await response.text());
    return response.text();
  },
  eventStreamUrl: (analysisId: string) =>
    `${API_BASE}/api/v1/analyses/${analysisId}/events/stream`,
  reportDownloadUrl: (analysisId: string) =>
    `${API_BASE}/api/v1/analyses/${analysisId}/report/download`,
  reportHtmlUrl: (analysisId: string) =>
    `${API_BASE}/api/v1/analyses/${analysisId}/report/html`,
  reportHtmlDownloadUrl: (analysisId: string) =>
    `${API_BASE}/api/v1/analyses/${analysisId}/report/html/download`,
};
