export type RunStatus =
  | "pending"
  | "running"
  | "waiting_requirement"
  | "waiting_budget"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export interface Project {
  id: string;
  name: string;
  requirement: string;
  created_at: string;
  updated_at: string;
}

export interface AgentRun {
  id: string;
  project_id: string;
  status: RunStatus;
  current_agent: string | null;
  is_simulated: boolean;
  token_budget: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentEvent {
  id: number;
  run_id: string;
  sequence: number;
  event_type: string;
  agent: string;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface Artifact {
  id: string;
  run_id: string;
  kind: string;
  name: string;
  content_type: string;
  sha256: string;
  created_at: string;
}

export interface FileEntry {
  path: string;
  size: number;
}

export interface FileList {
  run_id: string;
  files: FileEntry[];
  file_count: number;
  total_size: number;
}

export interface DiffResult {
  run_id: string;
  additions: number;
  deletions: number;
  patch: string;
}

export interface HealthComponent {
  status: "ok" | "not_configured" | "error";
  detail: string | null;
}

export interface HealthResult {
  status: "ok" | "degraded";
  version: string;
  components: Record<string, HealthComponent>;
}
