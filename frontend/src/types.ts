export type AnalysisStatus =
  | "pending"
  | "cloning"
  | "analyzing"
  | "completed"
  | "failed"
  | "cancelled";

export type Severity = "critical" | "major" | "minor" | "info";
export type FindingCategory = "architecture" | "test" | "security" | "quality";

export interface Repository {
  id: string;
  url: string;
  name: string;
  branch: string | null;
  provider: string;
  latest_commit: string | null;
  created_at: string;
  updated_at: string;
}

export interface Analysis {
  id: string;
  repository_id: string;
  status: AnalysisStatus;
  current_agent: string | null;
  branch: string | null;
  commit_sha: string | null;
  summary: string | null;
  error_message: string | null;
  finding_count: number;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface RepositorySubmission {
  repository: Repository;
  analysis: Analysis;
}

export interface AnalysisEvent {
  id: number;
  analysis_id: string;
  sequence: number;
  event_type: string;
  agent: string;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface Finding {
  id: string;
  analysis_id: string;
  category: FindingCategory;
  severity: Severity;
  title: string;
  file_path: string | null;
  line: number | null;
  evidence: string;
  impact: string;
  recommendation: string;
  created_at: string;
}

export interface Artifact {
  id: string;
  analysis_id: string;
  kind: string;
  name: string;
  content_type: string;
  sha256: string;
  created_at: string;
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
