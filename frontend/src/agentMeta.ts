export const ANALYSIS_AGENT_ORDER = [
  "main",
  "repository",
  "architecture",
  "test",
  "security",
  "quality",
  "report",
] as const;

export const CHAT_AGENT_ORDER = [
  "main",
  "intent",
  "conversation",
  "evidence_verifier",
] as const;

export const AGENT_LABELS: Record<string, string> = {
  main: "Main Agent",
  repository: "Repository Agent",
  architecture: "Architecture Agent",
  test: "Test Agent",
  security: "Security Agent",
  quality: "Quality Agent",
  report: "Report Agent",
  intent: "Intent Agent",
  conversation: "Conversation Agent",
  evidence_verifier: "Evidence Verifier",
};

export const AGENT_SHORT_LABELS: Record<string, string> = {
  main: "Main",
  repository: "Repository",
  architecture: "Architecture",
  test: "Test",
  security: "Security",
  quality: "Quality",
  report: "Report",
  intent: "Intent",
  conversation: "Conversation",
  evidence_verifier: "Verifier",
};
