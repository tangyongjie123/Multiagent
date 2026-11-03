import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AGENT_SHORT_LABELS } from "./agentMeta";
import { api } from "./api";
import type {
  Analysis,
  ChatCitation,
  ChatEvent,
  ChatMessage,
  ChatSession,
  Repository,
} from "./types";

const CHAT_STREAM_EVENTS = [
  "chat.turn.queued",
  "chat.turn.started",
  "chat.main.decision",
  "chat.agent.started",
  "chat.agent.completed",
  "chat.agent.failed",
  "chat.completed",
  "chat.failed",
];

const SUGGESTIONS = [
  {
    mark: "01",
    title: "找出最高风险",
    description: "按严重程度总结最值得优先处理的问题",
    prompt: "总结这个项目最严重的三个问题，并说明优先顺序",
  },
  {
    mark: "02",
    title: "解释安全证据",
    description: "定位凭证或危险调用，并解释证据含义",
    prompt: "解释第一条安全问题的证据，以及它可能造成的影响",
  },
  {
    mark: "03",
    title: "制定修复计划",
    description: "结合现有 Finding 生成分阶段修复步骤",
    prompt: "根据当前分析结果，按优先级生成修复计划",
  },
];

interface ChatWorkspaceProps {
  repository: Repository | null;
  analysis: Analysis | null;
  onClose: () => void;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function responsePreview(value: string): string {
  return value.length > 52 ? `${value.slice(0, 52)}…` : value;
}

export function ChatWorkspace({
  repository,
  analysis,
  onClose,
}: ChatWorkspaceProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [events, setEvents] = useState<ChatEvent[]>([]);
  const [citations, setCitations] = useState<Record<string, ChatCitation[]>>(
    {},
  );
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [eventCursor, setEventCursor] = useState(0);
  const [error, setError] = useState("");

  const canChat = Boolean(repository && analysis?.status === "completed");
  const latestEvent = events[events.length - 1];
  const activeSession =
    sessions.find((session) => session.id === activeSessionId) ?? null;

  async function loadSessions(): Promise<void> {
    if (!repository || !analysis) {
      setSessions([]);
      return;
    }
    const items = await api.chatSessions(repository.id);
    setSessions(
      items.filter(
        (session) =>
          session.analysis_id === analysis.id && session.status === "active",
      ),
    );
  }

  async function loadConversation(sessionId: string): Promise<void> {
    setActiveSessionId(sessionId);
    setMessages([]);
    setEvents([]);
    setCitations({});
    setError("");
    try {
      const [nextMessages, nextEvents] = await Promise.all([
        api.chatMessages(sessionId),
        api.chatEvents(sessionId),
      ]);
      const completed = nextMessages.filter(
        (message) =>
          message.role === "assistant" && message.status === "completed",
      );
      const entries = await Promise.all(
        completed.map(
          async (message) =>
            [message.id, await api.chatCitations(message.id)] as const,
        ),
      );
      setMessages(nextMessages);
      setEvents(nextEvents);
      setCitations(Object.fromEntries(entries));
      setEventCursor(nextEvents[nextEvents.length - 1]?.sequence ?? 0);
      setRunning(
        nextMessages.some(
          (message) =>
            message.role === "assistant" && message.status === "generating",
        ),
      );
    } catch (requestError) {
      setError(String(requestError));
    }
  }

  useEffect(() => {
    setActiveSessionId("");
    setMessages([]);
    setEvents([]);
    setCitations({});
    setInput("");
    setRunning(false);
    setEventCursor(0);
    setError("");
    if (!repository || !analysis) {
      setSessions([]);
      return;
    }
    let ignore = false;
    void api
      .chatSessions(repository.id)
      .then((items) => {
        if (ignore) return;
        setSessions(
          items.filter(
            (session) =>
              session.analysis_id === analysis.id &&
              session.status === "active",
          ),
        );
      })
      .catch((requestError) => {
        if (!ignore) setError(String(requestError));
      });
    return () => {
      ignore = true;
    };
  }, [repository?.id, analysis?.id]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (!activeSessionId || !running) return;
    const stream = new EventSource(
      api.chatEventStreamUrl(activeSessionId, eventCursor),
    );

    const refresh = async () => {
      const nextMessages = await api.chatMessages(activeSessionId);
      setMessages(nextMessages);
      const completed = nextMessages.filter(
        (message) =>
          message.role === "assistant" && message.status === "completed",
      );
      const entries = await Promise.all(
        completed.map(
          async (message) =>
            [message.id, await api.chatCitations(message.id)] as const,
        ),
      );
      setCitations(Object.fromEntries(entries));
    };

    const onEvent = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as ChatEvent;
      setEvents((current) =>
        current.some((item) => item.id === event.id)
          ? current
          : [...current, event].sort((a, b) => a.sequence - b.sequence),
      );
      void refresh();
      if (["chat.completed", "chat.failed"].includes(event.event_type)) {
        setRunning(false);
        setEventCursor(event.sequence);
        stream.close();
        void loadSessions();
      }
    };

    for (const eventName of CHAT_STREAM_EVENTS) {
      stream.addEventListener(eventName, onEvent as EventListener);
    }
    return () => {
      for (const eventName of CHAT_STREAM_EVENTS) {
        stream.removeEventListener(eventName, onEvent as EventListener);
      }
      stream.close();
    };
  }, [activeSessionId, eventCursor, running]);

  function startNewConversation(): void {
    if (running) return;
    setActiveSessionId("");
    setMessages([]);
    setEvents([]);
    setCitations({});
    setInput("");
    setEventCursor(0);
    setError("");
  }

  async function sendMessage(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    const content = input.trim();
    if (!content || running) return;
    if (!repository || analysis?.status !== "completed") {
      setError("请先完成一次仓库分析，再向 AI 助手提问。");
      return;
    }

    setRunning(true);
    setError("");
    setEventCursor(events[events.length - 1]?.sequence ?? 0);
    setInput("");
    try {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const session = await api.createChatSession(
          repository.id,
          analysis.id,
          responsePreview(content),
        );
        sessionId = session.id;
        setActiveSessionId(sessionId);
        setEvents([]);
        setSessions((current) => [
          session,
          ...current.filter((item) => item.id !== session.id),
        ]);
      }
      const turn = await api.sendChatMessage(sessionId, content);
      setMessages((current) => [
        ...current,
        turn.user_message,
        turn.assistant_message,
      ]);
    } catch (requestError) {
      setInput(content);
      setRunning(false);
      setError(String(requestError));
    }
  }

  return (
    <section className="chat-workspace">
      <aside className="chat-sidebar">
        <div className="chat-sidebar-brand">
          <span className="assistant-orb">RG</span>
          <div>
            <strong>RepoGraph AI</strong>
            <small>证据驱动的代码助手</small>
          </div>
        </div>

        <button
          className="new-chat-button"
          disabled={running}
          onClick={startNewConversation}
          type="button"
        >
          <span>＋</span>
          开启新对话
        </button>

        <div className="chat-context-card">
          <span>当前分析上下文</span>
          <strong>{repository ? repository.name : "尚未选择仓库"}</strong>
          <p>
            {analysis?.status === "completed"
              ? `${analysis.finding_count} 条 Finding · ${analysis.commit_sha?.slice(0, 8) ?? "未知 Commit"}`
              : "完成仓库分析后即可开始证据问答"}
          </p>
        </div>

        <div className="chat-history-heading">
          <span>最近对话</span>
          <b>{sessions.length.toString().padStart(2, "0")}</b>
        </div>
        <div className="chat-history-list">
          {sessions.map((session) => (
            <button
              className={session.id === activeSessionId ? "active" : ""}
              key={session.id}
              onClick={() => void loadConversation(session.id)}
              type="button"
            >
              <span>{session.title}</span>
              <small>
                {formatTime(session.last_message_at ?? session.created_at)}
              </small>
            </button>
          ))}
          {sessions.length === 0 && (
            <p className="chat-history-empty">
              提问后会在这里保存当前分析的对话。
            </p>
          )}
        </div>

        <button className="back-to-review" onClick={onClose} type="button">
          ← 返回审查工作台
        </button>
      </aside>

      <section className="chat-main">
        <header className="chat-main-header">
          <div>
            <span>AI ASSISTANT</span>
            <strong>{activeSession?.title ?? "当前仓库证据问答"}</strong>
          </div>
          <div className="chat-model-chip">
            <i />
            基于 Finding · 不执行目标代码
          </div>
        </header>

        <div className="chat-conversation">
          {!canChat ? (
            <div className="chat-unavailable">
              <span>WAITING FOR ANALYSIS</span>
              <h2>先完成仓库分析</h2>
              <p>
                AI 助手只基于已生成的分析 Finding
                回答，不会执行目标仓库中的代码。
              </p>
              <button
                className="outline-button"
                onClick={onClose}
                type="button"
              >
                返回审查工作台
              </button>
            </div>
          ) : messages.length === 0 ? (
            <div className="chat-welcome">
              <span className="welcome-mark">✦</span>
              <p>EVIDENCE-BASED ASSISTANT</p>
              <h1>你好，从这次分析开始提问吧</h1>
              <p className="welcome-copy">
                我会结合 {repository?.name} 的 {analysis?.finding_count ?? 0}{" "}
                条分析证据， 帮你定位风险、解释问题并整理修复步骤。
              </p>
              <div className="chat-suggestion-grid">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.mark}
                    onClick={() => setInput(suggestion.prompt)}
                    type="button"
                  >
                    <span>{suggestion.mark}</span>
                    <strong>{suggestion.title}</strong>
                    <small>{suggestion.description}</small>
                    <i>↗</i>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="chat-thread">
              {messages.map((message) => (
                <article
                  className={`chat-turn ${message.role} ${message.status}`}
                  key={message.id}
                >
                  <span className="chat-avatar">
                    {message.role === "user" ? "你" : "RG"}
                  </span>
                  <div className="chat-turn-body">
                    <div className="chat-turn-meta">
                      <strong>
                        {message.role === "user" ? "你" : "RepoGraph AI"}
                      </strong>
                      <span>
                        {message.status === "generating"
                          ? "正在分析证据"
                          : formatTime(message.created_at)}
                      </span>
                    </div>
                    <div className="chat-turn-content">
                      {message.status === "generating" ? (
                        "正在检索分析证据并组织回答…"
                      ) : message.role === "user" ? (
                        message.content
                      ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.content}
                        </ReactMarkdown>
                      )}
                    </div>
                    {message.role === "assistant" &&
                      citations[message.id]?.length > 0 && (
                        <details className="chat-evidence">
                          <summary>
                            <span>引用证据</span>
                            <b>{citations[message.id].length}</b>
                            <i>查看来源</i>
                          </summary>
                          <div>
                            {citations[message.id].map((citation) => (
                              <article key={citation.id}>
                                <code>
                                  {citation.file_path ?? "项目级"}
                                  {citation.line ? `:${citation.line}` : ""}
                                </code>
                                <p>{citation.excerpt}</p>
                              </article>
                            ))}
                          </div>
                        </details>
                      )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div className="chat-inline-error">
            <strong>请求失败</strong>
            <span>{error}</span>
            <button onClick={() => setError("")} type="button">
              ×
            </button>
          </div>
        )}

        {running && latestEvent && (
          <div className="chat-agent-status">
            <i />
            <strong>
              {AGENT_SHORT_LABELS[latestEvent.agent] ?? latestEvent.agent}
            </strong>
            <span>{latestEvent.message}</span>
          </div>
        )}

        <form className="chat-composer" onSubmit={sendMessage}>
          <textarea
            aria-label="向 RepoGraph AI 提问"
            disabled={!canChat || running}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={
              canChat
                ? "给 RepoGraph AI 发送消息，例如：这个项目最严重的问题是什么？"
                : "请先完成仓库分析"
            }
            rows={3}
            value={input}
          />
          <div className="chat-composer-footer">
            <div>
              <span>⌘ 当前分析</span>
              <span>◈ 证据引用</span>
            </div>
            <button
              aria-label="发送"
              disabled={!canChat || running || !input.trim()}
              type="submit"
            >
              ↑
            </button>
          </div>
        </form>
      </section>
    </section>
  );
}
