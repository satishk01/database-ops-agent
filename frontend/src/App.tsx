import React, { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import {
  Database,
  Send,
  Activity,
  Shield,
  Bot,
  User,
  Loader2,
  Wrench,
  HeartPulse,
  Brain,
  Sparkles,
} from "lucide-react";
import "./App.css";

type AgentType = "healthcheck" | "action" | "supervisor";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  agentType: AgentType;
  toolsUsed?: string[];
  timestamp: Date;
  isStreaming?: boolean;
}

const AGENT_INFO: Record<AgentType, { label: string; icon: React.ReactNode; color: string; desc: string }> = {
  healthcheck: {
    label: "Health Check",
    icon: <HeartPulse size={18} />,
    color: "#34d399",
    desc: "Analyzes database performance, finds bloat, unused indexes, and slow queries",
  },
  action: {
    label: "Action",
    icon: <Wrench size={18} />,
    color: "#fbbf24",
    desc: "Implements safe optimizations: CREATE INDEX CONCURRENTLY, VACUUM, ANALYZE",
  },
  supervisor: {
    label: "Supervisor",
    icon: <Brain size={18} />,
    color: "#6c63ff",
    desc: "Full autonomous mode: diagnose issues AND implement safe fixes",
  },
};

const QUICK_PROMPTS = [
  { label: "Full Health Check", prompt: "Run a comprehensive Aurora database health check and provide recommendations", agent: "healthcheck" as AgentType },
  { label: "Find Unused Indexes", prompt: "Show me unused indexes that are wasting space", agent: "healthcheck" as AgentType },
  { label: "Top Slow Queries", prompt: "Show me the top slow queries with execution plans and suggest optimizations", agent: "healthcheck" as AgentType },
  { label: "Diagnose & Fix", prompt: "Review database activity including top queries, identify root cause of high CPU utilization, and implement safe fixes one at a time with minimal production impact", agent: "supervisor" as AgentType },
  { label: "Aurora Cluster Status", prompt: "List Aurora clusters and show instance details including replica lag, CPU, and connection metrics", agent: "healthcheck" as AgentType },
  { label: "Active Sessions", prompt: "Show me active sessions and wait events to identify what's blocking queries", agent: "healthcheck" as AgentType },
];

/** Parse SSE lines from a text chunk. Handles partial lines across chunks. */
function parseSSEChunk(text: string): Array<{ type: string; content?: string; tool?: string; final_response?: string; tools_used?: string[]; message?: string }> {
  const events: Array<any> = [];
  const lines = text.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("data: ")) {
      try {
        const payload = JSON.parse(trimmed.slice(6));
        events.push(payload);
      } catch {
        // partial JSON, skip
      }
    }
  }
  return events;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [agentType, setAgentType] = useState<AgentType>("supervisor");
  const [loading, setLoading] = useState(false);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text?: string, overrideAgent?: AgentType) => {
    const msg = text || input.trim();
    const agent = overrideAgent || agentType;
    if (!msg || loading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: msg,
      agentType: agent,
      timestamp: new Date(),
    };

    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      agentType: agent,
      toolsUsed: [],
      timestamp: new Date(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setLoading(true);
    setActiveTools([]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, agent_type: agent }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let streamedContent = "";
      const toolsList: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE lines
        const events = parseSSEChunk(buffer);
        // Keep only the last incomplete line in buffer
        const lastNewline = buffer.lastIndexOf("\n");
        buffer = lastNewline >= 0 ? buffer.slice(lastNewline + 1) : buffer;

        for (const evt of events) {
          if (evt.type === "text" && evt.content) {
            streamedContent += evt.content;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: streamedContent }
                  : m
              )
            );
          } else if (evt.type === "tool" && evt.tool) {
            if (!toolsList.includes(evt.tool)) {
              toolsList.push(evt.tool);
              setActiveTools([...toolsList]);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, toolsUsed: [...toolsList] }
                    : m
                )
              );
            }
          } else if (evt.type === "done") {
            // Use final_response if available (sanitized by guardrails)
            const finalContent = evt.final_response || streamedContent;
            const finalTools = evt.tools_used || toolsList;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: finalContent, toolsUsed: finalTools, isStreaming: false }
                  : m
              )
            );
          } else if (evt.type === "error") {
            const errContent = `⚠️ ${evt.content || evt.message || "Unknown error"}`;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: errContent, isStreaming: false }
                  : m
              )
            );
          }
        }
      }

      // If stream ended without a done event, finalize
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.isStreaming
            ? { ...m, isStreaming: false }
            : m
        )
      );
    } catch (err: any) {
      if (err.name === "AbortError") return;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `⚠️ Error: ${err.message}`, isStreaming: false }
            : m
        )
      );
    } finally {
      setLoading(false);
      setActiveTools([]);
      abortRef.current = null;
    }
  }, [input, agentType, loading]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setLoading(false);
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <Database size={28} className="header-icon" />
          <div>
            <h1>DataOps Agent</h1>
            <p>AI-Powered Database Operations</p>
          </div>
        </div>
        <div className="header-badges">
          <span className="badge badge-aws">
            <Sparkles size={14} /> Strands SDK
          </span>
          <span className="badge badge-bedrock">
            <Bot size={14} /> Amazon Bedrock
          </span>
          <span className="badge badge-safe">
            <Shield size={14} /> Guardrails Active
          </span>
        </div>
      </header>

      <div className="main-layout">
        <aside className="sidebar">
          <div className="agent-selector">
            <h3>Agent Mode</h3>
            {(Object.entries(AGENT_INFO) as [AgentType, typeof AGENT_INFO[AgentType]][]).map(
              ([key, info]) => (
                <button
                  key={key}
                  className={`agent-btn ${agentType === key ? "active" : ""}`}
                  onClick={() => setAgentType(key)}
                  style={{ "--agent-color": info.color } as React.CSSProperties}
                >
                  <span className="agent-btn-icon">{info.icon}</span>
                  <div className="agent-btn-text">
                    <span className="agent-btn-label">{info.label}</span>
                    <span className="agent-btn-desc">{info.desc}</span>
                  </div>
                </button>
              )
            )}
          </div>

          <div className="quick-prompts">
            <h3>Quick Actions</h3>
            {QUICK_PROMPTS.map((qp, i) => (
              <button
                key={i}
                className="quick-btn"
                onClick={() => {
                  setAgentType(qp.agent);
                  sendMessage(qp.prompt, qp.agent);
                }}
                disabled={loading}
              >
                <Activity size={14} />
                {qp.label}
              </button>
            ))}
          </div>
        </aside>

        <main className="chat-area">
          <div className="messages">
            {messages.length === 0 && (
              <div className="empty-state">
                <Database size={48} className="empty-icon" />
                <h2>Welcome to DataOps Agent</h2>
                <p>
                  Ask me to analyze your Aurora PostgreSQL cluster health, find
                  performance issues, check replica lag, or implement safe
                  optimizations. Pick an agent mode from the sidebar or use a
                  quick action to get started.
                </p>
                <div className="arch-diagram">
                  <div className="arch-node arch-supervisor">
                    <Brain size={20} /> Supervisor
                  </div>
                  <div className="arch-arrows">
                    <span>↙</span>
                    <span>↘</span>
                  </div>
                  <div className="arch-children">
                    <div className="arch-node arch-health">
                      <HeartPulse size={16} /> Health Check
                    </div>
                    <div className="arch-node arch-action">
                      <Wrench size={16} /> Action
                    </div>
                  </div>
                  <div className="arch-db">
                    <Database size={16} /> Aurora PostgreSQL
                  </div>
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className={`message ${msg.role}`}>
                <div className="message-avatar">
                  {msg.role === "user" ? (
                    <User size={20} />
                  ) : (
                    <span style={{ color: AGENT_INFO[msg.agentType].color }}>
                      {AGENT_INFO[msg.agentType].icon}
                    </span>
                  )}
                </div>
                <div className="message-body">
                  <div className="message-meta">
                    <span className="message-sender">
                      {msg.role === "user" ? "You" : AGENT_INFO[msg.agentType].label + " Agent"}
                    </span>
                    <span className="message-time">
                      {msg.timestamp.toLocaleTimeString()}
                    </span>
                    {msg.isStreaming && (
                      <span className="streaming-badge">streaming</span>
                    )}
                  </div>
                  <div className="message-content">
                    {msg.role === "assistant" ? (
                      msg.content ? (
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      ) : msg.isStreaming ? (
                        <span className="thinking">Thinking...</span>
                      ) : null
                    ) : (
                      <p>{msg.content}</p>
                    )}
                  </div>
                  {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                    <div className="tools-used">
                      <Wrench size={12} />
                      <span>Tools: {msg.toolsUsed.join(", ")}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <div className="input-wrapper">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask the ${AGENT_INFO[agentType].label} agent...`}
                rows={1}
                disabled={loading}
              />
              {loading ? (
                <button className="stop-btn" onClick={handleStop} aria-label="Stop">
                  <span className="stop-icon" />
                </button>
              ) : (
                <button
                  className="send-btn"
                  onClick={() => sendMessage()}
                  disabled={!input.trim()}
                  aria-label="Send message"
                >
                  <Send size={20} />
                </button>
              )}
            </div>
            <p className="input-hint">
              Press Enter to send · Shift+Enter for new line ·
              Active: <span style={{ color: AGENT_INFO[agentType].color }}>{AGENT_INFO[agentType].label}</span>
              {activeTools.length > 0 && (
                <span className="active-tool-hint"> · Using: {activeTools[activeTools.length - 1]}</span>
              )}
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
