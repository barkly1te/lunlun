"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

import { MarkdownRenderer } from "./markdown-renderer";

import type { ChatMessage, StreamEvent } from "../lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const STORAGE_KEY = "agentscope.workspace.chat_state";
const LOCAL_CONTEXT_TOKEN_LIMIT = 600_000;
const LOCAL_CONTEXT_KEEP_RECENT = 12;

const QUICK_PROMPTS = [
  "请按 ACM/ICML 的审美标准，判断这个研究想法是否有顶刊感。",
  "请从顶会审稿人视角判断这段摘要是强方案，还是 AI 味很重的平庸方案。",
  "请结合 paper-aesthetic-critic、peer-review 和 venue-templates，评价这个论文方案该保留还是重写。",
];

const NAV_ITEMS = [
  {
    id: "chat",
    label: "Chat",
    description: "直接开始对话",
  },
  {
    id: "control",
    label: "Control",
    description: "查看 Token、会话与状态",
  },
  {
    id: "agent",
    label: "Agent",
    description: "查看论文品味工作流",
  },
  {
    id: "settings",
    label: "Settings",
    description: "查看本地配置与恢复策略",
  },
] as const;

type WorkbenchSection = (typeof NAV_ITEMS)[number]["id"];

interface PersistedChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  draft: string;
  savedAt: string;
}

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function estimateTokens(text: string) {
  return Math.ceil(Array.from(text).length / 4);
}

function estimateMessageTokens(messages: ChatMessage[]) {
  return messages.reduce(
    (total, message) =>
      total +
      estimateTokens(message.content ?? "") +
      estimateTokens(message.thinking ?? ""),
    0,
  );
}

function buildLocalSummaryMessage(messages: ChatMessage[]): ChatMessage {
  const summaryLines = messages
    .filter((message) => !message.id.startsWith("local-summary-"))
    .slice(-18)
    .map((message) => {
      const roleLabel = message.role === "user" ? "用户" : "助手";
      const body = message.content.replace(/\s+/g, " ").trim().slice(0, 120);
      return `- ${roleLabel}: ${body || "（空）"}`;
    });

  return {
    id: `local-summary-${Date.now()}`,
    role: "assistant",
    content: [
      "[本地上下文压缩摘要]",
      "本地存储中的较早上下文已被压缩，以下是用于刷新恢复的精简摘录：",
      ...(summaryLines.length ? summaryLines : ["- 暂无可压缩内容"]),
    ].join("\n"),
    state: "done",
  };
}

function compressMessagesForStorage(messages: ChatMessage[]) {
  if (estimateMessageTokens(messages) <= LOCAL_CONTEXT_TOKEN_LIMIT) {
    return messages;
  }

  if (messages.length <= LOCAL_CONTEXT_KEEP_RECENT) {
    return messages;
  }

  const recentMessages = messages.slice(-LOCAL_CONTEXT_KEEP_RECENT);
  const olderMessages = messages.slice(0, -LOCAL_CONTEXT_KEEP_RECENT);
  return [buildLocalSummaryMessage(olderMessages), ...recentMessages];
}

function formatSavedAt(value: string | null) {
  if (!value) {
    return "未写入";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", {
    hour12: false,
  });
}

export function ChatWorkbench() {
  const [activeSection, setActiveSection] = useState<WorkbenchSection>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [statusText, setStatusText] = useState("等待发送第一条消息。");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [backendSessionCount, setBackendSessionCount] = useState<number | null>(
    null,
  );
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const activeAssistantIdRef = useRef<string | null>(null);
  const finalAssistantTextRef = useRef<string>("");
  const streamDoneRef = useRef(false);
  const errorRef = useRef<string | null>(null);
  const renderQueueRef = useRef<string[]>([]);
  const renderFrameRef = useRef<number | null>(null);
  const storageReadyRef = useRef(false);

  const localTokenEstimate = estimateMessageTokens(messages);
  const shortSessionId = sessionId ? sessionId.slice(0, 8) : "未建立";
  const storageStatus = sessionId || messages.length || input.trim() ? "已启用" : "空";
  const runtimeStatus = errorText ? "异常" : isStreaming ? "处理中" : "就绪";
  const runtimeTone = errorText ? "error" : isStreaming ? "streaming" : "idle";

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }
    element.scrollTop = element.scrollHeight;
  }, [messages, statusText, activeSection]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (renderFrameRef.current !== null) {
        window.cancelAnimationFrame(renderFrameRef.current);
      }
    };
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        storageReadyRef.current = true;
        return;
      }

      const snapshot = JSON.parse(raw) as PersistedChatState;
      setMessages(Array.isArray(snapshot.messages) ? snapshot.messages : []);
      setSessionId(snapshot.sessionId ?? null);
      setInput(snapshot.draft ?? "");
      setLastSavedAt(snapshot.savedAt ?? null);
      if (snapshot.sessionId || snapshot.messages?.length) {
        setStatusText("已从本地恢复会话上下文。");
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    } finally {
      storageReadyRef.current = true;
    }
  }, []);

  useEffect(() => {
    if (!storageReadyRef.current) {
      return;
    }

    if (!sessionId && messages.length === 0 && !input.trim()) {
      window.localStorage.removeItem(STORAGE_KEY);
      setLastSavedAt(null);
      return;
    }

    const savedAt = new Date().toISOString();
    const snapshot: PersistedChatState = {
      sessionId,
      messages: compressMessagesForStorage(messages),
      draft: input,
      savedAt,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    setLastSavedAt(savedAt);
  }, [input, messages, sessionId]);

  const refreshHealth = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/health`);
      if (!response.ok) {
        return;
      }

      const data = (await response.json()) as { sessions?: number };
      if (typeof data.sessions === "number") {
        setBackendSessionCount(data.sessions);
      }
    } catch {
      setBackendSessionCount(null);
    }
  };

  useEffect(() => {
    void refreshHealth();
  }, [sessionId]);

  const updateAssistantMessage = (
    updater: (message: ChatMessage) => ChatMessage,
  ) => {
    const assistantId = activeAssistantIdRef.current;
    if (!assistantId) {
      return;
    }

    setMessages((current) =>
      current.map((message) =>
        message.id === assistantId ? updater(message) : message,
      ),
    );
  };

  const completeAssistantMessage = (state: ChatMessage["state"]) => {
    const assistantId = activeAssistantIdRef.current;
    if (!assistantId) {
      setIsStreaming(false);
      return;
    }

    setMessages((current) =>
      current.map((message) => {
        if (message.id !== assistantId) {
          return message;
        }

        const finalText = finalAssistantTextRef.current;
        return {
          ...message,
          content:
            finalText.length >= message.content.length ? finalText : message.content,
          state,
        };
      }),
    );

    activeAssistantIdRef.current = null;
    finalAssistantTextRef.current = "";
    streamDoneRef.current = false;
    if (state === "done") {
      setStatusText("回答已完成。");
    }
    setIsStreaming(false);
  };

  const scheduleCharacterFlush = () => {
    if (renderFrameRef.current !== null) {
      return;
    }

    const flush = () => {
      const assistantId = activeAssistantIdRef.current;
      if (!assistantId) {
        renderQueueRef.current = [];
        renderFrameRef.current = null;
        return;
      }

      const chunkSize =
        renderQueueRef.current.length > 220
          ? 4
          : renderQueueRef.current.length > 120
            ? 2
            : 1;
      const chunk = renderQueueRef.current.splice(0, chunkSize).join("");

      if (chunk) {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: message.content + chunk,
                  state: "streaming",
                }
              : message,
          ),
        );
      }

      if (renderQueueRef.current.length > 0) {
        renderFrameRef.current = window.requestAnimationFrame(flush);
        return;
      }

      renderFrameRef.current = null;
      if (streamDoneRef.current) {
        completeAssistantMessage(errorRef.current ? "error" : "done");
      }
    };

    renderFrameRef.current = window.requestAnimationFrame(flush);
  };

  const enqueueAssistantDelta = (delta: string) => {
    if (!delta) {
      return;
    }
    renderQueueRef.current.push(...Array.from(delta));
    scheduleCharacterFlush();
  };

  const appendThinkingDelta = (delta: string) => {
    if (!delta) {
      return;
    }

    updateAssistantMessage((message) => ({
      ...message,
      thinking: `${message.thinking ?? ""}${delta}`,
    }));
  };

  const resetConversation = async () => {
    abortRef.current?.abort();
    if (sessionId) {
      void fetch(`${API_BASE_URL}/api/sessions/${sessionId}`, {
        method: "DELETE",
      }).catch(() => undefined);
    }

    if (renderFrameRef.current !== null) {
      window.cancelAnimationFrame(renderFrameRef.current);
      renderFrameRef.current = null;
    }

    renderQueueRef.current = [];
    activeAssistantIdRef.current = null;
    finalAssistantTextRef.current = "";
    streamDoneRef.current = false;
    errorRef.current = null;
    abortRef.current = null;
    setMessages([]);
    setSessionId(null);
    setInput("");
    setErrorText(null);
    setStatusText("会话已重置。");
    setIsStreaming(false);
    setLastSavedAt(null);
    window.localStorage.removeItem(STORAGE_KEY);
    void refreshHealth();
  };

  const handleStreamEvent = (event: StreamEvent) => {
    switch (event.type) {
      case "session":
        if (event.session_id) {
          setSessionId(event.session_id);
          void refreshHealth();
        }
        return;
      case "status":
        setStatusText(event.message ?? "正在处理请求。");
        return;
      case "assistant_delta":
        enqueueAssistantDelta(event.delta ?? "");
        return;
      case "thinking_delta":
        appendThinkingDelta(event.delta ?? "");
        return;
      case "final":
        finalAssistantTextRef.current = event.message ?? "";
        return;
      case "error":
        errorRef.current = event.message ?? "发生未知错误。";
        setErrorText(errorRef.current);
        setStatusText(errorRef.current);
        streamDoneRef.current = true;
        if (!renderQueueRef.current.length && renderFrameRef.current === null) {
          completeAssistantMessage("error");
        }
        return;
      case "done":
        streamDoneRef.current = true;
        if (!renderQueueRef.current.length && renderFrameRef.current === null) {
          completeAssistantMessage(errorRef.current ? "error" : "done");
        }
        return;
      default:
        return;
    }
  };

  const submitMessage = async (message: string) => {
    const prompt = message.trim();
    if (!prompt || isStreaming) {
      return;
    }

    errorRef.current = null;
    setErrorText(null);
    setStatusText("正在连接后端流式接口。");
    setIsStreaming(true);
    streamDoneRef.current = false;
    finalAssistantTextRef.current = "";
    renderQueueRef.current = [];

    const userMessage: ChatMessage = {
      id: createId("user"),
      role: "user",
      content: prompt,
      state: "done",
    };
    const assistantMessage: ChatMessage = {
      id: createId("assistant"),
      role: "assistant",
      content: "",
      thinking: "",
      state: "streaming",
    };

    activeAssistantIdRef.current = assistantMessage.id;
    setMessages((current) => [...current, userMessage, assistantMessage]);
    setInput("");
    setActiveSection("chat");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: prompt,
          session_id: sessionId,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`后端响应异常 (${response.status})`);
      }

      if (!response.body) {
        throw new Error("后端没有返回可读取的流。");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        while (true) {
          const newlineIndex = buffer.indexOf("\n");
          if (newlineIndex === -1) {
            break;
          }

          const line = buffer.slice(0, newlineIndex).trim();
          buffer = buffer.slice(newlineIndex + 1);
          if (!line) {
            continue;
          }

          handleStreamEvent(JSON.parse(line) as StreamEvent);
        }
      }

      const tail = buffer.trim();
      if (tail) {
        handleStreamEvent(JSON.parse(tail) as StreamEvent);
      }
    } catch (error) {
      const messageText =
        error instanceof Error ? error.message : "前端读取流式响应失败。";
      errorRef.current = messageText;
      setErrorText(messageText);
      setStatusText(messageText);
      streamDoneRef.current = true;
      finalAssistantTextRef.current ||= messageText;
      if (!renderQueueRef.current.length && renderFrameRef.current === null) {
        completeAssistantMessage("error");
      }
    } finally {
      abortRef.current = null;
      if (!streamDoneRef.current) {
        streamDoneRef.current = true;
        if (!renderQueueRef.current.length && renderFrameRef.current === null) {
          completeAssistantMessage(errorRef.current ? "error" : "done");
        }
      }
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await submitMessage(input);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage(input);
    }
  };

  const jumpWithPrompt = (prompt: string) => {
    setActiveSection("chat");
    setInput(prompt);
  };

  const renderChatView = () => (
    <section className="panel-surface panel-chat">
      <header className="panel-header">
        <div>
          <span className="panel-kicker">Chat</span>
          <h1 className="panel-title">进入即对话</h1>
          <p className="panel-copy">
            进入页面后直接对论文题目、摘要、研究方案、图表叙事或投稿定位做审美判断；后台模块放在左侧切换。
          </p>
        </div>
        <div className="panel-side">
          <span className={`live-chip ${runtimeTone}`}>{runtimeStatus}</span>
          <div className="session-badge">
            <span>Session</span>
            <strong>{shortSessionId}</strong>
          </div>
        </div>
      </header>

      <div className="summary-strip">
        <button
          className="summary-item"
          type="button"
          onClick={() => setActiveSection("control")}
        >
          <span>Token</span>
          <strong>{localTokenEstimate.toLocaleString()}</strong>
        </button>
        <button
          className="summary-item"
          type="button"
          onClick={() => setActiveSection("control")}
        >
          <span>Messages</span>
          <strong>{messages.length}</strong>
        </button>
        <button
          className="summary-item"
          type="button"
          onClick={() => setActiveSection("control")}
        >
          <span>Sessions</span>
          <strong>{backendSessionCount === null ? "--" : backendSessionCount}</strong>
        </button>
        <button
          className="summary-item"
          type="button"
          onClick={() => setActiveSection("settings")}
        >
          <span>Storage</span>
          <strong>{storageStatus}</strong>
        </button>
      </div>

      <div ref={scrollRef} className="chat-log">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-card">
              <h2>直接输入任务，工作台会立刻开始流式对话。</h2>
              <p>
                聊天是默认入口。Control、Agent、Settings 都从左侧菜单进入，不再把后台信息堆在首页。
              </p>
              <div className="quick-prompts">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    className="quick-button"
                    type="button"
                    onClick={() => jumpWithPrompt(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div key={message.id} className={`message-row ${message.role}`}>
              <div className="message-bubble">
                <div className="message-content">
                  <MarkdownRenderer
                    content={message.content || ""}
                    className="message-markdown"
                  />
                  {message.role === "assistant" && message.state === "streaming" ? (
                    <span className="typing-cursor" aria-hidden="true" />
                  ) : null}
                </div>
                {message.role === "assistant" && message.thinking?.trim() ? (
                  <details className="message-process">
                    <summary>查看过程记录</summary>
                    <div className="message-process-content">{message.thinking}</div>
                  </details>
                ) : null}
                <div className="message-meta">
                  <span>{message.role === "user" ? "你" : "论论"}</span>
                  {message.role === "assistant" && message.thinking?.trim() ? (
                    <span className="message-process-flag">含过程记录</span>
                  ) : null}
                  <span className={`message-status ${message.state}`}>
                    {message.state === "streaming"
                      ? "流式输出中"
                      : message.state === "error"
                        ? "输出失败"
                        : "已完成"}
                  </span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <form className="composer" onSubmit={handleSubmit}>
        <div className="status-line">
          <span className={`status-pill ${runtimeTone}`}>
            {errorText ? errorText : statusText}
          </span>
          <span>{isStreaming ? "流式连接中" : "空闲"}</span>
        </div>

        <div className="composer-box">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入要交给智能体的任务。Enter 发送，Shift+Enter 换行。"
            disabled={isStreaming}
          />
          <div className="composer-actions">
            <button
              className="primary-button"
              type="submit"
              disabled={isStreaming || !input.trim()}
            >
              {isStreaming ? "生成中..." : "发送消息"}
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => void resetConversation()}
              disabled={!messages.length && !sessionId && !isStreaming}
            >
              重置会话
            </button>
          </div>
        </div>
      </form>
    </section>
  );

  const renderControlView = () => (
    <section className="panel-surface">
      <header className="panel-header">
        <div>
          <span className="panel-kicker">Control</span>
          <h1 className="panel-title">运行观测</h1>
          <p className="panel-copy">
            Token 检测、会话计数、本地恢复和接口状态都集中放在这里，主聊天区保持干净。
          </p>
        </div>
        <div className="panel-side compact">
          <button className="ghost-button" type="button" onClick={() => void refreshHealth()}>
            刷新状态
          </button>
        </div>
      </header>

      <div className="module-grid metrics-grid">
        <article className="module-card metric-card accent-card">
          <span className="module-label">本地上下文 Token</span>
          <strong className="module-value">{localTokenEstimate.toLocaleString()}</strong>
          <p className="module-note">按字符估算，用于本地恢复和压缩阈值判断。</p>
        </article>
        <article className="module-card metric-card">
          <span className="module-label">消息数</span>
          <strong className="module-value">{messages.length}</strong>
          <p className="module-note">当前浏览器中保留的对话条目数量。</p>
        </article>
        <article className="module-card metric-card">
          <span className="module-label">后端会话数</span>
          <strong className="module-value">
            {backendSessionCount === null ? "--" : backendSessionCount}
          </strong>
          <p className="module-note">服务端内存中的活跃会话数量。</p>
        </article>
        <article className="module-card metric-card">
          <span className="module-label">本地存储</span>
          <strong className="module-value">{storageStatus}</strong>
          <p className="module-note">刷新后自动恢复 session、消息和输入草稿。</p>
        </article>
      </div>

      <div className="module-grid detail-grid">
        <article className="module-card wide-card">
          <h2>会话控制</h2>
          <div className="detail-list">
            <div>
              <span>当前 Session</span>
              <strong>{shortSessionId}</strong>
            </div>
            <div>
              <span>运行状态</span>
              <strong>{runtimeStatus}</strong>
            </div>
            <div>
              <span>最近保存</span>
              <strong>{formatSavedAt(lastSavedAt)}</strong>
            </div>
          </div>
          <div className="module-actions">
            <button className="primary-button" type="button" onClick={() => setActiveSection("chat")}>
              返回聊天
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => void resetConversation()}
              disabled={!messages.length && !sessionId && !isStreaming}
            >
              重置会话
            </button>
          </div>
        </article>

        <article className="module-card wide-card">
          <h2>后台链路</h2>
          <div className="detail-list muted-detail-list">
            <div>
              <span>流式协议</span>
              <strong>NDJSON</strong>
            </div>
            <div>
              <span>接口地址</span>
              <strong className="inline-code">{API_BASE_URL}</strong>
            </div>
            <div>
              <span>状态文案</span>
              <strong>{statusText}</strong>
            </div>
          </div>
          <p className="module-note standalone-note">
            聊天区只负责对话，观测信息集中到 Control，和 OpenClaw 那种“左侧导航 + 主工作区”的结构一致。
          </p>
        </article>
      </div>
    </section>
  );

  const renderAgentView = () => (
    <section className="panel-surface">
      <header className="panel-header">
        <div>
          <span className="panel-kicker">Agent</span>
          <h1 className="panel-title">智能体工作方式</h1>
          <p className="panel-copy">
            这里不做参数堆砌，而是解释当前工作台里的 Agent 怎么响应、怎么保留上下文、怎么调用本地能力。
          </p>
        </div>
      </header>

      <div className="module-grid info-grid">
        <article className="module-card">
          <h2>流式回答</h2>
          <p className="module-note">
            前端直接消费后端的 NDJSON 流，把增量拆成字符队列逐步输出，而不是等整段文本返回后再一次性渲染。
          </p>
        </article>
        <article className="module-card">
          <h2>会话持续</h2>
          <p className="module-note">
            `sessionId` 和消息历史保存在浏览器本地，刷新页面后会自动恢复；真正的模型上下文仍以后端会话为准。
          </p>
        </article>
        <article className="module-card">
          <h2>本地技能</h2>
          <p className="module-note">
            当前工作区下的 `skills/*/SKILL.md` 会被模型发现并调用，用于代码分析、文档处理和其他项目内任务。
          </p>
        </article>
        <article className="module-card">
          <h2>长期记忆</h2>
          <p className="module-note">
            持久信息会保存在 `memory/MEMORY.md`，适合记录稳定约束、偏好和长期目标，而不是临时推理过程。
          </p>
        </article>
      </div>

      <article className="module-card wide-card">
        <h2>快速任务入口</h2>
        <p className="module-note standalone-note">
          这些快捷任务会直接把你带回 Chat，并把提示词填进输入框。
        </p>
        <div className="quick-prompts">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              className="quick-button"
              type="button"
              onClick={() => jumpWithPrompt(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
      </article>
    </section>
  );

  const renderSettingsView = () => (
    <section className="panel-surface">
      <header className="panel-header">
        <div>
          <span className="panel-kicker">Settings</span>
          <h1 className="panel-title">本地设置</h1>
          <p className="panel-copy">
            先把当前工作台的关键配置透明展示出来，后面如果要做真正可编辑的设置项，再继续往这里扩展。
          </p>
        </div>
      </header>

      <div className="module-grid settings-grid">
        <article className="module-card setting-card">
          <span className="module-label">API Base URL</span>
          <strong className="setting-value">{API_BASE_URL}</strong>
          <p className="module-note">前端通过这个地址访问 FastAPI 流式接口。</p>
        </article>
        <article className="module-card setting-card">
          <span className="module-label">Storage Key</span>
          <strong className="setting-value inline-code">{STORAGE_KEY}</strong>
          <p className="module-note">用于本地持久化 session、消息和草稿。</p>
        </article>
        <article className="module-card setting-card">
          <span className="module-label">压缩阈值</span>
          <strong className="setting-value">{LOCAL_CONTEXT_TOKEN_LIMIT.toLocaleString()}</strong>
          <p className="module-note">超过阈值后，较早的消息会被压成摘要再写入本地。</p>
        </article>
        <article className="module-card setting-card">
          <span className="module-label">保留最近消息</span>
          <strong className="setting-value">{LOCAL_CONTEXT_KEEP_RECENT}</strong>
          <p className="module-note">压缩时优先保留最近轮次，避免当前上下文被稀释。</p>
        </article>
      </div>

      <article className="module-card wide-card">
        <h2>当前恢复状态</h2>
        <div className="detail-list">
          <div>
            <span>本地存储</span>
            <strong>{storageStatus}</strong>
          </div>
          <div>
            <span>最近保存</span>
            <strong>{formatSavedAt(lastSavedAt)}</strong>
          </div>
          <div>
            <span>当前草稿</span>
            <strong>{input.trim() ? "有未发送内容" : "空"}</strong>
          </div>
        </div>
        <div className="module-actions">
          <button className="ghost-button" type="button" onClick={() => void refreshHealth()}>
            刷新服务状态
          </button>
          <button
            className="ghost-button"
            type="button"
            onClick={() => void resetConversation()}
            disabled={!messages.length && !sessionId && !isStreaming}
          >
            清空本地与会话
          </button>
        </div>
      </article>
    </section>
  );

  const renderSection = () => {
    switch (activeSection) {
      case "control":
        return renderControlView();
      case "agent":
        return renderAgentView();
      case "settings":
        return renderSettingsView();
      case "chat":
      default:
        return renderChatView();
    }
  };

  return (
    <main className="console-shell">
      <aside className="console-sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-kicker">Paper Taste Console</span>
          <h1>论文审美大师</h1>
          <p>
            一个论文科研审美agent，基于阿里云agentscope构建。
          </p>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`sidebar-nav-item${activeSection === item.id ? " active" : ""}`}
              type="button"
              onClick={() => setActiveSection(item.id)}
            >
              <span className="sidebar-nav-label">{item.label}</span>
              <span className="sidebar-nav-description">{item.description}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-meta">
          <div className="sidebar-meta-card">
            <span>Session</span>
            <strong>{shortSessionId}</strong>
          </div>
          <div className="sidebar-meta-card">
            <span>Runtime</span>
            <strong>{runtimeStatus}</strong>
          </div>
          <div className="sidebar-meta-card">
            <span>Storage</span>
            <strong>{storageStatus}</strong>
          </div>
        </div>

        <div className="sidebar-actions">
          <button className="primary-button" type="button" onClick={() => setActiveSection("chat")}>
            去聊天
          </button>
          <button
            className="ghost-button"
            type="button"
            onClick={() => void resetConversation()}
            disabled={!messages.length && !sessionId && !isStreaming}
          >
            新会话
          </button>
        </div>
      </aside>

      <section className="console-stage">{renderSection()}</section>
    </main>
  );
}



