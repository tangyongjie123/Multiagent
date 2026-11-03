export const AGENT_ORDER = [
  "main",
  "repository",
  "architecture",
  "test",
  "security",
  "quality",
  "report",
] as const;

export const AGENT_LABELS: Record<string, string> = {
  main: "Main Agent",
  repository: "Repository Agent",
  architecture: "Architecture Agent",
  test: "Test Agent",
  security: "Security Agent",
  quality: "Quality Agent",
  report: "Report Agent",
};

export const AGENT_SHORT_LABELS: Record<string, string> = {
  main: "Main",
  repository: "Repository",
  architecture: "Architecture",
  test: "Test",
  security: "Security",
  quality: "Quality",
  report: "Report",
};
