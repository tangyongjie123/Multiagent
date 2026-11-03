import type {
  AgentEvent,
  AgentRun,
  Artifact,
  DiffResult,
  FileList,
  HealthResult,
  Project,
} from "./types";

const runtimeHost =
  typeof window === "undefined" ? "localhost" : window.location.hostname;

export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? `${window.location.protocol}//${runtimeHost}:8000`
).replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResult>("/health"),
  projects: () => request<Project[]>("/api/v1/projects"),
  createProject: (name: string, requirement: string) =>
    request<Project>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify({ name, requirement }),
    }),
  runs: (projectId: string) =>
    request<AgentRun[]>(`/api/v1/projects/${projectId}/runs`),
  startRun: (projectId: string) =>
    request<AgentRun>(`/api/v1/projects/${projectId}/runs`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  cancelRun: (runId: string) =>
    request<AgentRun>(`/api/v1/runs/${runId}/cancel`, {
      method: "POST",
    }),
  run: (runId: string) => request<AgentRun>(`/api/v1/runs/${runId}`),
  events: (runId: string) =>
    request<AgentEvent[]>(`/api/v1/runs/${runId}/events`),
  artifacts: (runId: string) =>
    request<Artifact[]>(`/api/v1/runs/${runId}/artifacts`),
  files: (runId: string) =>
    request<FileList>(`/api/v1/runs/${runId}/files`),
  fileContent: async (runId: string, path: string) => {
    const response = await fetch(
      `${API_BASE}/api/v1/runs/${runId}/files/content?path=${encodeURIComponent(path)}`,
    );
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.text();
  },
  diff: (runId: string) =>
    request<DiffResult>(`/api/v1/runs/${runId}/diff`),
  downloadUrl: (runId: string) =>
    `${API_BASE}/api/v1/runs/${runId}/download`,
  eventStreamUrl: (runId: string) =>
    `${API_BASE}/api/v1/runs/${runId}/events/stream`,
};
