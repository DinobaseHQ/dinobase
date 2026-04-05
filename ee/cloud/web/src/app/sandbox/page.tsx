"use client";

import { createClient } from "@/lib/supabase";
import {
  api,
  type SandboxInfo,
  type SandboxEvent,
} from "@/lib/api";
import { Nav } from "@/components/Nav";
import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TurnRole = "assistant" | "tool" | "tool_result";

interface Turn {
  role: TurnRole;
  text?: string;
  tool?: string;
  input?: Record<string, unknown>;
  output?: string;
}

interface Metric {
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  tool_calls: number;
  turns: number;
}

interface Score {
  correct: boolean;
  partial: boolean;
  explanation: string;
}

interface PanelState {
  turns: Turn[];
  metric?: Metric;
  score?: Score;
  running: boolean;
  error?: string;
}

const emptyPanel = (): PanelState => ({ turns: [], running: false });

// ---------------------------------------------------------------------------
// TurnBlock — renders one conversation turn
// ---------------------------------------------------------------------------

function TurnBlock({
  turn,
  accent,
}: {
  turn: Turn;
  accent: "green" | "zinc";
}) {
  const [expanded, setExpanded] = useState(false);

  if (turn.role === "assistant" && turn.text) {
    return (
      <div className="text-sm text-zinc-100 bg-zinc-800/60 rounded-lg px-3 py-2 leading-relaxed whitespace-pre-wrap">
        {turn.text}
      </div>
    );
  }

  if (turn.role === "tool") {
    const inputStr =
      turn.input && Object.keys(turn.input).length > 0
        ? JSON.stringify(turn.input, null, 2)
        : null;
    return (
      <div
        className={`text-xs font-mono border-l-2 pl-3 ${
          accent === "green" ? "border-dino-green/60" : "border-zinc-500"
        }`}
      >
        <span className="text-zinc-500">→ </span>
        <span
          className={
            accent === "green" ? "text-dino-green" : "text-zinc-300"
          }
        >
          {turn.tool}
        </span>
        {inputStr && (
          <pre className="text-zinc-500 mt-1 whitespace-pre-wrap break-all overflow-x-auto">
            {inputStr}
          </pre>
        )}
      </div>
    );
  }

  if (turn.role === "tool_result") {
    return (
      <div className="text-xs font-mono border-l-2 border-zinc-700 pl-3">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-zinc-600 hover:text-zinc-400 flex items-center gap-1 transition-colors"
        >
          <span>← {turn.tool}</span>
          <span className="text-zinc-700">{expanded ? "▴" : "▾"}</span>
        </button>
        {expanded && (
          <pre className="text-zinc-500 mt-1 whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
            {turn.output}
          </pre>
        )}
      </div>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// ConversationPanel
// ---------------------------------------------------------------------------

function ConversationPanel({
  title,
  subtitle,
  accent,
  panel,
}: {
  title: string;
  subtitle: string;
  accent: "green" | "zinc";
  panel: PanelState;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [panel.turns.length]);

  const scoreColor = panel.score
    ? panel.score.correct
      ? "text-green-400"
      : panel.score.partial
      ? "text-yellow-400"
      : "text-red-400"
    : "";

  const scoreMark = panel.score
    ? panel.score.correct
      ? "✓"
      : panel.score.partial
      ? "~"
      : "✗"
    : "";

  return (
    <div className="flex flex-col bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden min-w-0">
      {/* Header */}
      <div
        className={`flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800 ${
          accent === "green" ? "bg-dino-green/5" : "bg-zinc-800/30"
        }`}
      >
        <span
          className={`text-sm font-semibold ${
            accent === "green" ? "text-dino-green" : "text-zinc-300"
          }`}
        >
          {title}
        </span>
        <span className="text-xs text-zinc-600">{subtitle}</span>
        {panel.running && (
          <span className="ml-auto flex gap-0.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className={`inline-block w-1 h-1 rounded-full ${
                  accent === "green" ? "bg-dino-green" : "bg-zinc-500"
                } animate-bounce`}
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </span>
        )}
      </div>

      {/* Conversation */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-2.5 min-h-64 max-h-[420px]"
      >
        {panel.turns.length === 0 && panel.running && (
          <p className="text-zinc-600 text-sm">Starting…</p>
        )}
        {panel.turns.length === 0 && !panel.running && !panel.error && (
          <p className="text-zinc-700 text-sm">
            Run a question to see the conversation.
          </p>
        )}
        {panel.turns.map((turn, i) => (
          <TurnBlock key={i} turn={turn} accent={accent} />
        ))}
      </div>

      {/* Metrics row */}
      {panel.metric && (
        <div className="border-t border-zinc-800 px-4 py-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
          <span>
            {(
              panel.metric.tokens_in + panel.metric.tokens_out
            ).toLocaleString()}{" "}
            tokens
          </span>
          <span className="text-zinc-600">
            ({panel.metric.tokens_in.toLocaleString()} in /{" "}
            {panel.metric.tokens_out.toLocaleString()} out)
          </span>
          <span>{(panel.metric.latency_ms / 1000).toFixed(1)}s</span>
          <span>{panel.metric.tool_calls} tool calls</span>
        </div>
      )}

      {/* Score */}
      {panel.score && (
        <div
          className={`px-4 py-2 flex items-start gap-2 text-xs border-t border-zinc-800 ${scoreColor}`}
        >
          <span className="font-bold mt-px shrink-0">{scoreMark}</span>
          <span>{panel.score.explanation}</span>
        </div>
      )}

      {/* Error */}
      {panel.error && (
        <div className="px-4 py-2 text-xs text-red-400 border-t border-zinc-800">
          {panel.error}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SandboxPage() {
  const supabase = createClient();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState<SandboxInfo | null>(null);
  const [infoError, setInfoError] = useState("");

  const [question, setQuestion] = useState("");
  const [model, setModel] = useState("claude-haiku-4-5-20251001");
  const [running, setRunning] = useState(false);

  const [dinoPanel, setDinoPanel] = useState<PanelState>(emptyPanel());
  const [mcpPanel, setMcpPanel] = useState<PanelState>(emptyPanel());

  // Dropdown state
  const [showPresets, setShowPresets] = useState(false);

  const loadInfo = useCallback(async (accessToken: string) => {
    try {
      const data = await api.getSandboxInfo(accessToken);
      setInfo(data);
      setModel(data.default_model);
    } catch (e) {
      setInfoError(e instanceof Error ? e.message : "Failed to load sandbox info");
    }
  }, []);

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        const freshToken = session.access_token;
        setEmail(session.user.email ?? "");
        setToken(freshToken);
        if (event === "INITIAL_SESSION" || event === "SIGNED_IN") {
          loadInfo(freshToken).then(() => setLoading(false));
        }
      }
    );
    return () => subscription.unsubscribe();
  }, []);

  const handleRun = useCallback(async () => {
    if (!token || !question.trim() || running) return;

    setRunning(true);
    setDinoPanel({ turns: [], running: true });
    setMcpPanel({ turns: [], running: true });

    try {
      const stream = api.streamSandbox(token, {
        question: question.trim(),
        model,
      });

      for await (const event of stream) {
        handleEvent(event);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Stream error";
      setDinoPanel((p) => ({ ...p, running: false, error: msg }));
      setMcpPanel((p) => ({ ...p, running: false, error: msg }));
    } finally {
      setRunning(false);
    }
  }, [token, question, model, running]);

  function handleEvent(event: SandboxEvent) {
    if (event.type === "turn") {
      const turn: Turn = {
        role: event.role,
        text: event.text,
        tool: event.tool,
        input: event.input,
        output: event.output,
      };
      if (event.approach === "dinobase") {
        setDinoPanel((p) => ({ ...p, turns: [...p.turns, turn] }));
      } else {
        setMcpPanel((p) => ({ ...p, turns: [...p.turns, turn] }));
      }
    } else if (event.type === "metric") {
      const metric: Metric = {
        tokens_in: event.tokens_in,
        tokens_out: event.tokens_out,
        latency_ms: event.latency_ms,
        tool_calls: event.tool_calls,
        turns: event.turns,
      };
      if (event.approach === "dinobase") {
        setDinoPanel((p) => ({ ...p, metric, running: false }));
      } else {
        setMcpPanel((p) => ({ ...p, metric, running: false }));
      }
    } else if (event.type === "score") {
      const score: Score = {
        correct: event.correct,
        partial: event.partial,
        explanation: event.explanation,
      };
      if (event.approach === "dinobase") {
        setDinoPanel((p) => ({ ...p, score }));
      } else {
        setMcpPanel((p) => ({ ...p, score }));
      }
    } else if (event.type === "error") {
      const msg = event.message || "Unknown error";
      if (!event.approach || event.approach === "dinobase") {
        setDinoPanel((p) => ({ ...p, running: false, error: msg }));
      }
      if (!event.approach || event.approach === "mcp") {
        setMcpPanel((p) => ({ ...p, running: false, error: msg }));
      }
    }
  }

  function selectPreset(q: string) {
    setQuestion(q);
    setShowPresets(false);
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-4xl animate-pulse">&#x1F995;</div>
      </div>
    );
  }

  const hasResults =
    dinoPanel.turns.length > 0 || mcpPanel.turns.length > 0 ||
    dinoPanel.running || mcpPanel.running;

  return (
    <>
      <Nav email={email} />
      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-1">Sandbox</h1>
          <p className="text-zinc-500 text-sm">
            Compare Dinobase SQL vs per-source MCP tools side by side — same
            question, same data, judged by AI.
          </p>
        </div>

        {infoError && (
          <div className="bg-red-900/20 border border-red-800 text-red-400 px-4 py-3 rounded-lg mb-6 text-sm">
            {infoError}
          </div>
        )}

        {/* Controls */}
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          {/* Question input + presets */}
          <div className="relative flex-1">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun();
              }}
              placeholder="Ask a question about your data…"
              rows={2}
              disabled={running}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none disabled:opacity-50"
            />
            {/* Preset dropdown */}
            {info && info.suggested_questions.length > 0 && (
              <div className="absolute right-2 top-2">
                <button
                  onClick={() => setShowPresets((v) => !v)}
                  disabled={running}
                  className="text-xs text-zinc-500 hover:text-zinc-300 bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded transition-colors disabled:opacity-40"
                >
                  Examples ▾
                </button>
                {showPresets && (
                  <div className="absolute right-0 top-7 z-10 w-80 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl py-1">
                    {info.suggested_questions.map((q, i) => (
                      <button
                        key={i}
                        onClick={() => selectPreset(q)}
                        className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700 transition-colors"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Model + Run */}
          <div className="flex gap-2 items-start sm:items-stretch">
            {info && info.models.length > 1 && (
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={running}
                className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-300 focus:outline-none focus:border-zinc-500 disabled:opacity-50"
              >
                {info.models.map((m) => (
                  <option key={m} value={m}>
                    {m.replace("claude-", "").replace("-20251001", "")}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={handleRun}
              disabled={running || !question.trim()}
              className="bg-dino-green text-white px-5 py-2 rounded-lg text-sm font-medium hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition-all whitespace-nowrap"
            >
              {running ? "Running…" : "Run →"}
            </button>
          </div>
        </div>

        {/* Side-by-side panels */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ConversationPanel
            title="Dinobase SQL"
            subtitle="unified query across all sources"
            accent="green"
            panel={dinoPanel}
          />
          <ConversationPanel
            title="Per-Source MCP"
            subtitle="separate API tool per table"
            accent="zinc"
            panel={mcpPanel}
          />
        </div>

        {/* Legend */}
        {!hasResults && info && info.sources.length > 0 && (
          <div className="mt-6 text-xs text-zinc-600">
            Connected sources:{" "}
            {info.sources
              .map((s) => `${s.name} (${s.table_count} tables)`)
              .join(", ")}
          </div>
        )}

        {/* No sources warning */}
        {!infoError && info && info.sources.length === 0 && (
          <div className="mt-6 bg-zinc-900 border border-zinc-800 border-dashed rounded-lg px-5 py-8 text-center text-zinc-500 text-sm">
            No data sources connected.{" "}
            <a href="/dashboard" className="text-dino-green hover:underline">
              Connect a source
            </a>{" "}
            to use the sandbox.
          </div>
        )}
      </main>
    </>
  );
}
