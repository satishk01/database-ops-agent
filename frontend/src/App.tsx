import React, { useState, useRef, useEffect } from "react";
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

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [agentType, setAgentType] = useState<AgentType>("supervisor");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text?: string, overrideAgent?: AgentType) => {
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
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, agent_type: agent }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(err.detail || "Request failed");
      }

      const data = await res.json();
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.response,
        agentType: agent,
        toolsUsed: data.tools_used,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `⚠️ Error: ${err.message}`,
        agentType: agent,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
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
                  </div>
                  <div className="message-content">
                    {msg.role === "assistant" ? (
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
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

            {loading && (
              <div className="message assistant">
                <div className="message-avatar">
                  <Loader2 size={20} className="spin" />
                </div>
                <div className="message-body">
                  <div className="loading-indicator">
                    <span>Agent is analyzing</span>
                    <span className="dots">
                      <span>.</span><span>.</span><span>.</span>
                    </span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <div className="input-wrapper">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask the ${AGENT_INFO[agentType].label} agent...`}
                rows={1}
                disabled={loading}
              />
              <button
                className="send-btn"
                onClick={() => sendMessage()}
                disabled={!input.trim() || loading}
                aria-label="Send message"
              >
                {loading ? <Loader2 size={20} className="spin" /> : <Send size={20} />}
              </button>
            </div>
            <p className="input-hint">
              Press Enter to send · Shift+Enter for new line ·
              Active: <span style={{ color: AGENT_INFO[agentType].color }}>{AGENT_INFO[agentType].label}</span>
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
