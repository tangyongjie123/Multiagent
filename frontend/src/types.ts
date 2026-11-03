export type AnalysisStatus =
  | "pending"
  | "cloning"
  | "analyzing"
  | "completed"
  | "failed"
  | "cancelled";

export type Severity = "critical" | "major" | "minor" | "info";
export type FindingCategory = "architecture" | "test" | "security" | "quality";

/** 用户提交分析的 Git 仓库。 */
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

/** 一次完整的仓库分析运行。 */
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

/** 创建仓库后自动启动首次分析的响应。 */
export interface RepositorySubmission {
  repository: Repository;
  analysis: Analysis;
}

/** SSE 与历史接口返回的持久化 Agent/工具事件。 */
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

/** 可定位、可排序的代码审查问题。 */
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

/** 报告、图表或中间 JSON 产物的元数据。 */
export interface Artifact {
  id: string;
  analysis_id: string;
  kind: string;
  name: string;
  content_type: string;
  sha256: string;
  created_at: string;
}

export type ChatMessageRole = "user" | "assistant";
export type ChatMessageStatus =
  | "recorded"
  | "generating"
  | "completed"
  | "failed";

/** 一个绑定仓库和可选分析结果的聊天会话。 */
export interface ChatSession {
  id: string;
  repository_id: string;
  analysis_id: string | null;
  title: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}

/** 聊天中的用户或助手消息。 */
export interface ChatMessage {
  id: string;
  session_id: string;
  role: ChatMessageRole;
  content: string;
  status: ChatMessageStatus;
  model_name: string | null;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
}

/** 助手回答引用的代码审查证据。 */
export interface ChatCitation {
  id: string;
  message_id: string;
  finding_id: string | null;
  source_type: string;
  file_path: string | null;
  line: number | null;
  excerpt: string;
  created_at: string;
}

/** 聊天主 Agent 和专业 Agent 的执行事件。 */
export interface ChatEvent {
  id: number;
  session_id: string;
  sequence: number;
  event_type: string;
  agent: string;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface ChatTurn {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

/** 单个依赖服务的健康状态。 */
export interface HealthComponent {
  status: "ok" | "not_configured" | "error";
  detail: string | null;
}

/** FastAPI 汇总的依赖服务健康状态。 */
export interface HealthResult {
  status: "ok" | "degraded";
  version: string;
  components: Record<string, HealthComponent>;
}
