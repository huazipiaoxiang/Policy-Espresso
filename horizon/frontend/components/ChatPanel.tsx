"use client";

import { useState, useRef, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";

interface Citation {
  id: string;
  type: "policy" | "document" | "web_source";
  title: string;
  url?: string;
  policy_id?: string | null;
  document_id?: string | null;
  source_id?: string | null;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  noAnswer?: boolean;
}

interface ChatPanelProps {
  onClose: () => void;
}

function safeCitationUrl(url?: string): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export default function ChatPanel({ onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "你好！我是 HORIZON 政策雷达助手。我会基于当前政策库回答，并附上可核查的来源。" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, error]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMsg: Message = { role: "user", content: input.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setError("");
    setLoading(true);

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
      };
      const demoRole = window.localStorage.getItem("horizon-demo-role");
      if (demoRole) headers["X-Demo-Role"] = demoRole;

      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          // Keep the mounted conversation intact, but bound outbound history.
          messages: newMessages.slice(-3).map(({ role, content }) => ({
            role,
            content: role === "assistant" ? content.slice(0, 1000) : content,
          })),
        }),
      });

      if (!res.ok) {
        throw new Error(`Chat request failed: ${res.status}`);
      }
      const data = await res.json();
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content: data.reply,
          citations: Array.isArray(data.citations) ? data.citations : [],
          noAnswer: Boolean(data.no_answer),
        },
      ]);
    } catch {
      setError("暂时无法连接政策助手，请稍后重试。你的对话已保留。");
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
    <div className="fixed bottom-24 right-6 z-50 flex h-[500px] w-[min(380px,calc(100vw-3rem))] flex-col rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--accent)]">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <span className="text-[14px] font-medium">AI 政策助手</span>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭 AI 助手" className="text-[var(--text-3)] hover:text-[var(--text)]">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-[13px] ${
                msg.role === "user"
                  ? "bg-[var(--accent)] text-white"
                  : "bg-[var(--surface-2)] text-[var(--text)]"
              }`}
            >
              {msg.noAnswer && (
                <div className="mb-1 text-[11px] font-medium text-[var(--text-3)]">未找到可靠依据</div>
              )}
              <div className="whitespace-pre-wrap">{msg.content}</div>
              {!!msg.citations?.length && (
                <div className="mt-2 border-t border-[var(--border)] pt-2">
                  <div className="mb-1 text-[11px] font-medium text-[var(--text-3)]">依据与来源</div>
                  <ul className="space-y-1">
                    {msg.citations.map((citation, citationIndex) => {
                      const href = safeCitationUrl(citation.url);
                      return (
                        <li key={`${citation.id}-${citationIndex}`} className="text-[12px] leading-5">
                          <span className="mr-1 text-[var(--text-3)]">[{citationIndex + 1}]</span>
                          {href ? (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="break-words text-[var(--accent)] underline decoration-transparent underline-offset-2 hover:decoration-current"
                            >
                              {citation.title}
                            </a>
                          ) : (
                            <span>{citation.title}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start" role="status">
            <div className="rounded-lg bg-[var(--surface-2)] px-3 py-2 text-[13px] text-[var(--text-3)]">
              正在检索当前政策库...
            </div>
          </div>
        )}
        {error && (
          <div role="alert" className="rounded-lg border border-[var(--accent)]/30 bg-[var(--surface-2)] px-3 py-2 text-[12px] text-[var(--text)]">
            {error}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-[var(--border)] p-3">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题..."
            aria-label="向政策助手提问"
            maxLength={4000}
            rows={2}
            className="flex-1 resize-none rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[13px] text-[var(--text)] placeholder-[var(--text-3)] focus:border-[var(--accent)] focus:outline-none"
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="self-end rounded-lg bg-[var(--accent)] px-3 py-2 text-[13px] text-white transition hover:bg-[var(--accent)]/90 disabled:opacity-50"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
